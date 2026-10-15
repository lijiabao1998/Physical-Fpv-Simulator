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
RETURN_DESCENT = 1.0  # return descent rate / v_h at an airspeed of 1.5 v_h and above
SLOW_DESCENT = 0.4  # descent rate / v_h below an airspeed of v_h: under the vortex-ring monitor's 0.5, with margin
RETURN_GAIN = 0.8  # 1/s, descent rate per metre above the start altitude near the end of the return
RETURN_SLOWDOWN = 8.0  # m above the start altitude at which the pilot starts braking
RETURN_TOLERANCE = 1.0  # m above the start altitude within which the next lap may start
RETURN_ACCEL = 0.5  # g, rate at which the airspeed builds up (tilting into the air: the flow comes from above)
RETURN_BRAKE = 0.25  # g, braking: the disks tilt back, and about 0.25 of the airspeed then flows through them from below
RETURN_TURN = 0.4  # g, lateral acceleration of the turn onto the return heading
ARRIVAL_SPEED = 0.5  # airspeed / v_h at which the next lap starts


class MissionPilot:
    """The test pilot over the maneuver, lap after lap, with a return flight in between.

    A punch-out leaves the aircraft about 50 m higher; repeated back to back,
    the laps would climb without end. A pilot dives back down, and does it in
    forward flight: a vertical descent at that rate would put the rotors in
    their own wake (vortex ring), and so would hard braking, which tilts the
    disks against the oncoming air. So after each lap's script the mission
    pilot

    * turns onto the heading of the start point (fixed when the return
      starts) instead of braking through zero airspeed, at RETURN_TURN g of
      lateral acceleration, and builds the airspeed up to RETURN_SPEED v_h at
      RETURN_ACCEL g (airspeed from the true mean wind, which a test pilot
      can feel);
    * descends at up to RETURN_DESCENT v_h at an airspeed of 1.5 v_h and
      above, SLOW_DESCENT v_h below an airspeed of v_h (where the
      vortex-ring monitor looks), linear in between;
    * from RETURN_SLOWDOWN above the start altitude, brakes at RETURN_BRAKE g
      while it eases into the start altitude (RETURN_GAIN), with the descent
      rate reduced by the flow that braking itself puts through the tilted
      disks (RETURN_BRAKE times the airspeed), and starts the next lap within
      RETURN_TOLERANCE of the start altitude (climbing back first if the lap
      ended below it) at an airspeed of ARRIVAL_SPEED v_h, with the hover
      throttle re-estimated for the battery's state.

    Lap length therefore varies with the climb to undo."""

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
        self._arriving = False
        self._direction = (1.0, 0.0)
        self._air_cmd = (0.0, 0.0)  # commanded horizontal velocity relative to the air, m/s
        self._z_ref = -start_altitude  # m (NED), height target of the return flight
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

    def _steer(self, target: float, dt: float) -> tuple[float, float]:
        """Move the commanded air velocity towards ``target`` m/s along the return
        heading: turn at RETURN_TURN g, speed up at RETURN_ACCEL g, slow down at RETURN_BRAKE g."""
        g = self.ac.env.g
        ux, uy = self._air_cmd
        speed = math.hypot(ux, uy)
        dx, dy = self._direction
        if speed < 0.5:  # (almost) at rest in the air: no heading to turn, speed up along the return heading
            heading = math.atan2(dy, dx) if target > 0.0 else math.atan2(uy, ux)
        else:
            heading = math.atan2(uy, ux)
            if target > 0.0:
                error = (math.atan2(dy, dx) - heading + math.pi) % (2.0 * math.pi) - math.pi
                step = RETURN_TURN * g / speed * dt
                heading += max(-step, min(step, error))
        rate = RETURN_ACCEL if target > speed else RETURN_BRAKE
        speed += max(-rate * g * dt, min(rate * g * dt, target - speed))
        self._air_cmd = (speed * math.cos(heading), speed * math.sin(heading))
        return self._air_cmd

    def sticks(self, t: float, s: list[float], dt: float):
        altitude = -s[2]
        tau = t - self.lap_starts[-1]
        if not self.returning and tau >= self.script:
            self.returning = True
            self._arriving = False
            d = math.hypot(s[0], s[1])
            self._direction = (-s[0] / d, -s[1] / d) if d > 5.0 else (-1.0, 0.0)  # towards the start point
            wn, we, _ = self.wind.mean_ned(max(altitude, 0.0))
            self._air_cmd = (s[3] - wn, s[4] - we)  # from the air velocity it has now
            self._z_ref = s[2]
        if self.returning:
            gap = altitude - self.base
            wn, we, _ = self.wind.mean_ned(max(altitude, 0.0))
            airspeed = math.hypot(s[3] - wn, s[4] - we)
            self._arriving = self._arriving or gap <= RETURN_SLOWDOWN
            if self._arriving and abs(gap) <= RETURN_TOLERANCE and airspeed <= ARRIVAL_SPEED * self.v_h:
                self._start_lap(t, s)
                tau = 0.0
            else:
                ux, uy = self._steer(0.0 if self._arriving else RETURN_SPEED * self.v_h, dt)
                fast = min(max((airspeed - self.v_h) / (0.5 * self.v_h), 0.0), 1.0)
                allowed = (SLOW_DESCENT + (RETURN_DESCENT - SLOW_DESCENT) * fast) * self.v_h
                if self._arriving:
                    allowed = max(allowed - RETURN_BRAKE * airspeed, 0.0)
                # down to half the tolerance above the start altitude; a lap that ended below it climbs back
                # (a negative rate, at most RETURN_DESCENT v_h)
                rate = max(min(allowed, RETURN_GAIN * (gap - 0.5 * RETURN_TOLERANCE)), -RETURN_DESCENT * self.v_h)
                self.inner.command_velocity = (wn + ux, we + uy, rate)
                # height target moving at the commanded rate (at most 2 m from the aircraft): the pilot's
                # position term then removes a steady error of the rate, e.g. a throttle trim learnt
                # holding position in wind that no longer fits while drifting with the air
                self._z_ref = min(max(self._z_ref + rate * dt, s[2] - 2.0), s[2] + 2.0)
                hold = self.inner.hold
                if hold is not None:
                    self.inner.hold = (hold[0], hold[1], self._z_ref)
                return self.inner.sticks(self.script, s, dt)  # past the script: no segment is active
        sticks = self.inner.sticks(tau, s, dt)
        hold = self.inner.hold
        if self._set_base_hold:  # a new lap: hold the start altitude (at most RETURN_TOLERANCE away)
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
    reason: str
    lap_duration: float  # s, the scripted part of a lap
    lap_starts: list[float]  # s, start time of each lap (script, then the return flight)
    hover_endurance: float  # s, design-report figure for comparison
    physics_rate: float

    @property
    def reason_zh(self) -> str:
        return REASONS_ZH[self.reason]

    @property
    def laps_complete(self) -> int:
        """Laps whose script and return flight are both complete."""
        return len(self.lap_starts) - 1

    @property
    def partial(self) -> float:
        """s flown in the lap that was under way when the mission ended (0 if it ended between laps,
        or within a second of the start of the next one)."""
        flown = self.time - self.lap_starts[-1]
        return flown if flown >= 1.0 else 0.0

    @property
    def partial_fraction(self) -> float | None:
        """The unfinished lap as a fraction of the mean complete lap (None without a complete lap to compare)."""
        if self.partial == 0.0:
            return 0.0
        if self.laps_complete == 0:
            return None
        mean = (self.lap_starts[-1] - self.lap_starts[0]) / self.laps_complete
        return min(self.partial / mean, 0.99)

    @property
    def laps(self) -> float:
        """Laps flown: complete laps plus the unfinished one as a fraction of a mean lap
        (without a complete lap, the unfinished one is not counted)."""
        return self.laps_complete + (self.partial_fraction or 0.0)

    def laps_text(self) -> str:
        if self.partial <= 0.0:
            return f"{self.laps_complete} 圈"
        if self.partial_fraction is None:
            return f"第 1 圈未完成（飛了 {self.partial:.0f} s）"
        return f"{self.laps_complete} 圈完成，加第 {self.laps_complete + 1} 圈約 {self.partial_fraction:.0%}（以平均圈長計）"


