"""Loading a design: spec + build + component files -> models.

A *build* is a list of parts placed in the body frame, plus the frame,
powertrain and battery it uses. Loading collects every physical parameter
into one flat ``ParamSet`` (keyed like ``motor.kv`` or ``frame.arm.mass``).
``Build.realize`` then constructs the physical models from any set of values,
so the same code serves nominal analysis and Monte Carlo samples.

Identical parts (four motors, four arms) share one parameter key, so their
values are fully correlated in uncertainty analysis. Asymmetry between
nominally identical parts is not modelled at this stage.
"""

from __future__ import annotations

import hashlib
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import units
from .atmosphere import Environment
from .battery import Battery
from .bemt import Airfoil, BladeGeometry, coefficient_curves
from .mass import BoxShape, CylinderShape, MassItem, MassProperties, PointShape, Shape, combine, rotation_matrix
from .motor import ESC, Motor
from .params import Param, ParamError, ParamSet, Source, Values, parse_param, parse_vector
from .powertrain import Powertrain
from .prop import Prop, PropCurves

COMPONENT_SCHEMA = "fpvsim.component/1"
BUILD_SCHEMA = "fpvsim.build/1"
SPEC_SCHEMA = "fpvsim.spec/1"

_REQUIRED = {
    "motor": ("kv", "rm", "i0_ref", "v_i0_ref", "i0_speed_fraction", "rotor_inertia", "max_current"),
    "prop": ("diameter", "pitch", "spin_inertia"),
    "esc": ("r_on", "quiescent_power", "max_current"),
    "battery": ("capacity", "r0_cell", "r1_cell", "tau1", "c_rating"),
    "frame": ("thrust_interference",),
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
    misplaced = {"mass", "shape", "cg_offset"} & set(data.get("meta", {}))
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
            MassItem(p.name, p.group, p.mass_key, v(p.mass_key), p.position, p.shape, p.rotation) for p in self.parts
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
    for key, entry in table.items():
        params.add(parse_param(f"{role}.{key}", entry))
    if "mass" in data:
        params.add(parse_param(f"{role}.mass", data["mass"]))
    return data


def load_build(path: str | Path) -> Build:
    path = Path(path).resolve()
    data = _read_toml(path, BUILD_SCHEMA)
    base = path.parent
    meta = data.get("meta", {})
    params = ParamSet()
    files = [path]

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
    idle = data.get("flight_controller", {}).get("motor_idle")
    if idle is None:
        raise DesignError(f"{path}: [flight_controller] needs motor_idle")
    params.add(parse_param("flight_controller.motor_idle", idle))

    parts: list[PartTemplate] = []
    rotors = _frame_parts(component_files["frame"], comp["frame"], params, parts)
    _rotor_parts(comp, rotors, parts)
    model_inputs = ParamSet()
    tables: list[DataTable] = []
    prop_curves, prop_curve_source = _prop_curves(component_files["prop"], comp["prop"], params, model_inputs, tables)

    for i, entry in enumerate(data.get("parts", [])):
        parts.append(_build_part(path, base, i, entry, comp, params, files))
    for role in ("battery", "esc"):
        placed = sum(1 for p in parts if p.mass_key == f"{role}.mass")
        if placed != 1:
            raise DesignError(f"{path}: place the {role} exactly once with [[parts]] uses = {role!r} (found {placed})")

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
        params.add(parse_param(key, entry.get("mass")))
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
    position = parse_vector(f"{where}.position", entry.get("position"))
    rotation = _rotation(where, entry.get("rotation_deg"))
    power_key = None

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
        params.add(parse_param(mass_key, data["mass"]))
        for key, value in data.get("params", {}).items():
            params.add(parse_param(f"{name}.{key}", value))
        if f"{name}.power" in params:
            power_key = f"{name}.power"
        shape = _parse_shape(str(comp_path), data.get("shape"))
        group = entry.get("group", data.get("meta", {}).get("category", "avionics"))
    else:  # inline part
        mass_key = f"{name}.mass"
        params.add(parse_param(mass_key, entry.get("mass")))
        shape = _parse_shape(where, entry.get("shape"))
        group = entry.get("group", "misc")

    return PartTemplate(name, str(group), mass_key, shape, position, rotation, power_key)


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
