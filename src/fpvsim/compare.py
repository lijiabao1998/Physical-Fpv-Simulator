"""Stage 7: design iteration, comparing design versions.

Every version goes through the same pipeline with the same settings:

* the design change list (what was added, removed, moved or re-valued),
* static analysis and requirement compliance with paired Monte Carlo:
  sample i of every version uses the same value for every physical item the
  versions share (see ParamSet.sample), so the *difference* between versions
  is sampled directly instead of as the difference of two noisy runs. Shared
  inputs still set how large the effect of a change is (a heavier quad costs
  more endurance with a less efficient prop), so they still contribute to
  the spread of the difference; delta_sensitivity shows which inputs do;
* the same flight-test maneuver with the same seed and the same FC settings,
* a tuning study per version: how the baseline gains behave on the new
  airframe, and which gains the sweep recommends for it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import flightanalysis as fa
from .blackbox import FlightLog
from .design import Build, PartTemplate, load_build
from .flightcontroller import FcConfig
from .performance import EnduranceResult, evaluate, hover_endurance
from .pilot import MANEUVERS, Maneuver
from .sim import SimSettings, simulate
from .tuning import TuningStudy, run_study
from .uncertainty import MonteCarloResult, monte_carlo

COMPARE_METRICS = (
    "auw",
    "cg_offset",
    "thrust_to_weight",
    "hover_duty",
    "hover_current",
    "hover_efficiency",
    "endurance",
    "peak_current",
    "full_throttle_cell_voltage",
    "disk_loading",
)


@dataclass(frozen=True)
class Change:
    kind: str  # added, removed, moved, replaced, component, value
    item: str
    before: str
    after: str


@dataclass
class VersionResult:
    build: Build
    nominal: dict[str, float]
    mc: MonteCarloResult
    compliance: dict[str, float]
    endurance: EnduranceResult
    flight: FlightLog | None = None
    flight_summary: dict = field(default_factory=dict)
    tuning: TuningStudy | None = None


@dataclass
class Comparison:
    versions: list[VersionResult]  # base first
    fc: FcConfig
    seed: int
    samples: int
    maneuver: Maneuver | None
    changes: list[list[Change]]  # per non-base version, against the base
    code_version: str = ""  # git commit when the analysis started
    sensitivity: list[dict] = field(default_factory=list)  # per non-base version: metric -> [DeltaBar]
    clearance: list = field(default_factory=list)  # per version: worst prop-clearance pair at nominal (or None)
    clearance_failures: list = field(default_factory=list)  # per version: {part: samples where it breaks the rule}

    @property
    def base(self) -> VersionResult:
        return self.versions[0]

    def delta(self, index: int, metric: str) -> np.ndarray:
        """Paired per-sample difference, version ``index`` minus the base."""
        return self.versions[index].mc.outputs[metric] - self.base.mc.outputs[metric]

    def relative_delta(self, index: int, metric: str) -> np.ndarray:
        base = self.base.mc.outputs[metric]
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.delta(index, metric) / np.abs(base)


def _fmt_shape(shape) -> str:
    from .mass import BoxShape, CylinderShape

    if isinstance(shape, BoxShape):
        return f"方塊 {1000 * shape.lx:.0f}×{1000 * shape.ly:.0f}×{1000 * shape.lz:.0f} mm"
    if isinstance(shape, CylinderShape):
        return f"圓柱 直徑 {2000 * shape.radius:.0f} mm × 高 {1000 * shape.height:.0f} mm"
    return "質點"


def _fmt_vec(v: np.ndarray) -> str:
    return "(" + ", ".join(f"{1000 * x:.1f}" for x in v) + ") mm"


def _fmt_param(p) -> str:
    text = f"{p.display_value:.4g}"
    if p.uncertain:
        text += f" ± {p.display_u:.3g}"
    return f"{text} {p.unit}（{p.source.label_zh}）"


def design_changes(base: Build, variant: Build) -> list[Change]:
    """What differs between two builds: parts, component files, the spec and
    every parameter (value, uncertainty, source), including parameters that
    exist in only one of them."""
    def by_name(parts: list[PartTemplate]) -> dict[str, PartTemplate]:
        return {p.name: p for p in parts}

    changes: list[Change] = []
    bp, vp = by_name(base.parts), by_name(variant.parts)
    added, removed = vp.keys() - bp.keys(), bp.keys() - vp.keys()
    for name in added:
        part = vp[name]
        changes.append(Change("added", name, "—", f"{variant.params[part.mass_key].display_value:.4g} "
                              f"{variant.params[part.mass_key].unit} @ {_fmt_vec(part.position)}"))
    for name in removed:
        changes.append(Change("removed", name, _fmt_vec(bp[name].position), "—"))
    for name in bp.keys() & vp.keys():
        a, b = bp[name], vp[name]
        if not np.allclose(a.position, b.position) or not np.allclose(a.rotation, b.rotation):
            changes.append(Change("moved", name, _fmt_vec(a.position), _fmt_vec(b.position)))
        if a.component_id != b.component_id:  # a part made from another (or edited) component file
            changes.append(Change("component", name, a.component or "行內零件", b.component or "行內零件"))
        elif a.mass_key != b.mass_key or type(a.shape) is not type(b.shape) or a.shape != b.shape:
            changes.append(Change("replaced", name, _fmt_shape(a.shape), _fmt_shape(b.shape)))
        if a.mounted_on != b.mounted_on:
            changes.append(Change("mount", name, a.mounted_on or "機架", b.mounted_on or "機架"))
    for role, path in variant.component_files.items():
        if base.component_files.get(role) != path:
            changes.append(Change("component", role, base.component_files[role].name, path.name))
    if base.spec.id != variant.spec.id:
        changes.append(Change("spec", "spec", base.spec.id, variant.spec.id))

    def owner(key: str) -> str:
        return key.split(".", 1)[0]

    bk, vk = set(base.params.params), set(variant.params.params)
    for key in sorted(vk - bk):
        if owner(key) not in added:  # parameters of an added part are covered by its row
            changes.append(Change("param_added", key, "—", _fmt_param(variant.params[key])))
    for key in sorted(bk - vk):
        if owner(key) not in removed:
            changes.append(Change("param_removed", key, _fmt_param(base.params[key]), "—"))
    for key in sorted(bk & vk):
        a, b = base.params[key], variant.params[key]
        if (a.value, a.u, a.dist, a.source) != (b.value, b.u, b.dist, b.source):
            changes.append(Change("value", key, _fmt_param(a), _fmt_param(b)))
    order = {"component": 0, "spec": 1, "added": 2, "removed": 3, "moved": 4, "replaced": 5, "mount": 6,
             "param_added": 7, "param_removed": 8, "value": 9}
    return sorted(changes, key=lambda c: (order[c.kind], c.item))


def _clearance_failures(v: VersionResult) -> dict[str, int]:
    """Which part is the worst one in each Monte Carlo sample that breaks
    the prop-clearance rule (re-realised from the stored sample inputs)."""
    from .geometry import clearance_margin

    margin = v.mc.outputs.get("prop_clearance")
    if margin is None:
        return {}
    counts: dict[str, int] = {}
    for i in np.nonzero(margin < 0.0)[0]:
        worst = clearance_margin(v.build.realize({k: x[i] for k, x in v.mc.inputs.items()}))
        if worst is not None:
            counts[worst.part] = counts.get(worst.part, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def forward_drag_split(ac, speed: float) -> tuple[float, float]:
    """(rotor drag, body drag) in N at ``speed`` m/s of level forward flight,
    rotors at hover speed: a first-order split of what sets the cruise tilt
    (tan(tilt) ~ drag / weight)."""
    from .dynamics import QuadModel

    m = QuadModel(ac, ac.extras)
    rotor = m.n * m.k_rotor_drag * m.hover_omega * speed
    cda_x = ac.extras.cda[0] + sum(areas[0] for _, areas in ac.extras.drag_points)
    return rotor, 0.5 * ac.env.rho * speed * speed * cda_x


def _window(log: FlightLog, t0: float, t1: float) -> np.ndarray:
    t = log.time
    return (t >= t0) & (t < t1)


def flight_summary(log: FlightLog, maneuver: Maneuver | None, cells: int) -> dict:
    """Headline numbers of a flight, plus per-element numbers for the
    freestyle maneuver (forward flight, punch-out, flips)."""
    speed = np.sqrt(log["vel_n"] ** 2 + log["vel_e"] ** 2 + log["vel_d"] ** 2)
    out = {
        "max_speed": float(speed.max()),
        "max_climb": float((-log["vel_d"]).max()),
        "min_cell_voltage": float(log["vbat"].min() / cells),
        "peak_current": float(log["current"].max()),
        "mah": float(log["mah"][-1]),
        "tracking_roll": fa.tracking_rms(log["setpoint_roll"], log["gyro_roll"]),
        "tracking_pitch": fa.tracking_rms(log["setpoint_pitch"], log["gyro_pitch"]),
        "saturation": float(log["saturated"].mean()),
        "crashed": bool(log.meta.get("crashed")),
    }
    if maneuver is None:
        return out
    alt = log["alt"]
    for seg in maneuver.segments:
        if not seg.tag or seg.end > log.time[-1]:  # untagged, or the log stops before it ends
            continue
        if seg.tag == "forward":  # last second of the forward-flight segment, quasi-steady
            w = _window(log, seg.end - 1.0, seg.end)
            out["forward_speed"] = float(np.mean(np.hypot(log["vel_n"][w], log["vel_e"][w])))
            out["forward_pitch"] = float(np.mean(-log["att_pitch"][w]))
        elif seg.tag == "punch":
            w = _window(log, seg.start, seg.start + 2.0)
            out["punch_alt_gain"] = float(alt[w].max() - alt[w][0])
        elif seg.tag in ("flip", "backflip"):
            w = _window(log, seg.start, seg.end + 1.5)
            out[f"{seg.tag}_alt_loss"] = float(alt[w][0] - alt[w].min())
        elif seg.tag == "yaw_spin":
            w = _window(log, seg.start + 0.3, seg.end)
            out["yaw_rate"] = float(np.mean(log["rate_yaw"][w]))
    return out


def analyse_version(build: Build, samples: int, seed: int) -> VersionResult:
    ac = build.realize()
    mc = monte_carlo(build, n=samples, seed=seed)
    return VersionResult(
        build=build,
        nominal=evaluate(ac),
        mc=mc,
        compliance={r.id: mc.probability_of_compliance(r) for r in build.spec.requirements},
        endurance=hover_endurance(ac),
    )


@dataclass(frozen=True)
class DeltaBar:
    """Effect of one input on a version difference: delta at input -1 sigma
    and +1 sigma (others nominal), and which version(s) the input belongs to."""

    key: str
    scope: str  # "shared", "base" or "variant"
    low: float
    high: float
    nominal: float = math.nan  # the difference with every input nominal

    @property
    def span(self) -> float:
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            return math.inf
        return abs(self.high - self.low)

    @property
    def effect(self) -> float:
        """Largest one-sided change of the difference (inputs can act one-sidedly,
        e.g. a placement error that moves the CG away from the centre either way)."""
        if not math.isfinite(self.nominal):
            return self.span / 2
        changes = [abs(x - self.nominal) for x in (self.low, self.high)]
        return math.inf if not all(map(math.isfinite, changes)) else max(changes)


def delta_sensitivity(base: Build, variant: Build, metrics: tuple[str, ...]) -> dict[str, list[DeltaBar]]:
    """One-at-a-time +/-1 sigma sensitivity of (variant - base) for each metric.

    Inputs are grouped by random stream, exactly as the paired Monte Carlo
    couples them: every parameter on one stream (the same physical item, in
    one build or both) moves together; a stream found in both builds is
    "shared", otherwise it belongs to the build it appears in."""
    def delta(over_base: dict, over_var: dict) -> dict[str, float]:
        vb, vv = evaluate(base.realize(over_base)), evaluate(variant.realize(over_var))
        return {m: vv[m] - vb[m] for m in metrics}

    groups: dict[str, tuple[list, list]] = {}
    for p in base.params:
        if p.uncertain:
            groups.setdefault(p.stream or p.key, ([], []))[0].append(p)
    for p in variant.params:
        if p.uncertain:
            groups.setdefault(p.stream or p.key, ([], []))[1].append(p)
    bars: dict[str, list[DeltaBar]] = {m: [] for m in metrics}
    nominal = delta({}, {})
    for in_base, in_var in groups.values():
        scope = "shared" if in_base and in_var else ("base" if in_base else "variant")
        key = " + ".join(sorted({p.key for p in in_base + in_var}))
        lo = delta({p.key: p.value - p.u for p in in_base}, {p.key: p.value - p.u for p in in_var})
        hi = delta({p.key: p.value + p.u for p in in_base}, {p.key: p.value + p.u for p in in_var})
        for m in metrics:
            bars[m].append(DeltaBar(key, scope, lo[m], hi[m], nominal[m]))
    for m in metrics:
        bars[m].sort(key=lambda b: (-b.effect, b.key))
    return bars


def _spec_signature(build: Build) -> tuple:
    reqs = tuple(sorted((r.id, r.metric, r.kind, round(r.limit, 12), r.unit) for r in build.spec.requirements))
    conditions = tuple(round(build.params[k].value, 12) for k in
                       ("env.altitude", "env.temperature", "criteria.reserve_soc", "criteria.min_cell_voltage"))
    return reqs, conditions


SENSITIVITY_METRICS = ("endurance", "thrust_to_weight", "hover_current", "cg_offset")


def compare(
    build_paths: list[str | Path],
    fc: FcConfig,
    samples: int = 1000,
    seed: int = 1,
    maneuver: str | None = "freestyle",
    tune: bool = True,
    workers: int | None = None,
) -> Comparison:
    if len(build_paths) < 2:
        raise ValueError("compare needs a base build and at least one other version")
    from .geometry import clearance_margin
    from .report import git_version

    if maneuver and maneuver not in MANEUVERS:
        raise ValueError(f"unknown maneuver {maneuver!r}; known: {sorted(MANEUVERS)}")
    builds = [load_build(p) for p in build_paths]
    for b in builds[1:]:  # one yardstick for all versions
        if _spec_signature(b) != _spec_signature(builds[0]):
            raise ValueError(
                f"{b.id} is checked against a different spec ({b.spec.id}) than the base ({builds[0].spec.id}); "
                "compare versions under one spec, or compare each spec separately"
            )
    code_version = git_version(builds[0].path.parent)  # before the long run, not after it
    versions = [analyse_version(b, samples, seed) for b in builds]
    man = MANEUVERS[maneuver] if maneuver else None
    for path, v in zip(build_paths, versions):
        if man is not None:
            v.flight = simulate(v.build, fc, man, SimSettings(log_rate=1000.0, seed=seed))
            v.flight_summary = flight_summary(v.flight, man, v.build.battery_series)
        if tune:
            v.tuning = run_study(path, fc, seed=seed, workers=workers)
    changes = [design_changes(builds[0], b) for b in builds[1:]]
    sensitivity = [delta_sensitivity(builds[0], b, SENSITIVITY_METRICS) for b in builds[1:]]
    clearance = [clearance_margin(b.realize()) for b in builds]
    clearance_failures = [_clearance_failures(v) for v in versions]
    return Comparison(versions, fc, seed, samples, man, changes, code_version, sensitivity, clearance, clearance_failures)


def summarise_delta(values: np.ndarray) -> tuple[float, float, float]:
    """P5, P50, P95 of finite values."""
    finite = values[np.isfinite(values)]
    if not len(finite):
        return (math.nan, math.nan, math.nan)
    return tuple(float(x) for x in np.percentile(finite, (5, 50, 95)))
