"""Mission endurance: fly a maneuver over and over until the battery is done.

The hover endurance of the design report is a lower bound on power and so
an upper bound on flight time; a freestyle pack is flown hard. Here the 6DOF
simulation repeats a maneuver (default ``freestyle``) lap after lap from a
full, rested pack until the first of

* the reserve state of charge (``criteria.reserve_soc``);
* the cell voltage, averaged over 1 s, below ``criteria.min_cell_voltage``
  (what a low-voltage warning on the OSD reacts to; the instantaneous dips
  of a punch-out are not counted);
* the pack temperature limit;
* a crash or ``max_laps``.

The test pilot adapts as a pilot does: at the start of each lap its hover
throttle estimate is recomputed from the battery's current state (otherwise
the altitude hold drifts as the voltage falls).

Cost: the physics runs at 4 kHz (gyro and PID loop at 4 kHz too, a common
Betaflight setting) instead of 8 kHz, and the log at 50 Hz; a few minutes
of flight take a few minutes to compute.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np

from .battery import BatteryState
from .blackbox import FlightLog
from .design import Build
from .flightcontroller import FcConfig
from .performance import hover_endurance, hover_point
from .pilot import MANEUVERS, Maneuver, Segment, TestPilot
from .sim import SimSettings, simulate
from .wind import WindSettings

REASONS_ZH = {
    "reserve_soc": "達到保留電量",
    "low_voltage": "單芯電壓（1 秒平均）達到下限",
    "battery_temperature": "電池溫度達到上限",
    "crash": "墜機",
    "max_laps": "達到圈數上限",
}


def repeated(maneuver: Maneuver, laps: int) -> Maneuver:
    segments = tuple(Segment(s.start + k * maneuver.duration, s.end + k * maneuver.duration, s.sticks, s.velocity, s.tag)
                     for k in range(laps) for s in maneuver.segments)
    return Maneuver(f"{maneuver.name}x{laps}", f"{maneuver.title}，重複 {laps} 圈", maneuver.duration * laps, segments)


class MissionPilot:
    """TestPilot over the repeated maneuver, re-estimating the hover throttle each lap."""

    def __init__(self, inner: TestPilot, ac, lap: float, n: int):
        self.inner = inner
        self.ac = ac
        self.lap = lap
        self.n = n
        self.duration = inner.maneuver.duration
        self.name = inner.maneuver.name
        self.laps_started = 0

    def sticks(self, t: float, s: list[float], dt: float):
        lap = int(t // self.lap)
        if lap >= self.laps_started:
            n = self.n
            hp = hover_point(self.ac, BatteryState(s[13 + n], s[14 + n], s[15 + n]))
            if hp is not None:
                self.inner.hover_duty = hp.duty
            self.laps_started = lap + 1
        return self.inner.sticks(t, s, dt)


@dataclass
class MissionResult:
    log: FlightLog
    time: float  # s
    laps: float  # completed laps (fractional)
    reason: str
    lap_duration: float
    hover_endurance: float  # s, design-report figure for comparison
    physics_rate: float

    @property
    def reason_zh(self) -> str:
        return REASONS_ZH[self.reason]


def fly_mission(build: Build, cfg: FcConfig, maneuver: str = "freestyle", max_laps: int = 60, seed: int = 1,
                physics_rate: float = 4000.0, log_rate: float = 50.0, overrides: Mapping[str, float] | None = None,
                wind: WindSettings = WindSettings(), start_altitude: float = 20.0,
                ground_effect: bool = True) -> MissionResult:
    base = MANEUVERS[maneuver]
    plan = repeated(base, max_laps)
    cfg = replace(cfg, gyro_rate=min(cfg.gyro_rate, physics_rate), pid_rate=min(cfg.pid_rate, physics_rate))
    ac = build.realize(overrides)
    hp = hover_point(ac)
    if hp is None:
        raise ValueError("the aircraft cannot hover")
    n = ac.powertrain.n_rotors
    pilot = MissionPilot(TestPilot(cfg, plan, ac.mass_props.mass, ac.env.g, hp.duty, ac.motor_idle), ac, base.duration, n)
    cells = ac.battery.series
    reserve, v_min, t_max = ac.criteria.reserve_soc, ac.criteria.min_cell_voltage, ac.battery.max_temperature
    window: deque[float] = deque(maxlen=max(1, int(round(log_rate))))  # 1 s of samples at the log rate

    def stop(t, s, out):
        window.append(out.v_bus / cells)
        if s[13 + n] <= reserve:
            return "reserve_soc"
        if len(window) == window.maxlen and sum(window) / len(window) <= v_min:
            return "low_voltage"
        if s[15 + n] >= t_max:
            return "battery_temperature"
        if out.on_ground and out.max_contact_speed > 3.0:
            return "crash"
        return None

    settings = SimSettings(physics_rate=physics_rate, log_rate=log_rate, seed=seed, start_altitude=start_altitude, wind=wind,
                           ground_effect=ground_effect)
    log = simulate(build, cfg, pilot, settings, overrides=overrides, stop=stop)
    time = float(log.time[-1]) if len(log.time) else 0.0
    reason = log.meta.get("stop") or ("crash" if log.meta.get("crashed") else "max_laps")
    return MissionResult(log, time, time / base.duration, reason, base.duration, hover_endurance(ac).endurance, physics_rate)


def lap_table(result: MissionResult, cells: int) -> list[dict]:
    """Per lap: start time, charge used, average power, lowest 1 s average cell voltage, highest pack temperature."""
    log = result.log
    t = log.time
    rows = []
    k = 0
    while k * result.lap_duration < t[-1]:
        t0, t1 = k * result.lap_duration, (k + 1) * result.lap_duration
        sel = (t >= t0) & (t < t1)
        if sel.sum() < 2:
            break
        v = log["vbat"][sel] / cells
        width = max(1, int(round(log.rate)))
        avg = np.convolve(v, np.ones(width) / width, mode="valid") if len(v) >= width else v
        p = log["vbat"][sel] * log["current"][sel]
        rows.append({"lap": k + 1, "start": t0, "mah": float(log["mah"][sel][-1] - log["mah"][sel][0]),
                     "power": float(p.mean()), "min_cell_avg": float(avg.min()), "max_temp": float(log["batt_temp"][sel].max()),
                     "complete": bool(t[-1] >= t1 - 1.0 / log.rate)})
        k += 1
    return rows
