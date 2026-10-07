"""Stage 7: design iteration, comparing design versions.

Every version goes through the same pipeline with the same settings:

* the design change list (what was added, removed, moved or re-valued),
* static analysis and requirement compliance with paired Monte Carlo:
  sample i of every version uses the same value for every parameter the
  versions share (see ParamSet.sample), so the *difference* between versions
  is sampled directly and its spread reflects only what actually changed;
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


def design_changes(base: Build, variant: Build) -> list[Change]:
    """What differs between two builds, part by part and parameter by parameter."""
    def by_name(parts: list[PartTemplate]) -> dict[str, PartTemplate]:
        return {p.name: p for p in parts}

    changes: list[Change] = []
    bp, vp = by_name(base.parts), by_name(variant.parts)
    for name in vp.keys() - bp.keys():
        part = vp[name]
        changes.append(Change("added", name, "—", f"{variant.params[part.mass_key].display_value:.4g} "
                              f"{variant.params[part.mass_key].unit} @ {_fmt_vec(part.position)}"))
    for name in bp.keys() - vp.keys():
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
    shared = set(base.params.params) & set(variant.params.params)
    for key in sorted(shared):
        a, b = base.params[key], variant.params[key]
        if (a.value, a.u, a.dist, a.source) != (b.value, b.u, b.dist, b.source):
            changes.append(Change("value", key, f"{a.display_value:.4g} {a.unit}", f"{b.display_value:.4g} {b.unit}"))
    order = {"component": 0, "added": 1, "removed": 2, "moved": 3, "replaced": 4, "value": 5}
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
        if seg.end > log.time[-1]:  # the log stops before this element ends
            continue
        if seg.velocity is not None:  # last second of the forward-flight segment, quasi-steady
            w = _window(log, seg.end - 1.0, seg.end)
            out["forward_speed"] = float(np.mean(np.hypot(log["vel_n"][w], log["vel_e"][w])))
            out["forward_pitch"] = float(np.mean(-log["att_pitch"][w]))
        elif seg.sticks.get("throttle") == 1.0:
            w = _window(log, seg.start, seg.start + 2.0)
            out["punch_alt_gain"] = float(alt[w].max() - alt[w][0])
        elif seg.sticks.get("roll") == 1.0 or seg.sticks.get("pitch") == -1.0:
            name = "flip" if "roll" in seg.sticks else "backflip"
            w = _window(log, seg.start, seg.end + 1.5)
            out[f"{name}_alt_loss"] = float(alt[w][0] - alt[w].min())
        elif seg.sticks.get("yaw") == 1.0:
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
    builds = [load_build(p) for p in build_paths]
    versions = [analyse_version(b, samples, seed) for b in builds]
    man = MANEUVERS[maneuver] if maneuver else None
    for path, v in zip(build_paths, versions):
        if man is not None:
            v.flight = simulate(v.build, fc, man, SimSettings(log_rate=1000.0, seed=seed))
            v.flight_summary = flight_summary(v.flight, man, v.build.battery_series)
        if tune:
            v.tuning = run_study(path, fc, seed=seed, workers=workers)
    changes = [design_changes(builds[0], b) for b in builds[1:]]
    return Comparison(versions, fc, seed, samples, man, changes)


def summarise_delta(values: np.ndarray) -> tuple[float, float, float]:
    """P5, P50, P95 of finite values."""
    finite = values[np.isfinite(values)]
    if not len(finite):
        return (math.nan, math.nan, math.nan)
    return tuple(float(x) for x in np.percentile(finite, (5, 50, 95)))
