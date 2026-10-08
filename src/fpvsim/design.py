"""Loading a design: spec + build + component files -> models.

A *build* is a list of parts placed in the body frame, plus the frame,
powertrain and battery it uses. Loading collects every physical parameter
into one flat ``ParamSet`` (keyed like ``motor.kv`` or ``frame.arm.mass``).
``Build.realize`` then constructs the physical models from any set of values,
so the same code serves nominal analysis and Monte Carlo samples.

Identical parts (four motors, four arms) share one parameter key, so their
values are fully correlated in uncertainty analysis. Asymmetry between
nominally identical parts is not modelled at this stage.

Design versions: a build file can ``extends`` another and list only what
changes, like an engineering change order. Parts merge by name (a part with
an existing name replaces it, a new name is added), ``remove_parts`` deletes
parts, and component roles and [electrical] / [flight_controller] keys
override the base. Relative paths are resolved against the file that wrote
them, so a variant may live in another directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import units
from .airframe import AirframeExtras, GyroSpec
from .atmosphere import Environment
from .battery import Battery
from .bemt import Airfoil, BladeGeometry, coefficient_curves
from .mass import BoxShape, CylinderShape, MassItem, MassProperties, PointShape, Shape, combine, rotation_matrix
from .motor import ESC, Motor
from .params import Param, ParamError, ParamSet, Source, Values, component_stream, parse_param, parse_vector
from .powertrain import Powertrain
from .prop import Prop, PropCurves

COMPONENT_SCHEMA = "fpvsim.component/1"
BUILD_SCHEMA = "fpvsim.build/1"
SPEC_SCHEMA = "fpvsim.spec/1"

_REQUIRED = {
    "motor": ("kv", "rm", "i0_ref", "v_i0_ref", "i0_speed_fraction", "rotor_inertia", "max_current"),
    "prop": ("diameter", "pitch", "spin_inertia", "rotor_drag_factor"),
    "esc": ("r_on", "quiescent_power", "max_current", "brake_current_limit", "drive_current_limit"),
    "battery": ("capacity", "r0_cell", "r1_cell", "tau1", "c_rating"),
    "frame": (
        "thrust_interference",
        "cda_x",
        "cda_y",
        "cda_z",
        "contact_stiffness",
        "contact_damping",
        "ground_friction",
        "vib_amp_1",
        "vib_amp_2",
        "vib_amp_3",
        "vib_ref_speed",
        "vib_exponent",
        "vib_yaw_ratio",
    ),
}
_POWERTRAIN_ROLES = ("frame", "motor", "prop", "esc", "battery")


class DesignError(ValueError):
    pass


# ---------------------------------------------------------------- file helpers


def _read_toml(path: Path, schema: str) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise DesignError(f"file not found: {path}") from None
    if data.get("schema") != schema:
        raise DesignError(f"{path}: expected schema = {schema!r}, got {data.get('schema')!r}")
    misplaced = {"mass", "shape", "cg_offset", "drag_center"} & set(data.get("meta", {}))
    if misplaced:
        raise DesignError(f"{path}: {sorted(misplaced)} ended up inside [meta]; put top-level keys before the first table")
    return data


def _parse_shape(where: str, entry: Mapping[str, Any] | None) -> Shape:
    if entry is None:
        return PointShape()
    kind = entry.get("type")
    unit = entry.get("unit", "mm")
    if kind == "point":
        return PointShape()
    if kind == "box":
        size = entry.get("size")
        if not isinstance(size, list) or len(size) != 3:
            raise DesignError(f"{where}: box shape needs size = [lx, ly, lz]")
        return BoxShape(*(units.to_si(float(s), unit) for s in size))
    if kind == "cylinder":
        return CylinderShape(
            radius=units.to_si(float(entry["radius"]), unit),
            height=units.to_si(float(entry["height"]), unit),
            inner_radius=units.to_si(float(entry.get("inner_radius", 0.0)), unit),
        )
    raise DesignError(f"{where}: unknown shape type {kind!r} (use point, box or cylinder)")


def _rotation(where: str, entry: Any) -> np.ndarray:
    if entry is None:
        return np.eye(3)
    if not isinstance(entry, list) or len(entry) != 3:
        raise DesignError(f"{where}: rotation_deg must be [roll, pitch, yaw]")
    return rotation_matrix(*(math.radians(float(a)) for a in entry))


def _int(where: str, table: Mapping[str, Any], key: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DesignError(f"{where}: config.{key} must be a positive integer")
    return value


# ----------------------------------------------------------------- data model


@dataclass(frozen=True)
class PartTemplate:
    """A part placed in the body frame; its mass is looked up by key."""

    name: str
    group: str
    mass_key: str
    shape: Shape
    position: np.ndarray
    rotation: np.ndarray
    power_key: str | None = None  # W drawn from the regulated rail, if any
    drag_keys: tuple[str | None, str | None, str | None] = (None, None, None)  # the part's own CdA per body axis
    offset_keys: tuple[str, str, str] | None = None  # the part's own placement uncertainty (x, y, z), m
    mounted_on: str | None = None  # parent part: this part moves with the parent's placement error
    inherited_offsets: tuple[tuple[str, str, str], ...] = ()  # the parent chain's offset keys, resolved at load
    component: str | None = None  # component file the part is made from (file name), None for inline parts
    component_id: str | None = None  # its identity (id and content hash), as used for the random streams

    def placed(self, v) -> np.ndarray:
        chain = self.inherited_offsets + ((self.offset_keys,) if self.offset_keys else ())
        if not chain:
            return self.position
        return self.position + sum(np.array([v(k) for k in keys]) for keys in chain)


@dataclass(frozen=True)
class RotorMount:
    position: np.ndarray  # motor mounting point, body frame
    spin: str  # "cw" or "ccw" seen from above


@dataclass(frozen=True)
class DataTable:
    """Provenance of array data (blade geometry, OCV curve)."""

    name: str
    source: Source
    ref: str
    note: str


@dataclass(frozen=True)
class Requirement:
    id: str
    metric: str
    limit: float  # SI
    kind: str  # "min" or "max"
    unit: str  # display unit
    title: str
    rationale: str

    def passes(self, value: float) -> bool:
        if not math.isfinite(value):
            return False
        return value >= self.limit if self.kind == "min" else value <= self.limit


@dataclass(frozen=True)
class Spec:
    id: str
    name: str
    description: str
    requirements: list[Requirement]


@dataclass(frozen=True)
class EnduranceCriteria:
    reserve_soc: float
    min_cell_voltage: float


@dataclass(frozen=True)
class Aircraft:
    """One fully specified physical realization of a build."""

    name: str
    items: list[MassItem]
    mass_props: MassProperties
    powertrain: Powertrain
    battery: Battery
    harness_resistance: float
    thrust_interference: float
    motor_idle: float
    rotors: list[RotorMount]
    env: Environment
    criteria: EnduranceCriteria
    extras: AirframeExtras
    gyro: GyroSpec

    @property
    def weight(self) -> float:
        return self.mass_props.mass * self.env.g

    @property
    def thrust_centroid(self) -> np.ndarray:
        return np.mean([r.position for r in self.rotors], axis=0)


@dataclass
class Build:
    id: str
    name: str
    description: str
    path: Path
    spec: Spec
    params: ParamSet
    parts: list[PartTemplate]
    rotors: list[RotorMount]
    contacts: list[np.ndarray]
    drag_center: np.ndarray  # where the frame's own drag acts, mount origin frame, m
    fc_board: str
    battery_series: int
    battery_parallel: int
    ocv_soc: np.ndarray
    ocv_cell: np.ndarray
    prop_blades: int
    prop_curves: PropCurves
    prop_curve_source: Source
    component_files: dict[str, Path]
    model_inputs: ParamSet = field(default_factory=ParamSet)  # inputs of derived models, not sampled
    tables: list[DataTable] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    lineage: list[dict] = field(default_factory=list)  # base first: id, name, change, path

    def input_hash(self) -> str:
        """SHA-256 over every input file, to tie a report to its exact inputs."""
        h = hashlib.sha256()
        for path in sorted(set(self.files)):
            h.update(path.name.encode())
            h.update(path.read_bytes())
        return h.hexdigest()

    def realize(self, overrides: Mapping[str, float] | None = None) -> Aircraft:
        v = Values(self.params, overrides)

        prop = Prop(
            diameter=v("prop.diameter"),
            blades=self.prop_blades,
            pitch=v("prop.pitch"),
            mass=v("prop.mass"),
            spin_inertia=v("prop.spin_inertia"),
            curves=self.prop_curves,
            ct_scale=v("prop.ct_scale"),
            cp_scale=v("prop.cp_scale"),
        )
        motor = Motor(
            kv=v("motor.kv"),
            rm=v("motor.rm"),
            i0_ref=v("motor.i0_ref"),
            v_i0_ref=v("motor.v_i0_ref"),
            i0_speed_fraction=min(max(v("motor.i0_speed_fraction"), 0.0), 1.0),
            rotor_inertia=v("motor.rotor_inertia"),
            max_current=v("motor.max_current"),
        )
        esc = ESC(r_on=v("esc.r_on"), quiescent_power=v("esc.quiescent_power"), max_current=v("esc.max_current"))
        capacity = v("battery.capacity")
        battery = Battery(
            series=self.battery_series,
            parallel=self.battery_parallel,
            capacity=capacity,
            r0_cell=v("battery.r0_cell"),
            r1_cell=v("battery.r1_cell"),
            tau1=v("battery.tau1"),
            ocv_soc=self.ocv_soc,
            ocv_cell=self.ocv_cell,
            max_current=v("battery.c_rating") * capacity / 3600.0,
        )

        items = [
            MassItem(p.name, p.group, p.mass_key, v(p.mass_key), p.placed(v), p.shape, p.rotation) for p in self.parts
        ]
        rail_power = sum(v(p.power_key) for p in self.parts if p.power_key)
        p_aux = rail_power / v("electrical.bec_efficiency") + esc.quiescent_power

        return Aircraft(
            name=self.name,
            items=items,
            mass_props=combine(items),
            powertrain=Powertrain(motor, prop, esc, len(self.rotors), p_aux),
            battery=battery,
            harness_resistance=v("electrical.harness_resistance"),
            thrust_interference=v("frame.thrust_interference"),
            motor_idle=v("flight_controller.motor_idle"),
            rotors=self.rotors,
            env=Environment(altitude=v("env.altitude"), temperature=v("env.temperature")),
            criteria=EnduranceCriteria(
                reserve_soc=v("criteria.reserve_soc"), min_cell_voltage=v("criteria.min_cell_voltage")
            ),
            extras=AirframeExtras(
                cda=tuple(v(f"frame.cda_{axis}") for axis in "xyz"),
                cda_center=tuple(float(x) for x in self.drag_center),
                drag_points=tuple(
                    (
                        tuple(float(x) for x in p.placed(v)),
                        tuple(v(k) if k else 0.0 for k in p.drag_keys),
                    )
                    for p in self.parts
                    if any(p.drag_keys)
                ),
                rotor_drag_factor=v("prop.rotor_drag_factor"),
                brake_current_limit=v("esc.brake_current_limit"),
                drive_current_limit=v("esc.drive_current_limit"),
                contacts=tuple(tuple(float(x) for x in c) for c in self.contacts),
                contact_stiffness=v("frame.contact_stiffness"),
                contact_damping=v("frame.contact_damping"),
                ground_friction=v("frame.ground_friction"),
            ),
            gyro=GyroSpec(
                noise_density=v(f"{self.fc_board}.gyro_noise_density"),
                vib_amplitudes=(v("frame.vib_amp_1"), v("frame.vib_amp_2"), v("frame.vib_amp_3")),
                vib_harmonics=(1, 2, self.prop_blades),
                vib_ref_speed=v("frame.vib_ref_speed"),
                vib_exponent=v("frame.vib_exponent"),
                vib_yaw_ratio=v("frame.vib_yaw_ratio"),
            ),
        )


# -------------------------------------------------------------------- loaders


def load_spec(path: Path, params: ParamSet) -> Spec:
    data = _read_toml(path, SPEC_SCHEMA)
    meta = data.get("meta", {})
    for section, keys, prefix in (
        ("environment", ("altitude", "temperature"), "env"),
        ("endurance", ("reserve_soc", "min_cell_voltage"), "criteria"),
    ):
        table = data.get(section, {})
        for key in keys:
            if key not in table:
                raise DesignError(f"{path}: [{section}] needs {key}")
            params.add(parse_param(f"{prefix}.{key}", table[key]))

    from .performance import METRICS  # local import: performance depends on design

    requirements = []
    for i, entry in enumerate(data.get("requirements", [])):
        where = f"{path}: requirements[{i}]"
        metric = entry.get("metric")
        if metric not in METRICS:
            raise DesignError(f"{where}: unknown metric {metric!r}; known: {sorted(METRICS)}")
        kinds = [k for k in ("min", "max") if k in entry]
        if len(kinds) != 1:
            raise DesignError(f"{where}: give exactly one of min or max")
        unit = entry.get("unit", METRICS[metric].unit)
        if units.si_unit(unit) != units.si_unit(METRICS[metric].unit):
            raise DesignError(f"{where}: unit {unit!r} does not match metric {metric!r}")
        requirements.append(
            Requirement(
                id=str(entry.get("id", f"R{i + 1}")),
                metric=metric,
                limit=units.to_si(float(entry[kinds[0]]), unit),
                kind=kinds[0],
                unit=unit,
                title=str(entry.get("title", METRICS[metric].title)),
                rationale=str(entry.get("rationale", "")),
            )
        )
    return Spec(str(meta.get("id", path.stem)), str(meta.get("name", "")), str(meta.get("description", "")), requirements)


def _load_component(path: Path, role: str, category: str, params: ParamSet) -> dict[str, Any]:
    data = _read_toml(path, COMPONENT_SCHEMA)
    meta = data.get("meta", {})
    if meta.get("category") != category:
        raise DesignError(f"{path}: expected category {category!r}, got {meta.get('category')!r}")
    table = data.get("params", {})
    for key in _REQUIRED.get(category, ()):
        if key not in table:
            raise DesignError(f"{path}: [params] needs {key}")
    cid = _component_id(path, data)
    for key, entry in table.items():
        params.add(parse_param(f"{role}.{key}", entry, component_stream(cid, key)))
    if "mass" in data:
        params.add(parse_param(f"{role}.mass", data["mass"], component_stream(cid, "mass")))
    return data


def _component_id(path: Path, data: Mapping[str, Any]) -> str:
    """Identity of a component file as a physical item, for paired sampling:
    its id (or file name) plus a hash of its parsed contents (comments and
    formatting do not count). The same file in two builds is the same item;
    a copied file with edited values is a different item even if it kept the
    id, so it gets independent random errors."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{data.get('meta', {}).get('id') or path.stem}#{digest}"