def wake_sources(result: MissionResult, maneuver: Maneuver, flagged: np.ndarray) -> list[tuple[str, float]]:
    """Where the samples in ``flagged`` (a boolean per log sample, e.g. the vortex-ring
    monitor) fall: each scripted element from its start to the next element's start
    (by segment tag), the hover before the first element, and the return flights.
    Returns (tag, seconds) pairs; tag "" is the hover before the first element,
    "script" the untagged elements, "return" the return flights."""
    t = result.log.time
    dt = 1.0 / result.log.rate
    edges = [(0.0, "")] + [(seg.start, seg.tag or "script") for seg in sorted(maneuver.segments, key=lambda seg: seg.start)]
    totals: dict[str, float] = {}
    ends = result.lap_starts[1:] + [float("inf")]
    for t0, t1 in zip(result.lap_starts, ends):
        tau = t - t0
        in_lap = (t >= t0) & (t < t1)
        for k, (start, tag) in enumerate(edges):
            stop = edges[k + 1][0] if k + 1 < len(edges) else maneuver.duration
            sel = in_lap & (tau >= start) & (tau < stop)
            totals[tag] = totals.get(tag, 0.0) + float(np.count_nonzero(flagged & sel)) * dt
        totals["return"] = totals.get("return", 0.0) + float(np.count_nonzero(flagged & in_lap & (tau >= maneuver.duration))) * dt
    return list(totals.items())


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
    return MissionResult(log, time, reason, base.duration, starts, hover_endurance(ac).endurance, physics_rate)


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
