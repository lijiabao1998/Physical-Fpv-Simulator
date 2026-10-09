"""Virtual wind tunnel: the flight model on a six-component balance.

Real development puts the aircraft, or one motor and prop, on a balance in
a wind tunnel. Here the same tests run on the model (dynamics.QuadModel and
rotor_ff.AnchoredRotor), so their results are exactly what the flight
simulation uses:

* Test section and balance. Free stream V at angle of attack alpha (nose
  down positive, the forward-flight tilt) and sideslip beta (wind from the
  right positive). The balance is at the CG and reads forces in body axes
  (FRD) and moments about the CG in body axes; lift, drag and side force
  are the same forces in wind axes. The free stream is uniform; wall,
  blockage and mounting corrections belong to the measurement side of a
  real test and are not modelled.
* Rotor states: props removed, props stopped (held), fixed rpm (motors at
  the duty that holds it), fixed throttle (motors settle at their own rpm).
* The battery is the aircraft's own model in the given state (default:
  full and rested).

Tests:

1. Drag polar: props removed or stopped, speed and alpha swept.
2. Powertrain in oblique flow: one prop at fixed rpm, speed and disk angle
   of attack swept: thrust, rotor drag (H), torque, shaft power.
3. Trim in level flight: at each speed the tilt, collective throttle and
   front/rear throttle difference that give zero net force and zero
   pitching moment, with the motors at their equilibrium rpm; roll and yaw
   residuals are reported.
4. Power curve: battery output power against speed, the speeds of minimum
   power (longest endurance) and minimum power per speed (longest range),
   the highest level speed at full throttle, and endurance and range at
   constant speed from a full pack (re-trimmed as the battery discharges).

Synthetic balance data (``balance_data``) adds load-cell noise to these
readings for validating ``tunnel_fit``, as the virtual thrust stand does for
``fit-prop``.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

from .design import Aircraft
from .dynamics import Outputs, QuadModel
from .flightcontroller import quad_mixer
from .performance import hover_point
from .units import RADS_TO_RPM

PROPS = ("off", "stopped", "rpm", "throttle")


def _quaternion(alpha: float, yaw: float = 0.0) -> tuple[float, float, float, float]:
    """Attitude with pitch -alpha (nose down by alpha) and the given yaw (ZYX)."""
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(-alpha / 2), math.sin(-alpha / 2)
    return (cy * cp, -sy * sp, cy * sp, sy * cp)


def _rotation(q) -> np.ndarray:
    qw, qx, qy, qz = q
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qw * qz), 2 * (qx * qz + qw * qy)],
        [2 * (qx * qy + qw * qz), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qw * qx)],
        [2 * (qx * qz - qw * qy), 2 * (qy * qz + qw * qx), 1 - 2 * (qx * qx + qy * qy)],
    ])


def body_velocity(speed: float, alpha: float, beta: float) -> np.ndarray:
    """Air-relative velocity of the aircraft in body axes for the tunnel's
    free stream (the aircraft 'flies' north-east at sideslip beta, pitched
    nose down by alpha)."""
    v_world = speed * np.array([math.cos(beta), math.sin(beta), 0.0])
    return _rotation(_quaternion(alpha)).T @ v_world


@dataclass(frozen=True)
class Reading:
    speed: float  # m/s
    alpha: float  # rad
    beta: float  # rad
    props: str
    omega: tuple[float, ...]  # rad/s per rotor
    duty: tuple[float, ...]
    force: tuple[float, float, float]  # N, body axes
    moment: tuple[float, float, float]  # N m, body axes about the CG
    lift: float
    drag: float
    side: float
    p_bus: float  # W, battery output
    i_bus: float  # A
    v_bus: float  # V


class Tunnel:
    """One aircraft on the balance."""

    def __init__(self, ac: Aircraft, soc: float = 1.0):
        self.ac = ac
        self.model = QuadModel(ac, ac.extras, ground_effect=False)
        prop = replace(ac.powertrain.prop, blade=None)
        bare = replace(ac, powertrain=replace(ac.powertrain, prop=prop))
        self.props_off = QuadModel(bare, replace(ac.extras, rotor_drag_factor=0.0, flap_fraction=None), ground_effect=False)
        self.inertia = np.array(self.model.inertia)
        self.mass = self.model.mass
        self.rho = ac.env.rho
        self.g = ac.env.g
        self.battery = (soc, 0.0, ac.battery_start_temperature)  # rested pack at the take-off temperature
        self.mixer = quad_mixer([r.position for r in ac.rotors], [r.spin for r in ac.rotors])
        self.pitch_mix = [row[1] for row in self.mixer]
        self.n = self.model.n
        hp = hover_point(ac)
        self.hover = hp

    # ------------------------------------------------------------ balance

    def _state(self, speed, alpha, beta, omegas, battery=None):
        q = _quaternion(alpha)
        v = (speed * math.cos(beta), speed * math.sin(beta), 0.0)
        soc, v_rc, temp = battery or self.battery
        return [0.0, 0.0, -1000.0, *v, *q, 0.0, 0.0, 0.0, *omegas, soc, v_rc, temp]

    def _loads(self, model, s, duties):
        o = Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)
        d = model.derivative(s, list(duties), out=o)
        R = _rotation(s[6:10])
        f_world = self.mass * np.array(d[3:6]) - np.array([0.0, 0.0, self.mass * self.g])
        force = R.T @ f_world
        moment = self.inertia @ np.array(d[10:13])  # body rates are zero: no gyroscopic or Euler terms
        return d, force, moment, o

    def reading(self, speed: float, alpha: float = 0.0, beta: float = 0.0, props: str = "stopped",
                rpm: float | None = None, duty: float | None = None) -> Reading:
        """One balance reading. ``props``: off, stopped, rpm (with ``rpm`` in rad/s) or throttle (``duty``)."""
        if props not in PROPS:
            raise ValueError(f"props must be one of {PROPS}")
        n = self.n
        model = self.props_off if props == "off" else self.model
        if props in ("off", "stopped"):
            omegas, duties = [0.0] * n, [0.0] * n
        elif props == "rpm":
            omegas = [float(rpm)] * n

            def res(dd):
                d = model.derivative(self._state(speed, alpha, beta, omegas), list(dd))
                return d[13:13 + n]

            duties = list(fsolve(res, [self.hover.duty] * n, xtol=1e-12))
        else:
            duties = [float(duty)] * n

            def res(ww):
                d = model.derivative(self._state(speed, alpha, beta, list(ww)), duties)
                return [x / 1e3 for x in d[13:13 + n]]

            omegas = list(fsolve(res, [self.hover.omega] * n, xtol=1e-12))
        s = self._state(speed, alpha, beta, omegas)
        _, force, moment, o = self._loads(model, s, duties)
        R = _rotation(s[6:10])
        f_world = R @ force
        v_hat = np.array([math.cos(beta), math.sin(beta), 0.0])
        drag = -float(f_world @ v_hat)
        lift = -float(f_world[2])
        side = float(f_world @ np.array([-math.sin(beta), math.cos(beta), 0.0]))
        return Reading(speed, alpha, beta, props, tuple(omegas), tuple(duties), tuple(force), tuple(moment), lift, drag,
                       side, o.v_bus * o.i_bus, o.i_bus, o.v_bus)

    # --------------------------------------------------------------- trim

    def trim(self, speed: float, guess: np.ndarray | None = None, battery=None) -> "TrimPoint | None":
        """Level flight at ``speed`` (m/s): tilt, collective, pitch differential and
        rotor speeds for zero net force and pitching moment."""
        n = self.n
        model = self.model
        pm = self.pitch_mix
        if guess is None:
            guess = np.array([math.radians(1.5 * speed), self.hover.duty, 0.0, *([self.hover.omega] * n)])

        def duties_of(x):
            return [x[1] + x[2] * pm[i] for i in range(n)]

        def res(x):
            s = self._state(speed, x[0], 0.0, list(x[3:]), battery)
            d = model.derivative(s, duties_of(x))
            return [d[3], d[5], d[11] * 1e-2, *[w / 1e3 for w in d[13:13 + n]]]

        x, info, ier, _ = fsolve(res, guess, full_output=True, xtol=1e-11)
        x[0] = (x[0] + math.pi) % (2.0 * math.pi) - math.pi  # the attitude is periodic in the tilt
        if ier != 1 or np.max(np.abs(res(x))) > 1e-6 or not (-0.2 < x[0] < 1.45) or min(x[3:]) <= 0.0:
            return None
        s = self._state(speed, x[0], 0.0, list(x[3:]), battery)
        duties = duties_of(x)
        d, force, moment, o = self._loads(model, s, duties)
        v_body = body_velocity(speed, x[0], 0.0)
        # drag budget along the flight path: airframe drag (per-axis drag areas) and rotor in-plane force
        body_drag = 0.5 * self.rho * sum(ax * v_body[0] ** 2 + az * v_body[2] ** 2 for _, (ax, _ay, az) in model.drag_points)
        rotor_drag = 0.0
        if speed > 0.0:
            v_hat = v_body / speed
            for i, w in enumerate(x[3:]):
                if model.rotor is not None:
                    fx, fy, _ = model.rotor.loads(tuple(v_body), float(w), model.spin[i], self.rho)["force"]
                else:
                    k = model.k_rotor_drag * float(w)
                    fx, fy = -k * v_body[0], -k * v_body[1]
                rotor_drag -= fx * v_hat[0] + fy * v_hat[1]
        return TrimPoint(speed=speed, tilt=float(x[0]), collective=float(x[1]), pitch_diff=float(x[2]),
                         duties=tuple(duties), omegas=tuple(float(w) for w in x[3:]), p_bus=o.v_bus * o.i_bus,
                         i_bus=o.i_bus, v_bus=o.v_bus, roll_residual=float(moment[0]), yaw_residual=float(moment[2]),
                         body_drag=body_drag, rotor_drag=rotor_drag, x=x, max_mu=o.edgewise_ratio)


@dataclass(frozen=True)
class TrimPoint:
    speed: float
    tilt: float  # rad, nose down
    collective: float  # duty
    pitch_diff: float  # duty, times the mixer's pitch row
    duties: tuple[float, ...]
    omegas: tuple[float, ...]
    p_bus: float  # W, battery output
    i_bus: float
    v_bus: float
    roll_residual: float  # N m
    yaw_residual: float
    body_drag: float  # N, airframe drag along the flight path
    rotor_drag: float  # N, rotors' in-plane force along the flight path
    x: np.ndarray = field(repr=False, default=None)
    max_mu: float = 0.0  # rotorcraft advance ratio, worst rotor

    @property
    def feasible(self) -> bool:
        return max(self.duties) <= 1.0


@dataclass
class TrimCurve:
    points: list[TrimPoint]
    v_max: float  # m/s, highest level speed with every motor at or below full throttle
    v_max_point: TrimPoint | None

    def arrays(self):
        v = np.array([p.speed for p in self.points])
        return v, np.array([p.p_bus for p in self.points])

    def best_speeds(self) -> tuple[float, float]:
        """(minimum-power speed, minimum power-per-speed speed), parabolic refinement on the grid."""
        v, p = self.arrays()
        out = []
        for y, x0 in ((p, 0.0), (p / np.maximum(v, 1e-9), 1.0)):
            mask = v >= x0
            vv, yy = v[mask], y[mask]
            k = int(np.argmin(yy))
            if 0 < k < len(vv) - 1:
                a, b, c = np.polyfit(vv[k - 1:k + 2], yy[k - 1:k + 2], 2)
                out.append(float(-b / (2 * a)) if a > 0 else float(vv[k]))
            else:
                out.append(float(vv[k]))
        return out[0], out[1]


def trim_curve(tunnel: Tunnel, speeds: np.ndarray | None = None, battery=None) -> TrimCurve:
    """Trim from hover upwards (each point starts from the previous one) until a
    motor would need more than full throttle; the top speed is found by bisection."""
    if speeds is None:
        speeds = np.arange(0.0, 100.0001, 2.0)
    points: list[TrimPoint] = []
    guess = None
    last_ok, first_bad = None, None
    for v in speeds:
        tp = tunnel.trim(float(v), guess, battery)
        if tp is None or not tp.feasible:
            first_bad = float(v)
            break
        points.append(tp)
        guess = tp.x
        last_ok = float(v)
    v_max, v_point = (last_ok if last_ok is not None else math.nan), (points[-1] if points else None)
    if last_ok is not None and first_bad is not None:
        lo, hi, g = last_ok, first_bad, points[-1].x
        for _ in range(12):
            mid = 0.5 * (lo + hi)
            tp = tunnel.trim(mid, g, battery)
            if tp is not None and tp.feasible:
                lo, g, v_point = mid, tp.x, tp
            else:
                hi = mid
        v_max = lo
    return TrimCurve(points, v_max, v_point)


@dataclass(frozen=True)
class CruiseEndurance:
    speed: float
    time: float  # s
    distance: float  # m
    reason: str  # reserve_soc, min_cell_voltage, battery_temperature, cannot_hold, t_max

    REASONS_ZH = {
        "reserve_soc": "達到保留電量",
        "min_cell_voltage": "負載下單芯電壓達到下限",
        "battery_temperature": "電池溫度達到上限",
        "cannot_hold": "電壓不足以維持此速度",
        "t_max": "達到計算時間上限",
    }

    @property
    def reason_zh(self) -> str:
        return self.REASONS_ZH[self.reason]


def cruise_endurance(tunnel: Tunnel, speed: float, guess: np.ndarray | None = None, dt: float = 5.0,
                     t_max: float = 7200.0) -> CruiseEndurance:
    """Constant-speed level flight from a full, rested pack at the take-off
    temperature until reserve charge, minimum cell voltage under load or the
    temperature limit; re-trimmed every ``dt`` as the battery discharges, the
    pack cooled by the airspeed. Last step interpolated to the crossing."""
    ac = tunnel.ac
    battery = ac.battery
    state = ac.initial_battery_state()
    reserve, v_min, t_lim = ac.criteria.reserve_soc, ac.criteria.min_cell_voltage, battery.max_temperature
    t = 0.0
    prev = None
    while t <= t_max:
        tp = tunnel.trim(speed, guess, (state.soc, state.v_rc, state.temperature))
        if tp is None or not tp.feasible:
            return CruiseEndurance(speed, t, speed * t, "cannot_hold")
        guess = tp.x
        v_cell = tp.v_bus / battery.series
        hit = {"reserve_soc": state.soc <= reserve, "min_cell_voltage": v_cell <= v_min,
               "battery_temperature": state.temperature >= t_lim}
        if any(hit.values()):
            if prev is None:
                return CruiseEndurance(speed, 0.0, 0.0, next(k for k, h in hit.items() if h))
            p_t, p_soc, p_v, p_temp = prev
            frac = {
                "reserve_soc": (p_soc - reserve) / (p_soc - state.soc) if hit["reserve_soc"] else 2.0,
                "min_cell_voltage": (p_v - v_min) / (p_v - v_cell) if hit["min_cell_voltage"] else 2.0,
                "battery_temperature": (t_lim - p_temp) / (state.temperature - p_temp) if hit["battery_temperature"] else 2.0,
            }
            reason = min(frac, key=frac.get)
            t_end = p_t + min(max(frac[reason], 0.0), 1.0) * (t - p_t)
            return CruiseEndurance(speed, t_end, speed * t_end, reason)
        prev = (t, state.soc, v_cell, state.temperature)
        state = state.step(battery, tp.i_bus, dt, ambient=ac.env.temperature, air_speed=speed)
        t += dt
    return CruiseEndurance(speed, t_max, speed * t_max, "t_max")


# ------------------------------------------------------------ test series


@dataclass
class PolarPoint:
    speed: float
    alpha: float
    props: str
    reading: Reading
    cda: float  # m^2, drag / (1/2 rho V^2)


def drag_polar(tunnel: Tunnel, speeds, alphas, props: str = "stopped") -> list[PolarPoint]:
    out = []
    for v in speeds:
        for a in alphas:
            r = tunnel.reading(float(v), float(a), 0.0, props)
            out.append(PolarPoint(float(v), float(a), props, r, r.drag / (0.5 * tunnel.rho * v * v)))
    return out


@dataclass
class RotorPoint:
    speed: float
    disk_alpha: float  # rad, forward tilt of the disk against the free stream
    omega: float
    thrust: float
    h_force: float
    torque: float
    mu: float  # rotorcraft advance ratio V cos(alpha) / (omega R)
    lam: float  # V sin(alpha) / (omega R)


def rotor_sweep(tunnel: Tunnel, omega: float, speeds, disk_alphas) -> list[RotorPoint]:
    """One prop at fixed rpm. Forward tilt alpha puts the free stream through the
    disk from the thrust side, as in forward flight (V_c = V sin alpha)."""
    rotor = tunnel.model.rotor
    if rotor is None:
        return []
    R = rotor.radius
    out = []
    for a in disk_alphas:
        for v in speeds:
            v_hub = (v * math.cos(a), 0.0, -v * math.sin(a))  # body FRD: edgewise along x, climb along -z
            loads = rotor.loads(v_hub, omega, 1.0, tunnel.rho)
            out.append(RotorPoint(float(v), float(a), omega, loads["thrust"], loads["h_force"], loads["torque"],
                                  v * math.cos(a) / (omega * R), v * math.sin(a) / (omega * R)))
    return out


# ------------------------------------------------------ synthetic data


BALANCE_COLUMNS = (("props", "1"), ("speed", "m/s"), ("alpha", "deg"), ("beta", "deg"), ("rpm", "rpm"), ("rho", "kg/m^3"),
                   ("fx", "N"), ("fy", "N"), ("fz", "N"), ("mx", "N*m"), ("my", "N*m"), ("mz", "N*m"))
PROPS_CODE = {"off": 0, "stopped": 1, "rpm": 2}


@dataclass(frozen=True)
class BalanceNoise:
    force: float = 0.01  # N, 1 sigma, plus the relative part
    moment: float = 0.0005  # N m
    relative: float = 0.005


def balance_data(tunnel: Tunnel, seed: int = 1, noise: BalanceNoise = BalanceNoise()) -> list[dict]:
    """A test matrix with load-cell noise: props removed over speed, alpha and
    beta (airframe drag and its centre), props at hover rpm and 1.3x hover rpm
    in edgewise flow (rotor drag)."""
    rng = np.random.default_rng(seed)
    rows = []
    matrix = []
    for v in (8.0, 12.0, 16.0, 20.0, 25.0):
        for a in (-10.0, 0.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0):
            matrix.append(("off", v, a, 0.0, 0.0))
        for b in (-20.0, 10.0, 20.0):
            matrix.append(("off", v, 0.0, b, 0.0))
    if tunnel.model.rotor is not None:
        for w in (tunnel.hover.omega, 1.3 * tunnel.hover.omega):
            for v in (3.0, 6.0, 9.0, 12.0, 15.0):
                matrix.append(("rpm", v, 0.0, 0.0, w))
    for props, v, a, b, w in matrix:
        r = tunnel.reading(v, math.radians(a), math.radians(b), props, rpm=w)
        f = np.array(r.force) + rng.normal(0.0, 1.0, 3) * (noise.force + noise.relative * np.abs(r.force))
        m = np.array(r.moment) + rng.normal(0.0, 1.0, 3) * (noise.moment + noise.relative * np.abs(r.moment))
        rows.append({"props": PROPS_CODE[props], "speed": v, "alpha": a, "beta": b, "rpm": w * RADS_TO_RPM,
                     "rho": tunnel.rho, "fx": f[0], "fy": f[1], "fz": f[2], "mx": m[0], "my": m[1], "mz": m[2]})
    return rows


def write_balance_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"{name} [{unit}]" for name, unit in BALANCE_COLUMNS])
        for row in rows:
            w.writerow([f"{row[name]:.6g}" for name, _ in BALANCE_COLUMNS])