def _absolute(base: Path, value: Any) -> str:
    return str((base / str(value)).resolve())


def _absolutise(data: dict[str, Any], base: Path) -> dict[str, Any]:
    """Copy of raw build data with every file path made absolute."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in data.items()}
    meta = out.setdefault("meta", {})
    for key in ("spec", "extends"):
        if key in meta:
            meta[key] = _absolute(base, meta[key])
    if "components" in out:
        out["components"] = {role: _absolute(base, p) for role, p in out["components"].items()}
    parts = []
    for entry in out.get("parts", []):
        entry = dict(entry)
        if "component" in entry:
            entry["component"] = _absolute(base, entry["component"])
        parts.append(entry)
    if "parts" in out:
        out["parts"] = parts
    return out


def _merge_builds(base: dict[str, Any], variant: dict[str, Any], where: Path) -> dict[str, Any]:
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    vmeta = variant.get("meta", {})
    # a version never inherits the base's identity: id, name, description and change are its own
    identity = ("extends", "change", "remove_parts", "id", "name", "description")
    meta = {k: v for k, v in merged.get("meta", {}).items() if k not in identity}
    meta.update({k: v for k, v in vmeta.items() if k not in ("extends", "remove_parts")})
    merged["meta"] = meta
    for table in ("components", "electrical", "flight_controller"):
        if table in variant:
            merged[table] = {**merged.get(table, {}), **variant[table]}
    parts = list(merged.get("parts", []))
    names = [p.get("name") for p in parts]
    for name in vmeta.get("remove_parts", []):
        if name not in names:
            raise DesignError(f"{where}: remove_parts names {name!r}, which the base build does not have")
        parts = [p for p in parts if p.get("name") != name]
        names = [p.get("name") for p in parts]
    for entry in variant.get("parts", []):
        name = entry.get("name")
        if name in names:
            parts[names.index(name)] = entry
        else:
            parts.append(entry)
            names.append(name)
    merged["parts"] = parts
    return merged


def _resolve_build(path: Path, chain: tuple[Path, ...] = ()) -> tuple[dict[str, Any], list[Path], list[dict]]:
    """Raw build data with its ``extends`` chain merged in, plus the files and
    the version lineage (base first)."""
    if path in chain:
        cycle = " -> ".join(str(p.name) for p in (*chain, path))
        raise DesignError(f"circular extends: {cycle}")
    data = _absolutise(_read_toml(path, BUILD_SCHEMA), path.parent)
    meta = data["meta"]
    entry = {
        "id": str(meta.get("id", path.stem)),
        "name": str(meta.get("name", path.stem)),
        "change": str(meta.get("change", "")),
        "path": path,
    }
    if "extends" not in meta:
        if "remove_parts" in meta:
            raise DesignError(f"{path}: remove_parts needs extends")
        return data, [path], [entry]
    base_data, files, lineage = _resolve_build(Path(meta["extends"]), (*chain, path))
    return _merge_builds(base_data, data, path), [*files, path], [*lineage, entry]


def load_build(path: str | Path) -> Build:
    path = Path(path).resolve()
    data, files, lineage = _resolve_build(path)
    base = path.parent
    meta = data.get("meta", {})
    params = ParamSet()
    files = list(files)

    if "spec" not in meta:
        raise DesignError(f"{path}: [meta] needs spec = <path to spec file>")
    spec_path = (base / meta["spec"]).resolve()
    files.append(spec_path)
    spec = load_spec(spec_path, params)

    roles = data.get("components", {})
    missing = [r for r in _POWERTRAIN_ROLES if r not in roles]
    if missing:
        raise DesignError(f"{path}: [components] is missing {missing}")
    component_files = {role: (base / roles[role]).resolve() for role in _POWERTRAIN_ROLES}
    files.extend(component_files.values())
    comp = {role: _load_component(component_files[role], role, role, params) for role in _POWERTRAIN_ROLES}

    for key in ("harness_resistance", "bec_efficiency"):
        entry = data.get("electrical", {}).get(key)
        if entry is None:
            raise DesignError(f"{path}: [electrical] needs {key}")
        params.add(parse_param(f"electrical.{key}", entry))
    fc_table = data.get("flight_controller", {})
    if "motor_idle" not in fc_table or "board" not in fc_table:
        raise DesignError(f"{path}: [flight_controller] needs motor_idle and board (the part name of the FC)")
    params.add(parse_param("flight_controller.motor_idle", fc_table["motor_idle"]))

    parts: list[PartTemplate] = []
    rotors = _frame_parts(component_files["frame"], comp["frame"], params, parts)
    _rotor_parts(comp, rotors, parts)
    model_inputs = ParamSet()
    tables: list[DataTable] = []
    prop_curves, prop_curve_source = _prop_curves(component_files["prop"], comp["prop"], params, model_inputs, tables)

    for i, entry in enumerate(data.get("parts", [])):
        parts.append(_build_part(path, base, i, entry, comp, params, files))
    parts = _resolve_mounts(path, parts)
    for role in ("battery", "esc"):
        placed = sum(1 for p in parts if p.mass_key == f"{role}.mass")
        if placed != 1:
            raise DesignError(f"{path}: place the {role} exactly once with [[parts]] uses = {role!r} (found {placed})")
    board = str(fc_table["board"])
    if f"{board}.gyro_noise_density" not in params:
        raise DesignError(f"{path}: flight controller part {board!r} must define gyro_noise_density in its [params]")
    contacts = [
        parse_vector(f"{component_files['frame']}: contacts[{i}].position", c.get("position"))
        for i, c in enumerate(comp["frame"].get("contacts", []))
    ]
    if len(contacts) < 3:
        raise DesignError(f"{component_files['frame']}: a frame needs at least 3 [[contacts]] ground contact points")
    if "drag_center" not in comp["frame"]:
        raise DesignError(f"{component_files['frame']}: needs drag_center, the point where the frame's drag acts")
    drag_center = parse_vector(f"{component_files['frame']}: drag_center", comp["frame"]["drag_center"])

    battery_cfg = comp["battery"].get("config", {})
    ocv = comp["battery"].get("ocv", {})
    ocv_soc = np.asarray(ocv.get("soc", []), dtype=float)
    ocv_cell = np.asarray(ocv.get("cell_voltage", []), dtype=float)
    if len(ocv_soc) < 2 or len(ocv_soc) != len(ocv_cell):
        raise DesignError(f"{component_files['battery']}: [ocv] needs matching soc and cell_voltage arrays")
    tables.append(_table(component_files["battery"], "battery.ocv", ocv))

    build = Build(
        id=str(meta.get("id", path.stem)),
        name=str(meta.get("name", path.stem)),
        description=str(meta.get("description", "")),
        path=path,
        spec=spec,
        params=params,
        parts=parts,
        rotors=rotors,
        contacts=contacts,
        drag_center=drag_center,
        fc_board=board,
        battery_series=_int(str(component_files["battery"]), battery_cfg, "series"),
        battery_parallel=_int(str(component_files["battery"]), battery_cfg, "parallel"),
        ocv_soc=ocv_soc,
        ocv_cell=ocv_cell,
        prop_blades=_int(str(component_files["prop"]), comp["prop"].get("config", {}), "blades"),
        prop_curves=prop_curves,
        prop_curve_source=prop_curve_source,
        component_files=component_files,
        model_inputs=model_inputs,
        tables=tables,
        files=files,
        lineage=lineage,
    )
    build.realize()  # fail at load time, not halfway through an analysis
    return build


def _frame_parts(path: Path, data: dict[str, Any], params: ParamSet, parts: list[PartTemplate]) -> list[RotorMount]:
    rotors = []
    for i, entry in enumerate(data.get("rotors", [])):
        spin = entry.get("spin")
        if spin not in ("cw", "ccw"):
            raise DesignError(f"{path}: rotors[{i}].spin must be 'cw' or 'ccw'")
        rotors.append(RotorMount(parse_vector(f"{path}: rotors[{i}].position", entry.get("position")), spin))
    if len(rotors) < 3:
        raise DesignError(f"{path}: a frame needs at least 3 [[rotors]] mounts")

    for i, entry in enumerate(data.get("parts", [])):
        where = f"{path}: parts[{i}]"
        name = entry.get("name")
        if not name:
            raise DesignError(f"{where}: needs a name")
        key = f"frame.{name}.mass"
        params.add(parse_param(key, entry.get("mass"), component_stream(_component_id(path, data), f"parts.{name}.mass")))
        shape = _parse_shape(where, entry.get("shape"))
        placements = entry.get("placements")
        if not isinstance(placements, list) or not placements:
            raise DesignError(f"{where}: needs placements = [{{ position = ..., rotation_deg = ... }}, ...]")
        for j, place in enumerate(placements):
            parts.append(
                PartTemplate(
                    name=f"{name}[{j}]" if len(placements) > 1 else name,
                    group="frame",
                    mass_key=key,
                    shape=shape,
                    position=parse_vector(f"{where}.placements[{j}].position", place.get("position")),
                    rotation=_rotation(where, place.get("rotation_deg")),
                )
            )
    return rotors


def _rotor_parts(comp: dict[str, dict[str, Any]], rotors: list[RotorMount], parts: list[PartTemplate]) -> None:
    for role in ("motor", "prop"):
        data = comp[role]
        shape = _parse_shape(role, data.get("shape"))
        offset = parse_vector(f"{role}.cg_offset", data["cg_offset"]) if "cg_offset" in data else np.zeros(3)
        for i, rotor in enumerate(rotors):
            parts.append(
                PartTemplate(
                    name=f"{role}[{i}]",
                    group="propulsion",
                    mass_key=f"{role}.mass",
                    shape=shape,
                    position=rotor.position + offset,
                    rotation=np.eye(3),
                )
            )


def _table(path: Path, name: str, table: Mapping[str, Any]) -> DataTable:
    try:
        source = Source(table["source"])
    except (KeyError, ValueError):
        raise DesignError(f"{path}: table {name} needs a valid source") from None
    return DataTable(name, source, str(table.get("ref", "")), str(table.get("note", "")))


def _prop_curves(
    path: Path, data: dict[str, Any], params: ParamSet, model_inputs: ParamSet, tables: list[DataTable]
) -> tuple[PropCurves, Source]:
    """Measured coefficient tables take precedence; otherwise run BEMT."""
    if "coefficients" in data:
        table = data["coefficients"]
        tables.append(_table(path, "prop.coefficients", table))
        source = tables[-1].source
        curves = PropCurves(
            np.asarray(table["J"], dtype=float), np.asarray(table["ct"], dtype=float), np.asarray(table["cp"], dtype=float)
        )
        ref = str(table.get("ref", ""))
        u_ct, u_cp = float(table.get("ct_u_rel", 0.0)), float(table.get("cp_u_rel", 0.0))
    elif "bemt" in data:
        bemt = data["bemt"]
        blades = _int(str(path), data.get("config", {}), "blades")
        curves = _run_bemt(path, bemt, blades, params, model_inputs, tables)
        source = Source.DERIVED
        ref = "BEMT（fpvsim.bemt，由槳葉幾何計算）"
        u_ct, u_cp = float(bemt["ct_model_u_rel"]), float(bemt["cp_model_u_rel"])
    else:
        raise DesignError(f"{path}: a prop needs [coefficients] (measured) or [bemt] (geometry)")

    for name, u_rel in (("ct_scale", u_ct), ("cp_scale", u_cp)):
        params.add(
            Param(
                key=f"prop.{name}",
                value=1.0,
                unit="1",
                source=source,
                u=u_rel,
                ref=ref,
                note="係數曲線的模型不確定度乘數",
                stream=component_stream(_component_id(path, data), name),
            )
        )
    return curves, source


def _run_bemt(
    path: Path, bemt: Mapping[str, Any], blades: int, params: ParamSet, model_inputs: ParamSet, tables: list[DataTable]
) -> PropCurves:
    """Run BEMT once at nominal inputs. Its inputs are recorded for provenance
    but not sampled: their uncertainty is carried by ct_scale and cp_scale."""
    for key in ("ct_model_u_rel", "cp_model_u_rel"):
        if key not in bemt:
            raise DesignError(f"{path}: [bemt] needs {key}")
    foil_table = bemt.get("airfoil", {})
    foil_values = {}
    for key in ("cl_alpha", "alpha0", "cl_max", "cl_min", "cd_min", "cl_cd_min", "k_cd"):
        if key not in foil_table:
            raise DesignError(f"{path}: [bemt.airfoil] needs {key}")
        foil_values[key] = model_inputs.add(parse_param(f"prop.airfoil.{key}", foil_table[key])).value
    blade = bemt.get("blade", {})
    tables.append(_table(path, "prop.blade", blade))
    unit = blade.get("chord_unit", "mm")
    hub = model_inputs.add(parse_param("prop.hub_radius", bemt.get("hub_radius"))).value
    geom = BladeGeometry(
        radius=0.5 * params["prop.diameter"].value,
        hub_radius=hub,
        r_over_R=np.asarray(blade["r_over_R"], dtype=float),
        chord=np.asarray([units.to_si(float(c), unit) for c in blade["chord"]]),
        pitch=params["prop.pitch"].value,
        blades=blades,
    )
    J = np.asarray(bemt.get("J", np.round(np.arange(0.0, 1.0001, 0.05), 4).tolist()), dtype=float)
    return coefficient_curves(geom, Airfoil(**foil_values), J)


def _build_part(
    path: Path,
    base: Path,
    i: int,
    entry: Mapping[str, Any],
    comp: dict[str, dict[str, Any]],
    params: ParamSet,
    files: list[Path],
) -> PartTemplate:
    where = f"{path}: parts[{i}]"
    name = entry.get("name")
    if not name:
        raise DesignError(f"{where}: needs a name")
    if name in _RESERVED_PREFIXES:
        raise DesignError(f"{where}: part name {name!r} is reserved; choose another name")
    position = parse_vector(f"{where}.position", entry.get("position"))
    rotation = _rotation(where, entry.get("rotation_deg"))
    component = component_id = None
    offset_keys = _placement_uncertainty(where, name, entry.get("position_u"), params)
    mounted_on = entry.get("mounted_on")
    if mounted_on is not None and (not isinstance(mounted_on, str) or mounted_on == name):
        raise DesignError(f"{where}: mounted_on must name another part")
    power_key = None
    drag = {}
    for axis in "xyz":  # inline drag areas, e.g. cda_x = { value = ..., unit = "cm^2", ... }
        if f"cda_{axis}" in entry and "component" in entry:
            raise DesignError(f"{where}: give drag areas in the component file, not in the part entry")
        if f"cda_{axis}" in entry:
            drag[axis] = params.add(parse_param(f"{name}.cda_{axis}", entry[f"cda_{axis}"])).key

    if "uses" in entry:  # a powertrain component placed as a part (battery, ESC)
        role = entry["uses"]
        if role not in ("battery", "esc"):
            raise DesignError(f"{where}: uses must be 'battery' or 'esc'")
        data = comp[role]
        mass_key = f"{role}.mass"
        if mass_key not in params:
            raise DesignError(f"{where}: component {role!r} has no mass")
        shape = _parse_shape(where, data.get("shape"))
        group = "battery" if role == "battery" else "avionics"
    elif "component" in entry:  # a separate component file (electronics)
        comp_path = (base / entry["component"]).resolve()
        files.append(comp_path)
        data = _read_toml(comp_path, COMPONENT_SCHEMA)
        if "mass" not in data:
            raise DesignError(f"{comp_path}: needs mass")
        mass_key = f"{name}.mass"
        cid = _component_id(comp_path, data)
        # the stream is scoped to the part name: two parts made from one file are two items
        params.add(parse_param(mass_key, data["mass"], component_stream(cid, f"{name}.mass")))
        for key, value in data.get("params", {}).items():
            added = params.add(parse_param(f"{name}.{key}", value, component_stream(cid, f"{name}.{key}")))
            if key in ("cda_x", "cda_y", "cda_z"):
                drag[key[-1]] = added.key
        if f"{name}.power" in params:
            power_key = f"{name}.power"
        shape = _parse_shape(str(comp_path), data.get("shape"))
        group = entry.get("group", data.get("meta", {}).get("category", "avionics"))
        component, component_id = comp_path.name, cid
    else:  # inline part
        mass_key = f"{name}.mass"
        params.add(parse_param(mass_key, entry.get("mass")))
        shape = _parse_shape(where, entry.get("shape"))
        group = entry.get("group", "misc")

    drag_keys = tuple(drag.get(axis) for axis in "xyz")
    return PartTemplate(name, str(group), mass_key, shape, position, rotation, power_key, drag_keys, offset_keys, mounted_on,
                        component=component, component_id=component_id)


_RESERVED_PREFIXES = {"frame", "motor", "prop", "electrical", "flight_controller", "env", "criteria"}


def _resolve_mounts(path: Path, parts: list[PartTemplate]) -> list[PartTemplate]:
    """``mounted_on = "battery"``: the part is fixed to another part, so its
    placement error is the parent's (and the parent's parent's) plus its own
    ``position_u``, which is then relative to the parent."""
    by_name = {p.name: p for p in parts}

    def chain(p: PartTemplate, seen: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
        if p.mounted_on is None:
            return ()
        if p.mounted_on in seen:
            raise DesignError(f"{path}: mounted_on forms a loop: {' -> '.join(seen + (p.mounted_on,))}")
        parent = by_name.get(p.mounted_on)
        if parent is None:
            raise DesignError(f"{path}: part {p.name!r} is mounted_on unknown part {p.mounted_on!r}")
        own = (parent.offset_keys,) if parent.offset_keys else ()
        return chain(parent, seen + (parent.name,)) + own

    return [replace(p, inherited_offsets=chain(p, (p.name,))) if p.mounted_on else p for p in parts]


def _placement_uncertainty(where: str, name: str, entry: Any, params: ParamSet) -> tuple[str, str, str] | None:
    """``position_u = { value = [ux, uy, uz], unit = "mm", source = ..., note = ... }``:
    standard uncertainty of where the part ends up (straps, mounts, the pilot)."""
    if entry is None:
        return None
    if not isinstance(entry, Mapping) or "source" not in entry:
        raise DesignError(f"{where}: position_u needs value = [ux, uy, uz], unit and source")
    spread = parse_vector(f"{where}.position_u", entry)
    unit = entry["unit"]
    keys = []
    for axis, u in zip("xyz", spread):
        param = parse_param(
            f"{name}.offset_{axis}",
            {"value": 0.0, "unit": unit, "source": entry["source"], "u": u / units.scale(unit),
             "note": str(entry.get("note", "安裝位置的不確定度"))},
        )
        keys.append(params.add(param).key)
    return tuple(keys)


def check_sources(build: Build) -> list[str]:
    """Return warnings for parameters whose provenance is weak or incomplete."""
    warnings = []
    for p in build.params:
        if p.source in (Source.ESTIMATE, Source.DERIVED) and not p.uncertain:
            warnings.append(f"{p.key}: {p.source.value} value without an uncertainty")
        if p.source == Source.SYNTHETIC:
            warnings.append(f"{p.key}: synthetic data must not be used in a design")
        if p.source in (Source.DATASHEET, Source.LITERATURE, Source.MEASURED) and not p.ref:
            warnings.append(f"{p.key}: {p.source.value} value without a reference")
    return warnings


__all__ = [
    "Aircraft",
    "Build",
    "DesignError",
    "EnduranceCriteria",
    "ParamError",
    "Requirement",
    "Spec",
    "check_sources",
    "load_build",
]
