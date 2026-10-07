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
    clearance: list[list] = field(default_factory=list)  # per version: prop clearance problems

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
        if a.mass_key != b.mass_key or type(a.shape) is not type(b.shape) or a.shape != b.shape:
            changes.append(Change("replaced", name, a.mass_key, b.mass_key))
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
    order = {"component": 0, "spec": 1, "added": 2, "removed": 3, "moved": 4, "replaced": 5,
             "param_added": 6, "param_removed": 7, "value": 8}
    return sorted(changes, key=lambda c: (order[c.kind], c.item))


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

    @property
    def span(self) -> float:
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            return math.inf
        return abs(self.high - self.low)


def delta_sensitivity(base: Build, variant: Build, metrics: tuple[str, ...]) -> dict[str, list[DeltaBar]]:
    """One-at-a-time +/-1 sigma sensitivity of (variant - base) for each metric.

    A parameter that is the same physical item in both builds (same random
    stream) moves in both at once, as it does in the paired Monte Carlo;
    otherwise it moves only in the build it belongs to."""
    def delta(over_base: dict, over_var: dict) -> dict[str, float]:
        vb, vv = evaluate(base.realize(over_base)), evaluate(variant.realize(over_var))
        return {m: vv[m] - vb[m] for m in metrics}

    inputs = []
    for key in sorted(set(base.params.params) | set(variant.params.params)):
        pb, pv = base.params.params.get(key), variant.params.params.get(key)
        if pb is not None and pv is not None and pb.stream == pv.stream:
            if pb.uncertain:
                inputs.append((key, "shared", pb, pv))
            continue
        if pb is not None and pb.uncertain:
            inputs.append((key, "base", pb, None))
        if pv is not None and pv.uncertain:
            inputs.append((key, "variant", None, pv))
    bars: dict[str, list[DeltaBar]] = {m: [] for m in metrics}
    for key, scope, pb, pv in inputs:
        lo = delta({key: pb.value - pb.u} if pb else {}, {key: pv.value - pv.u} if pv else {})
        hi = delta({key: pb.value + pb.u} if pb else {}, {key: pv.value + pv.u} if pv else {})
        for m in metrics:
            bars[m].append(DeltaBar(key, scope, lo[m], hi[m]))
    for m in metrics:
        bars[m].sort(key=lambda b: b.span, reverse=True)
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
    from .geometry import prop_clearance
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
    clearance = [prop_clearance(b.realize()) for b in builds]
    return Comparison(versions, fc, seed, samples, man, changes, code_version, sensitivity, clearance)


def summarise_delta(values: np.ndarray) -> tuple[float, float, float]:
    """P5, P50, P95 of finite values."""
    finite = values[np.isfinite(values)]
    if not len(finite):
        return (math.nan, math.nan, math.nan)
    return tuple(float(x) for x in np.percentile(finite, (5, 50, 95)))
