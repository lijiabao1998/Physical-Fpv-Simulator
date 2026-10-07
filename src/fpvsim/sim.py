"""Multi-rate flight simulation.

Rates (defaults): physics 8 kHz (RK4), gyro sampling 8 kHz, PID loop 4 kHz
(gyro samples averaged down to the loop rate), RC link 250 Hz (sticks are
held between frames), logging at a chosen rate. Motor commands are held
constant between PID loops (zero-order hold), as an ESC would.

Motor telemetry (rpm for the RPM filter) is the true rotor speed of the
previous physics step, i.e. one step of latency and no quantisation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .blackbox import FlightLog
from .design import Build
from .dynamics import Outputs, QuadModel, euler_angles
from .flightcontroller import FcConfig, FlightController, quad_mixer
from .performance import hover_point
from .pilot import Maneuver, StickFile, TestPilot
from .sensors import Gyro
from .units import RADS_TO_RPM

DEG = 180.0 / math.pi
AXES = ("roll", "pitch", "yaw")


@dataclass(frozen=True)
class SimSettings:
    physics_rate: float = 8000.0
    log_rate: float = 2000.0
    seed: int = 1
    start_altitude: float = 20.0  # m above ground, starting in trimmed hover
    wind: tuple[float, float, float] = (0.0, 0.0, 0.0)  # NED, m/s
    crash_speed: float = 3.0  # m/s, contact speed treated as a crash


def _define_columns(log: FlightLog, n: int) -> None:
    log.define("time", "s")
    for a in ("roll", "pitch", "yaw", "throttle"):
        log.define(f"rc_{a}", "1")
    for a in AXES:
        log.define(f"setpoint_{a}", "deg/s")
    for a in AXES:
        log.define(f"gyro_raw_{a}", "deg/s")
    for a in AXES:
        log.define(f"gyro_{a}", "deg/s")
    for term in ("p", "i", "d", "f"):
        for a in AXES:
            log.define(f"{term}_{a}", "1")
    for i in range(n):
        log.define(f"motor_{i}", "%")
    for i in range(n):
        log.define(f"rpm_{i}", "rpm")
    log.define("vbat", "V")
    log.define("current", "A")
    log.define("mah", "mAh")
    # truth and physics, not available on a real aircraft
    for name, unit in (("pos_n", "m"), ("pos_e", "m"), ("alt", "m"), ("vel_n", "m/s"), ("vel_e", "m/s"), ("vel_d", "m/s")):
        log.define(name, unit)
    for a in AXES:
        log.define(f"att_{a}", "deg")
    for a in AXES:
        log.define(f"rate_{a}", "deg/s")
    for i in range(n):
        log.define(f"motor_current_{i}", "A")
    for i in range(n):
        log.define(f"thrust_{i}", "gf")
    for name in ("saturated", "on_ground", "descent_ratio", "max_advance_ratio", "tip_mach", "soc"):
        log.define(name, "1")


def simulate(
    build: Build,
    cfg: FcConfig,
    pilot_input: Maneuver | StickFile,
    settings: SimSettings = SimSettings(),
    overrides: Mapping[str, float] | None = None,
    duration: float | None = None,
) -> FlightLog:
    ac = build.realize(overrides)
    model = QuadModel(ac, ac.extras)
    n = model.n
    rng = np.random.default_rng(settings.seed)
    phys = settings.physics_rate
    for rate, name in ((cfg.gyro_rate, "gyro"), (cfg.pid_rate, "PID"), (settings.log_rate, "log")):
        if phys % rate:
            raise ValueError(f"physics rate must be an integer multiple of the {name} rate")
    gyro_every = int(phys // cfg.gyro_rate)
    pid_every = int(phys // cfg.pid_rate)
    log_every = int(phys // settings.log_rate)
    rc_every = max(1, int(round(phys / cfg.rc_link_rate)))
    dt = 1.0 / phys

    gyro = Gyro(ac.gyro, n, cfg.gyro_rate, rng)
    mixer = quad_mixer([r.position for r in ac.rotors], [r.spin for r in ac.rotors])
    fc = FlightController(cfg, mixer, ac.motor_idle)
    hover = hover_point(ac)
    if hover is None:
        raise ValueError("the aircraft cannot hover; nothing to fly")
    if isinstance(pilot_input, Maneuver):
        pilot = TestPilot(cfg, pilot_input, ac.mass_props.mass, ac.env.g, hover.duty, ac.motor_idle)
        total = duration if duration is not None else pilot_input.duration
    else:
        pilot = pilot_input
        total = duration if duration is not None else pilot_input.duration

    state = model.initial_state(position=(0.0, 0.0, -settings.start_altitude), omega=hover.omega)
    duties = [hover.duty] * n
    fc.initialise_hover(hover.duty)
    thetas = [0.0] * n
    sticks = (0.0, 0.0, 0.0, (hover.duty - ac.motor_idle) / (1.0 - ac.motor_idle))
    gyro_acc = [0.0, 0.0, 0.0]
    gyro_count = 0
    gyro_raw_deg = [0.0, 0.0, 0.0]
    mah = 0.0
    out = Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)
    speed_of_sound = ac.env.speed_of_sound
    radius = ac.powertrain.prop.radius
    max_contact = 0.0

    log = FlightLog(rate=settings.log_rate)
    _define_columns(log, n)
    log.meta = {
        "build": build.id,
        "fc": cfg.id,
        "input": getattr(pilot_input, "name", "stick file"),
        "seed": settings.seed,
        "physics_rate_hz": phys,
        "gyro_rate_hz": cfg.gyro_rate,
        "pid_rate_hz": cfg.pid_rate,
        "log_rate_hz": settings.log_rate,
        "input_hash": build.input_hash()[:16],
        "overrides": dict(overrides or {}),
    }

    steps = int(round(total * phys))
    for k in range(steps):
        t = k * dt
        if k % rc_every == 0:
            sticks = pilot.sticks(t, state, rc_every * dt)
        if k % gyro_every == 0:
            g = gyro.sample(state[10:13], thetas, state[13 : 13 + n])
            gyro_acc[0] += g[0]
            gyro_acc[1] += g[1]
            gyro_acc[2] += g[2]
            gyro_count += 1
        if k % pid_every == 0:
            gyro_raw_deg = [x / gyro_count * DEG for x in gyro_acc]
            gyro_acc = [0.0, 0.0, 0.0]
            gyro_count = 0
            rotor_hz = [w / (2.0 * math.pi) for w in state[13 : 13 + n]]
            duties = fc.update(sticks, gyro_raw_deg, rotor_hz)

        prev = state
        state = model.step(state, duties, dt, settings.wind, out)
        for i in range(n):
            thetas[i] = (thetas[i] + prev[13 + i] * dt) % (2.0 * math.pi)
        mah += out.i_bus * dt / 3.6
        max_contact = max(max_contact, out.max_contact_speed)

        if k % log_every == 0:
            roll, pitch, yaw = euler_angles(tuple(prev[6:10]))
            omegas = prev[13 : 13 + n]
            row = {
                "time": t,
                "rc_roll": sticks[0],
                "rc_pitch": sticks[1],
                "rc_yaw": sticks[2],
                "rc_throttle": sticks[3],
                "vbat": out.v_bus,
                "current": out.i_bus,
                "mah": mah,
                "pos_n": prev[0],
                "pos_e": prev[1],
                "alt": -prev[2],
                "vel_n": prev[3],
                "vel_e": prev[4],
                "vel_d": prev[5],
                "att_roll": roll * DEG,
                "att_pitch": pitch * DEG,
                "att_yaw": yaw * DEG,
                "saturated": 1.0 if fc.saturated else 0.0,
                "on_ground": 1.0 if out.on_ground else 0.0,
                "descent_ratio": out.descent_ratio,
                "max_advance_ratio": max(out.advance_ratio),
                "tip_mach": max(omegas) * radius / speed_of_sound,
                "soc": prev[13 + n],
            }
            for a, axis in enumerate(AXES):
                row[f"setpoint_{axis}"] = fc.setpoint[a]
                row[f"gyro_raw_{axis}"] = gyro_raw_deg[a]
                row[f"gyro_{axis}"] = fc.gyro_filtered[a]
                row[f"rate_{axis}"] = prev[10 + a] * DEG
                for j, term in enumerate("pidf"):
                    row[f"{term}_{axis}"] = fc.terms[a][j]
            for i in range(n):
                row[f"motor_{i}"] = 100.0 * duties[i]
                row[f"rpm_{i}"] = omegas[i] * RADS_TO_RPM
                row[f"motor_current_{i}"] = out.i_motor[i]
                row[f"thrust_{i}"] = out.thrust[i] / 9.80665e-3
            log.append(row)

    log.meta["max_contact_speed_m_s"] = max_contact
    log.meta["crashed"] = max_contact > settings.crash_speed
    return log
