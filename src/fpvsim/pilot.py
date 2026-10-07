"""Virtual test pilot and flight-test maneuvers.

The flight controller only knows acro (rate) mode, like a freestyle quad.
Someone has to hold the aircraft steady between test inputs; on a real test
day that is the pilot. ``TestPilot`` is an automated stand-in: it watches the
true state, holds position, altitude and heading, and between scripted inputs
moves the sticks the way a smooth pilot would. It is a test harness, not a
model of human behaviour, and it is not part of the aircraft being evaluated.

A maneuver is a list of segments. During a segment the listed sticks are
overridden (a value, or a linear ramp (start, end)); the other axes stay under
the pilot's control. A segment can also give a velocity to fly instead of
holding position. When an override ends, the pilot holds wherever the
aircraft is at that moment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .flightcontroller import FcConfig

AXES = ("roll", "pitch", "yaw", "throttle")


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    sticks: dict = field(default_factory=dict)  # axis -> value or (start, end) ramp
    velocity: tuple[float, float, float] | None = None  # NED, m/s

    def stick(self, axis: str, t: float) -> float | None:
        if axis not in self.sticks:
            return None
        value = self.sticks[axis]
        if isinstance(value, tuple):
            frac = (t - self.start) / (self.end - self.start)
            return value[0] + frac * (value[1] - value[0])
        return float(value)


@dataclass(frozen=True)
class Maneuver:
    name: str
    title: str
    duration: float
    segments: tuple[Segment, ...]

    def active(self, t: float) -> list[Segment]:
        return [s for s in self.segments if s.start <= t < s.end]


def _tune() -> Maneuver:
    """Stick snaps on each axis at three amplitudes, both directions: the input
    a pilot flies for step-response analysis."""
    segments, t = [], 1.0
    for axis in ("roll", "pitch", "yaw"):
        for amp in (0.4, 0.7, 1.0):
            for sign in (1.0, -1.0):
                segments.append(Segment(t, t + 0.15, {axis: sign * amp}))
                t += 0.75
        t += 0.5
    return Maneuver("tune", "調參飛行：三軸、三種幅度的正反向打桿", t + 1.0, tuple(segments))


def _throttle_sweep() -> Maneuver:
    segs = (
        Segment(1.0, 4.0, {"throttle": (0.05, 1.0)}),
        Segment(4.0, 5.0, {"throttle": (1.0, 0.05)}),
    )
    return Maneuver("throttle_sweep", "油門掃描：從低到全油門再收回，用於雜訊對轉速分析", 8.0, segs)


def _punch() -> Maneuver:
    segs = (
        Segment(1.0, 2.0, {"throttle": 1.0}),
        Segment(2.0, 2.7, {"throttle": 0.0}),
    )
    return Maneuver("punch", "全油門衝刺 1 秒後收油下墜，再改出", 6.0, segs)


def _flip() -> Maneuver:
    segs = (Segment(1.0, 1.6, {"roll": 1.0, "throttle": 0.2}),)
    return Maneuver("flip", "滾轉翻滾一圈後改出", 5.0, segs)


def _forward() -> Maneuver:
    segs = (Segment(1.0, 6.0, velocity=(15.0, 0.0, 0.0)),)
    return Maneuver("forward", "15 m/s 前飛 5 秒後煞停", 10.0, segs)


def _freestyle() -> Maneuver:
    # Flips come before the punch-out and after a pause, so each element starts
    # from a settled hover and its numbers are not mixed with the previous one.
    segs = (
        Segment(1.0, 5.0, velocity=(10.0, 0.0, 0.0)),
        Segment(7.0, 7.6, {"roll": 1.0, "throttle": 0.2}),
        Segment(9.0, 9.6, {"pitch": -1.0, "throttle": 0.2}),
        Segment(11.0, 12.0, {"yaw": 1.0}),
        Segment(13.0, 13.8, {"throttle": 1.0}),
        Segment(15.0, 15.6, {"throttle": 0.0}),
    )
    return Maneuver("freestyle", "綜合飛行：10 m/s 前飛、滾轉翻、後空翻、原地自轉、衝刺、收油下墜", 19.0, segs)


def _hover() -> Maneuver:
    return Maneuver("hover", "定點懸停", 5.0, ())


MANEUVERS = {m.name: m for m in (_hover(), _tune(), _throttle_sweep(), _punch(), _flip(), _forward(), _freestyle())}


def inverse_rate_table(rates, points: int = 801) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(-1.0, 1.0, points)
    return np.array([rates.rate(v) for v in x]), x


def _quat_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _quat_from_euler(roll: float, pitch: float, yaw: float):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    )


class TestPilot:
    MAX_TILT = math.radians(40.0)
    ATTITUDE_GAIN = 7.0  # rad/s per rad
    MAX_RATE = math.radians(400.0)

    def __init__(self, cfg: FcConfig, maneuver: Maneuver, mass: float, g: float, hover_duty: float, idle: float):
        self.maneuver = maneuver
        self.mass, self.g = mass, g
        self.hover_duty, self.idle = hover_duty, idle
        self.tables = [inverse_rate_table(r) for r in cfg.rates]
        self.hold = None  # position target
        self.heading = 0.0
        self.alt_integral = 0.0
        self.vel_integral = [0.0, 0.0]  # m/s^2, removes the steady speed error against drag
        self._was_overridden = False

    def _stick_for_rate(self, axis: int, rate_rad: float) -> float:
        rates, x = self.tables[axis]
        return float(np.interp(math.degrees(rate_rad), rates, x))

    def sticks(self, t: float, s: list[float], dt: float) -> tuple[float, float, float, float]:
        active = self.maneuver.active(t)
        overridden = any(seg.sticks or seg.velocity for seg in active)
        if self.hold is None or (self._was_overridden and not overridden):
            self.hold = (s[0], s[1], s[2])  # hold wherever we are
        self._was_overridden = overridden
        velocity = next((seg.velocity for seg in active if seg.velocity), None)

        px, py, pz, vx, vy, vz = s[0:6]
        q = tuple(s[6:10])
        if velocity is not None:
            ex, ey = velocity[0] - vx, velocity[1] - vy
            ax = 1.5 * ex + self.vel_integral[0]
            ay = 1.5 * ey + self.vel_integral[1]
            if math.hypot(ax, ay) < self.g * math.tan(self.MAX_TILT):  # integrate only while not tilt-limited
                self.vel_integral = [i + 0.8 * e * dt for i, e in zip(self.vel_integral, (ex, ey))]
            az_target = 1.0 * (self.hold[2] - pz) + 2.0 * (velocity[2] - vz)
        else:
            self.vel_integral = [0.0, 0.0]
            ax = 1.2 * (self.hold[0] - px) - 2.0 * vx
            ay = 1.2 * (self.hold[1] - py) - 2.0 * vy
            az_target = 4.0 * (self.hold[2] - pz) - 4.0 * vz
        a_max = self.g * math.tan(self.MAX_TILT)
        a_h = math.hypot(ax, ay)
        if a_h > a_max:
            ax, ay = ax * a_max / a_h, ay * a_max / a_h
        c, sn = math.cos(self.heading), math.sin(self.heading)
        a_fwd = ax * c + ay * sn
        a_right = -ax * sn + ay * c
        pitch_des = -math.atan2(a_fwd, self.g)
        roll_des = math.atan2(a_right, self.g)

        # attitude error as a rotation in body axes -> body rate command
        q_des = _quat_from_euler(roll_des, pitch_des, self.heading)
        q_err = _quat_mul((q_des[0], -q_des[1], -q_des[2], -q_des[3]), q)
        sign = 1.0 if q_err[0] >= 0.0 else -1.0
        rate_cmd = [-2.0 * self.ATTITUDE_GAIN * sign * q_err[k] for k in (1, 2, 3)]
        rate_cmd = [max(-self.MAX_RATE, min(self.MAX_RATE, r)) for r in rate_cmd]

        # throttle: thrust for the vertical acceleration, tilt-compensated
        az_target = max(-0.8 * self.g, min(1.5 * self.g, az_target))
        self.alt_integral += (self.hold[2] - pz) * dt if velocity is None else 0.0
        self.alt_integral = max(-2.0, min(2.0, self.alt_integral))
        tilt = 1.0 - 2.0 * (q[1] ** 2 + q[2] ** 2)  # cos of tilt = R22
        thrust_ratio = (self.g - az_target - 0.8 * self.alt_integral) / self.g / max(tilt, 0.3)
        duty = self.hover_duty * math.sqrt(max(thrust_ratio, 0.0))
        throttle = (duty - self.idle) / (1.0 - self.idle)

        sticks = [
            self._stick_for_rate(0, rate_cmd[0]),
            self._stick_for_rate(1, -rate_cmd[1]),  # pitch stick forward = nose down
            self._stick_for_rate(2, rate_cmd[2]),
            max(0.0, min(1.0, throttle)),
        ]
        for seg in active:
            for k, axis in enumerate(AXES):
                value = seg.stick(axis, t)
                if value is not None:
                    sticks[k] = value
        return tuple(sticks)


class StickFile:
    """Recorded stick inputs (CSV: time [s], roll [1], pitch [1], yaw [1],
    throttle [1]), sample-and-hold, for replaying a pilot's inputs."""

    def __init__(self, path: str | Path):
        from .sysid import read_csv

        data = read_csv(path)
        missing = {"time", *AXES} - set(data)
        if missing:
            raise ValueError(f"{path}: stick file needs columns {sorted(missing)}")
        self.t = data["time"]
        self.values = np.column_stack([data[a] for a in AXES])
        self.duration = float(self.t[-1])

    def sticks(self, t: float, s: list[float], dt: float) -> tuple[float, float, float, float]:
        k = max(0, int(np.searchsorted(self.t, t, side="right")) - 1)
        return tuple(float(v) for v in self.values[k])
