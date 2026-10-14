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
the altitude hold drifts as the voltage falls), and after each lap's script
it dives back down to the start altitude in forward flight before the next
lap begins (MissionPilot), so every lap starts at the same height.

Cost: the physics runs at 4 kHz (gyro and PID loop at 4 kHz too, a common
Betaflight setting) instead of 8 kHz, and the log at 50 Hz; a few minutes
of flight take a few minutes to compute.
"""

from __future__ import annotations

import math
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


RETURN_SPEED = 2.0  # return-flight airspeed / hover induced velocity v_h: the wake is blown away
RETURN_DESCENT = 1.0  # return descent rate / v_h at full return airspeed
SLOW_DESCENT = 0.4  # descent rate / v_h below an airspeed of v_h: under the vortex-ring monitor's 0.5, with margin
RETURN_GAIN = 0.4  # 1/s, descent rate per metre above the start altitude near the end of the return
RETURN_SLOWDOWN = 8.0  # m above the start altitude below which the return airspeed is brought down with the height
RETURN_TOLERANCE = 1.0  # m above the start altitude at which the next lap starts


class MissionPilot:
    """The test pilot over the maneuver, lap after lap, with a return flight in between.

    A punch-out leaves the aircraft about 50 m higher; repeated back to back,
    the laps would climb without end. A pilot dives back down, and does it in
    forward flight: a vertical descent at that rate would put the rotors in
    their own wake (vortex ring). So after each lap's script the mission pilot
    flies towards the start point at RETURN_SPEED v_h of airspeed (from the
    true mean wind, which a test pilot can feel) and descends at up to
    RETURN_DESCENT v_h once the airspeed is 1.5 v_h, SLOW_DESCENT v_h below an
    airspeed of v_h (where the vortex-ring monitor looks), linear in between; over the last RETURN_SLOWDOWN metres it slows down in
    both directions together (no hard braking, which would put air through the
    disks from below); the next lap starts
    within RETURN_TOLERANCE of the start altitude, with the hover throttle
    re-estimated for the battery's state. The return direction is fixed when
    the return starts. Lap length therefore varies with the climb to undo."""

    def __init__(self, inner: TestPilot, ac, n: int, start_altitude: float, max_laps: int,
                 wind: WindSettings = WindSettings()):
        self.inner = inner
        self.ac = ac
        self.n = n
        self.script = inner.maneuver.duration
        self.name = inner.maneuver.name
        self.max_laps = max_laps
        self.duration = max_laps * (self.script + 120.0)  # time limit; the mission ends on max_laps first
        self.base = start_altitude
        self.wind = wind
        prop = ac.powertrain.prop
        self.v_h = math.sqrt(ac.weight / (n * 2.0 * ac.env.rho * prop.disk_area))
        self.lap_starts: list[float] = []
        self.returning = False
        self._direction = (1.0, 0.0)
        self._start_lap(0.0, None)

    @property
    def laps_done(self) -> int:
        """Laps whose script and return are both complete."""
        return len(self.lap_starts) - 1

    def _start_lap(self, t: float, s) -> None:
        self.lap_starts.append(t)
        self.returning = False
        self.inner.command_velocity = None
        self._set_base_hold = s is not None
        if s is not None:
            n = self.n
            hp = hover_point(self.ac, BatteryState(s[13 + n], s[14 + n], s[15 + n]))
            if hp is not None:
                self.inner.hover_duty = hp.duty

    def sticks(self, t: float, s: list[float], dt: float):
        altitude = -s[2]
        tau = t - self.lap_starts[-1]
        if not self.returning and tau >= self.script:
            self.returning = True
            d = math.hypot(s[0], s[1])
            self._direction = (-s[0] / d, -s[1] / d) if d > 5.0 else (-1.0, 0.0)  # towards the start point
        if self.returning:
            gap = altitude - self.base
            if gap <= RETURN_TOLERANCE:
                self._start_lap(t, s)
                tau = 0.0
            else:
                wn, we, _ = self.wind.mean_ned(max(altitude, 0.0))
                airspeed = math.hypot(s[3] - wn, s[4] - we)
                fast = min(max((airspeed - self.v_h) / (0.5 * self.v_h), 0.0), 1.0)
                allowed = (SLOW_DESCENT + (RETURN_DESCENT - SLOW_DESCENT) * fast) * self.v_h
                v = RETURN_SPEED * self.v_h * min(1.0, gap / RETURN_SLOWDOWN)
                self.inner.command_velocity = (wn + v * self._direction[0], we + v * self._direction[1],
                                               min(allowed, RETURN_GAIN * gap))
                sticks = self.inner.sticks(self.script, s, dt)  # past the script: no segment is active
                hold = self.inner.hold
                self.inner.hold = (hold[0], hold[1], s[2])  # vertical speed control only
                return sticks
        sticks = self.inner.sticks(tau, s, dt)
        hold = self.inner.hold
        if self._set_base_hold:  # a new lap: hold the start altitude (at most RETURN_TOLERANCE below)
            self.inner.hold = (hold[0], hold[1], -self.base)
            self._set_base_hold = False
        elif s[5] < 0.0 and s[2] < hold[2] and not any(seg.sticks or seg.velocity for seg in self.inner.maneuver.active(tau)):
            # still coasting up after a punch-out: hold the top of the climb, not the point where the script let go
            # (pulling back down to it would be a fast vertical descent into the rotors' own wake)
            self.inner.hold = (hold[0], hold[1], s[2])
        return sticks


@dataclass
class MissionResult:
    log: FlightLog
    time: float  # s
    laps: float  # completed laps (fractional)
    reason: str
    lap_duration: float  # s, the scripted part of a lap
    lap_starts: list[float]  # s, start time of each lap (script, then the return flight)
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
    cfg = replace(cfg, gyro_rate=min(cfg.gyro_rate, physics_rate), pid_rate=min(cfg.pid_rate, physics_rate))
    ac = build.realize(overrides)
    hp = hover_point(ac)
    if hp is None:
        raise ValueError("the aircraft cannot hover")
    n = ac.powertrain.n_rotors
    pilot = MissionPilot(TestPilot(cfg, base, ac.mass_props.mass, ac.env.g, hp.duty, ac.motor_idle), ac, n,
                         start_altitude, max_laps, wind)
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
        if pilot.laps_done >= max_laps:
            return "max_laps"
        return None

    settings = SimSettings(physics_rate=physics_rate, log_rate=log_rate, seed=seed, start_altitude=start_altitude, wind=wind,
                           ground_effect=ground_effect)
    log = simulate(build, cfg, pilot, settings, overrides=overrides, stop=stop)
    time = float(log.time[-1]) if len(log.time) else 0.0
    reason = log.meta.get("stop") or ("crash" if log.meta.get("crashed") else "max_laps")
    starts = [t for t in pilot.lap_starts if t <= time]
    laps = len(starts) - 1 + min(1.0, (time - starts[-1]) / base.duration)
    return MissionResult(log, time, laps, reason, base.duration, starts, hover_endurance(ac).endurance, physics_rate)


def lap_table(result: MissionResult, cells: int) -> list[dict]:
    """Per lap (script and return flight): start time, length, charge used, average
    power, lowest 1 s average cell voltage, highest pack temperature, start altitude."""
    log = result.log
    t = log.time
    rows = []
    ends = result.lap_starts[1:] + [float("inf")]
    for k, (t0, t1) in enumerate(zip(result.lap_starts, ends)):
        sel = (t >= t0) & (t < t1)
        if sel.sum() < 2:
            break
        v = log["vbat"][sel] / cells
        width = max(1, int(round(log.rate)))
        avg = np.convolve(v, np.ones(width) / width, mode="valid") if len(v) >= width else v
        p = log["vbat"][sel] * log["current"][sel]
        complete = t1 != float("inf")
        rows.append({"lap": k + 1, "start": t0, "length": float((t1 if complete else t[-1]) - t0),
                     "mah": float(log["mah"][sel][-1] - log["mah"][sel][0]), "power": float(p.mean()),
                     "min_cell_avg": float(avg.min()), "max_temp": float(log["batt_temp"][sel].max()),
                     "start_alt": float(log["alt"][sel][0]), "max_alt": float(log["alt"][sel].max()), "complete": complete})
    return rows
