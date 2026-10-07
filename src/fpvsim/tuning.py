"""Stage 5: a tuning session, the way it is done on a real quad.

1. Noise survey: a throttle sweep is flown and logged at the PID-loop rate.
   The raw gyro spectrum against throttle shows where motor noise lives; the
   filtered gyro, D-term and motor-output noise show what gets through. The
   same flight is repeated with filter variants (RPM filter off; lighter
   low-pass filters) to quantify the noise / delay trade-off.
2. Gain sweep: the tuning flight (stick snaps) is flown with P and D scaled
   by a grid of multipliers. For each, the step response is recovered from
   the log by deconvolution, and its quality is set against motor-output
   noise (heat and wasted power).
3. Recommendation: among candidates whose roll/pitch overshoot is within the
   limit and whose motor noise is at most a set multiple of the baseline's,
   the one with the lowest roll/pitch tracking error on the same scripted
   flight; the rule is printed with the result.

Flights run in parallel processes; every flight uses the same seed, so the
candidates differ only in their settings.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from . import flightanalysis as fa
from .design import load_build
from .filters import chain_response, group_delay, make_lowpass
from .flightcontroller import FcConfig, FilterSpec
from .pilot import MANEUVERS, Maneuver, Segment
from .sim import SimSettings, simulate

AXES = ("roll", "pitch", "yaw")
NOISE_BAND = (100.0, 1000.0)  # Hz
OVERSHOOT_LIMIT = 0.15  # our design target for the step-response peak, not an industry standard
NOISE_FACTOR_LIMIT = 1.5


NOISE_RAMP = 2.5  # s, level throttle ramp at the end of the sweep flight


def sweep_maneuver() -> tuple[Maneuver, tuple[float, float]]:
    """Shorter tuning flight for sweeps: two amplitudes per axis, then a calm
    level throttle ramp. Returns the maneuver and the noise window: noise is
    measured only during the ramp, because stick snaps put real (wanted)
    signal into the same frequency band."""
    segments, t = [], 1.0
    for axis in AXES:
        for amp in (0.5, 1.0):
            for sign in (1.0, -1.0):
                segments.append(Segment(t, t + 0.15, {axis: sign * amp}))
                t += 0.75
        t += 0.4
    t += 0.6
    segments.append(Segment(t, t + NOISE_RAMP, {"throttle": (0.2, 0.7)}))
    maneuver = Maneuver("tune_short", "調參飛行（掃描用）：三軸、兩種幅度的正反向打桿，最後平飛油門爬升量測雜訊", t + NOISE_RAMP, tuple(segments))
    return maneuver, (t + 0.3, t + NOISE_RAMP)


def filter_delay(specs: tuple[FilterSpec, ...], fs: float, f: float = 50.0) -> float:
    """Group delay (s) of a low-pass chain at frequency f."""
    if not specs:
        return 0.0
    freqs = np.array([0.9 * f, f, 1.1 * f])
    h = chain_response([make_lowpass(s.kind, s.cutoff, fs) for s in specs], freqs, fs)
    return float(group_delay(h, freqs)[1])


def flight_metrics(log, noise_window: tuple[float, float] | None = None) -> dict:
    """Step response and tracking over the whole flight; noise (gyro,
    D-term, motor output in NOISE_BAND) only inside ``noise_window``."""
    fs = log.rate
    t = log.time
    quiet = (t >= noise_window[0]) & (t < noise_window[1]) if noise_window else np.ones(len(t), dtype=bool)
    out: dict = {"axes": {}}
    for axis in AXES:
        sp, gy = log[f"setpoint_{axis}"], log[f"gyro_{axis}"]
        sr = fa.step_response(sp, gy, fs)
        metrics = fa.step_metrics(sr.t, sr.mean) if sr else {}
        out["axes"][axis] = {
            "step": (sr.t.tolist(), sr.mean.tolist(), sr.std.tolist(), sr.segments) if sr else None,
            **metrics,
            "tracking_rms": fa.tracking_rms(sp, gy),
            "latency": fa.latency(sp, gy, fs),
            "dterm_noise": fa.band_rms(log[f"d_{axis}"][quiet], fs, *NOISE_BAND),
            "gyro_noise": fa.band_rms(gy[quiet], fs, *NOISE_BAND),
            "gyro_raw_noise": fa.band_rms(log[f"gyro_raw_{axis}"][quiet], fs, *NOISE_BAND),
        }
    motors = [k for k in log.columns if k.startswith("motor_") and not k.startswith("motor_current")]
    out["motor_noise"] = float(np.mean([fa.band_rms(log[m][quiet], fs, *NOISE_BAND) for m in motors]))
    out["saturation"] = float(log["saturated"].mean())
    out["crashed"] = bool(log.meta.get("crashed"))
    rp = [out["axes"][a] for a in ("roll", "pitch")]
    out["overshoot_rp"] = float(np.mean([a.get("overshoot", math.nan) for a in rp]))
    out["settling_rp"] = float(np.mean([a.get("settling_time", math.nan) for a in rp]))
    out["tracking_rp"] = float(np.mean([a["tracking_rms"] for a in rp]))
    return out


def _fly(job: dict) -> dict:
    build = load_build(job["build"])
    log = simulate(build, job["cfg"], job["maneuver"], SimSettings(log_rate=job["log_rate"], seed=job["seed"]))
    result = {"label": job["label"], "metrics": flight_metrics(log, job.get("noise_window"))}
    if job.get("keep_log"):
        result["log"] = log
    return result


def _run(jobs: list[dict], workers: int | None) -> list[dict]:
    workers = workers or min(len(jobs), os.cpu_count() or 1)
    if workers <= 1:
        return [_fly(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_fly, jobs))


@dataclass
class Candidate:
    label: str
    pd: float
    d: float
    cfg: FcConfig
    metrics: dict = field(default_factory=dict)
    feasible: bool = False


@dataclass
class TuningStudy:
    baseline: FcConfig
    noise_runs: list[dict]  # label, cfg, metrics, log
    candidates: list[Candidate]
    recommended: Candidate | None
    rule: str
    seed: int
    pd_values: tuple[float, ...] = ()
    d_values: tuple[float, ...] = ()
    baseline_log: object = None  # the baseline candidate's tuning-flight log

    @property
    def at_grid_edge(self) -> list[str]:
        """Which multipliers of the recommendation sit on the sweep boundary."""
        if self.recommended is None:
            return []
        edges = []
        if len(self.pd_values) > 1 and self.recommended.pd in (min(self.pd_values), max(self.pd_values)):
            edges.append("PD")
        if len(self.d_values) > 1 and self.recommended.d in (min(self.d_values), max(self.d_values)):
            edges.append("D")
        return edges


def select(candidates: list[Candidate]) -> tuple[Candidate | None, str]:
    """Mark feasible candidates and pick the recommendation (see module docstring)."""
    base = next((c for c in candidates if c.pd == 1.0 and c.d == 1.0), candidates[len(candidates) // 2])
    noise_cap = NOISE_FACTOR_LIMIT * base.metrics["motor_noise"]
    for c in candidates:
        m = c.metrics
        c.feasible = (
            not m["crashed"]
            and math.isfinite(m["overshoot_rp"])
            and m["overshoot_rp"] <= OVERSHOOT_LIMIT
            and m["motor_noise"] <= noise_cap
        )
    feasible = [c for c in candidates if c.feasible]
    recommended = min(feasible, key=lambda c: c.metrics["tracking_rp"]) if feasible else None
    rule = (
        f"滾轉與俯仰的平均超調 ≤ {OVERSHOOT_LIMIT:.0%}（本專案的設計目標，不是業界標準），"
        f"且馬達輸出雜訊（{NOISE_BAND[0]:.0f}–{NOISE_BAND[1]:.0f} Hz RMS）不超過基準設定的 {NOISE_FACTOR_LIMIT:g} 倍；"
        "符合條件者中，取同一段調參飛行中滾轉與俯仰追蹤誤差 (RMS) 最小的。"
        "排序不用安定時間，因為由飛行數據反卷積得到的步階響應有漣波，安定時間對它很敏感。"
    )
    return recommended, rule


def filter_variants(cfg: FcConfig) -> list[tuple[str, str, FcConfig]]:
    """(Chinese label, English chart label, config) for the noise survey."""
    lighter = replace(
        cfg,
        gyro_lowpass=tuple(FilterSpec(s.kind, min(1.6 * s.cutoff, 0.45 * cfg.pid_rate)) for s in cfg.gyro_lowpass),
        dterm_lowpass=tuple(FilterSpec(s.kind, min(1.3 * s.cutoff, 0.45 * cfg.pid_rate)) for s in cfg.dterm_lowpass),
    )
    return [
        ("基準設定", "baseline", cfg),
        ("關閉 RPM 濾波", "RPM filter off", cfg.without_rpm_filter()),
        ("RPM 濾波 + 較輕的低通", "RPM filter + lighter low-pass", lighter),
    ]


def run_study(
    build_path: str | Path,
    cfg: FcConfig,
    pd_values=(0.7, 0.85, 1.0, 1.15, 1.3),
    d_values=(0.8, 1.0, 1.25),
    seed: int = 1,
    workers: int | None = None,
) -> TuningStudy:
    build_path = str(Path(build_path).resolve())
    sweep = MANEUVERS["throttle_sweep"]
    noise_jobs = [
        {"build": build_path, "cfg": c, "maneuver": sweep, "log_rate": cfg.pid_rate, "seed": seed, "label": label,
         "keep_log": True, "noise_window": (1.0, 5.0)}
        for label, _, c in filter_variants(cfg)
    ]
    candidates = [
        Candidate(f"PD×{pd:g} D×{d:g}", pd, d, cfg.with_gains(pd=pd, d=d)) for pd in pd_values for d in d_values
    ]
    tune, window = sweep_maneuver()
    gain_jobs = [
        {"build": build_path, "cfg": c.cfg, "maneuver": tune, "log_rate": 2000.0, "seed": seed, "label": c.label,
         "noise_window": window, "keep_log": c.pd == 1.0 and c.d == 1.0}
        for c in candidates
    ]
    results = _run(noise_jobs + gain_jobs, workers)
    noise_runs = []
    for (label, label_en, c), res in zip(filter_variants(cfg), results[: len(noise_jobs)]):
        noise_runs.append({"label": label, "label_en": label_en, "cfg": c, "metrics": res["metrics"], "log": res["log"]})
    baseline_log = None
    for cand, res in zip(candidates, results[len(noise_jobs) :]):
        cand.metrics = res["metrics"]
        baseline_log = res.get("log", baseline_log)

    recommended, rule = select(candidates)
    return TuningStudy(cfg, noise_runs, candidates, recommended, rule, seed, tuple(pd_values), tuple(d_values), baseline_log)
