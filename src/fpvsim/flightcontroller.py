"""Acro (rate) flight controller with the structure of Betaflight.

Independent implementation from public descriptions; no Betaflight source
code is used. What follows Betaflight, and how closely:

* Actual rates: rate(x) = C x + max(0, M - C) |x| (e x^5 + (1 - e) x), with C
  the centre sensitivity and M the max rate in deg/s. This matches the
  behaviour described in Betaflight PR #9495: a linear centre term plus a
  "wedge" ramp to the max rate, shaped by expo, each parameter independent.
* PID gain scaling uses Betaflight's published constants (P 0.032029,
  I 0.244381, D 0.000529), so gains are in the familiar numeric range. The
  PID sum is in units where 1000 = full motor range, limited to 500 (roll,
  pitch) and 400 (yaw), as in Betaflight.
* D-term acts on the measurement (filtered gyro), not on the error.
* Feedforward is the smoothed setpoint derivative. Its scale (F/100 x
  0.013754 per deg/s^2) is our assumption; Betaflight's feedforward adds
  averaging, jitter reduction and boost that are not modelled.
* Filters: static gyro and D-term low-pass chains and an RPM filter (notches
  at rotor harmonics from motor telemetry). Dynamic low-pass, dynamic notch,
  TPA, anti-gravity, I-term relax and thrust linearisation are not modelled.
* Mixer with airmode: the PID mix is scaled down if its range exceeds the
  motor range, then throttle is shifted to keep every motor within [0, 1].
* I-term anti-windup: integration is frozen while the mixer saturates and
  the error would grow the I-term; the I-term is also clamped.

Body-rate convention is FRD: roll + right wing down, pitch + nose up, yaw +
nose right. Stick convention: roll/yaw right positive, pitch stick forward
positive (which commands nose down).

So Betaflight gains and rates are a good starting point here, but a tune is
not guaranteed to transfer one to one.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .filters import PTn, make_lowpass

P_SCALE = 0.032029
I_SCALE = 0.244381
D_SCALE = 0.000529
F_SCALE = 0.013754  # per (F / 100); our assumption, see module docstring

FC_SCHEMA = "fpvsim.fc/1"


class FcConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AxisRates:
    center: float  # deg/s
    max: float  # deg/s
    expo: float  # 0..1

    def rate(self, x: float) -> float:
        """Commanded rate in deg/s for stick deflection x in [-1, 1]."""
        x = max(-1.0, min(1.0, x))
        shaped = abs(x) * (self.expo * x**5 + (1.0 - self.expo) * x)
        return self.center * x + max(0.0, self.max - self.center) * shaped


@dataclass(frozen=True)
class AxisPid:
    p: float
    i: float
    d: float
    f: float

    def scaled(self, factor_pd: float = 1.0, factor_i: float = 1.0, factor_f: float = 1.0) -> "AxisPid":
        return AxisPid(self.p * factor_pd, self.i * factor_i, self.d * factor_pd, self.f * factor_f)


@dataclass(frozen=True)
class FilterSpec:
    kind: str
    cutoff: float  # Hz


@dataclass(frozen=True)
class FcConfig:
    id: str
    name: str
    gyro_rate: float
    pid_rate: float
    rc_link_rate: float
    setpoint_smoothing: float  # Hz, PT3
    feedforward_smoothing: float  # Hz, PT3
    rates: tuple[AxisRates, AxisRates, AxisRates]
    pids: tuple[AxisPid, AxisPid, AxisPid]
    gyro_lowpass: tuple[FilterSpec, ...]
    dterm_lowpass: tuple[FilterSpec, ...]
    rpm_harmonics: int
    rpm_q: float
    rpm_min_hz: float
    airmode: bool = True
    pidsum_limit: float = 500.0
    pidsum_limit_yaw: float = 400.0
    iterm_limit: float = 400.0
    path: Path | None = field(default=None, compare=False)

    def with_gains(self, pd: float = 1.0, i: float = 1.0, f: float = 1.0, d: float = 1.0) -> "FcConfig":
        """Copy with gains multiplied, as in a tuning sweep (d multiplies D on top of pd)."""
        pids = tuple(AxisPid(a.p * pd, a.i * i, a.d * pd * d, a.f * f) for a in self.pids)
        return replace(self, pids=pids)

    def without_rpm_filter(self) -> "FcConfig":
        return replace(self, rpm_harmonics=0)


def _positive(where: str, value, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FcConfigError(f"{where} must be a number")
    if value < 0 or (value == 0 and not allow_zero):
        raise FcConfigError(f"{where} must be {'non-negative' if allow_zero else 'positive'}")
    return float(value)


def load_fc_config(path: str | Path) -> FcConfig:
    path = Path(path).resolve()
    with path.open("rb") as f:
        data = tomllib.load(f)
    if data.get("schema") != FC_SCHEMA:
        raise FcConfigError(f"{path}: expected schema = {FC_SCHEMA!r}")
    meta, loop, rc = data.get("meta", {}), data.get("loop", {}), data.get("rc", {})
    axes = ("roll", "pitch", "yaw")
    try:
        rates = tuple(
            AxisRates(
                _positive(f"rates.{a}.center", data["rates"][a]["center"]),
                _positive(f"rates.{a}.max", data["rates"][a]["max"]),
                float(data["rates"][a]["expo"]),
            )
            for a in axes
        )
        pids = tuple(
            AxisPid(*(_positive(f"pid.{a}.{k}", data["pid"][a][k], allow_zero=True) for k in "pidf")) for a in axes
        )
    except KeyError as e:
        raise FcConfigError(f"{path}: missing {e}") from None
    for a, r in zip(axes, rates):
        if not 0.0 <= r.expo < 1.0:
            raise FcConfigError(f"{path}: rates.{a}.expo must be in [0, 1)")

    filters = data.get("filters", {})

    def chain(name: str) -> tuple[FilterSpec, ...]:
        return tuple(
            FilterSpec(str(item["type"]), _positive(f"filters.{name}.cutoff_hz", item["cutoff_hz"]))
            for item in filters.get(name, [])
        )

    rpm = filters.get("rpm_filter", {"harmonics": 0, "q": 5.0, "min_hz": 100.0})
    limits = data.get("pid_limits", {})
    gyro_rate = _positive("loop.gyro_rate_hz", loop.get("gyro_rate_hz"))
    pid_rate = _positive("loop.pid_rate_hz", loop.get("pid_rate_hz"))
    if gyro_rate % pid_rate:
        raise FcConfigError(f"{path}: gyro rate must be an integer multiple of the PID rate")
    cfg = FcConfig(
        id=str(meta.get("id", path.stem)),
        name=str(meta.get("name", "")),
        gyro_rate=gyro_rate,
        pid_rate=pid_rate,
        rc_link_rate=_positive("rc.link_rate_hz", rc.get("link_rate_hz")),
        setpoint_smoothing=_positive("rc.setpoint_smoothing_hz", rc.get("setpoint_smoothing_hz")),
        feedforward_smoothing=_positive("rc.feedforward_smoothing_hz", rc.get("feedforward_smoothing_hz")),
        rates=rates,
        pids=pids,
        gyro_lowpass=chain("gyro_lowpass"),
        dterm_lowpass=chain("dterm_lowpass"),
        rpm_harmonics=int(rpm.get("harmonics", 0)),
        rpm_q=_positive("filters.rpm_filter.q", rpm.get("q", 5.0)),
        rpm_min_hz=_positive("filters.rpm_filter.min_hz", rpm.get("min_hz", 100.0)),
        airmode=bool(data.get("mixer", {}).get("airmode", True)),
        pidsum_limit=_positive("pid_limits.pidsum_limit", limits.get("pidsum_limit", 500.0)),
        pidsum_limit_yaw=_positive("pid_limits.pidsum_limit_yaw", limits.get("pidsum_limit_yaw", 400.0)),
        iterm_limit=_positive("pid_limits.iterm_limit", limits.get("iterm_limit", 400.0)),
        path=path,
    )
    for spec in cfg.gyro_lowpass + cfg.dterm_lowpass:
        make_lowpass(spec.kind, spec.cutoff, cfg.pid_rate)  # validates the type
        if spec.cutoff >= 0.5 * cfg.pid_rate:
            raise FcConfigError(f"{path}: filter cutoff {spec.cutoff} Hz is above the PID-loop Nyquist frequency")
    return cfg


def quad_mixer(positions, spins) -> list[tuple[float, float, float]]:
    """Mixer rows (roll, pitch, yaw) from rotor geometry.

    Thrust at (x, y) on -z gives roll moment -y T and pitch moment x T; a CW
    rotor (spin +z) reacts with -z torque, so yaw needs CCW rotors faster.
    """
    max_x = max(abs(p[0]) for p in positions)
    max_y = max(abs(p[1]) for p in positions)
    return [(-p[1] / max_y, p[0] / max_x, -1.0 if spin == "cw" else 1.0) for p, spin in zip(positions, spins)]


class FlightController:
    def __init__(self, cfg: FcConfig, mixer: list[tuple[float, float, float]], motor_idle: float):
        fs = cfg.pid_rate
        self.cfg = cfg
        self.fs = fs
        self.dt = 1.0 / fs
        self.mixer = mixer
        self.n = len(mixer)
        self.idle = motor_idle
        self.gyro_filters = [[make_lowpass(s.kind, s.cutoff, fs) for s in cfg.gyro_lowpass] for _ in range(3)]
        self.dterm_filters = [[make_lowpass(s.kind, s.cutoff, fs) for s in cfg.dterm_lowpass] for _ in range(3)]
        self.sp_smooth = [PTn(3, cfg.setpoint_smoothing, fs) for _ in range(3)]
        self.ff_smooth = [PTn(3, cfg.feedforward_smoothing, fs) for _ in range(3)]
        self.kp = [a.p * P_SCALE for a in cfg.pids]
        self.ki = [a.i * I_SCALE for a in cfg.pids]
        self.kd = [a.d * D_SCALE for a in cfg.pids]
        self.kf = [a.f / 100.0 * F_SCALE for a in cfg.pids]
        self.limits = (cfg.pidsum_limit, cfg.pidsum_limit, cfg.pidsum_limit_yaw)
        # RPM filter: per (motor, harmonic) coefficients, per (motor, harmonic, axis) state
        self.n_notch = self.n * cfg.rpm_harmonics
        self.notch_state = [[0.0, 0.0] for _ in range(self.n_notch * 3)]
        self.reset()

    def reset(self) -> None:
        self.iterm = [0.0, 0.0, 0.0]
        self.prev_d_input = [0.0, 0.0, 0.0]
        self.prev_sp_raw = [0.0, 0.0, 0.0]
        self.setpoint = [0.0, 0.0, 0.0]
        self.gyro_filtered = [0.0, 0.0, 0.0]
        self.terms = [[0.0] * 4 for _ in range(3)]  # P, I, D, F per axis
        self.motor = [0.0] * self.n
        self.saturated = False
        for group in (self.gyro_filters, self.dterm_filters):
            for axis in group:
                for flt in axis:
                    flt.reset()
        for flt in self.sp_smooth + self.ff_smooth:
            flt.reset()
        for st in self.notch_state:
            st[0] = st[1] = 0.0

    def initialise_hover(self, throttle: float) -> None:
        """Start as if already flying level at this throttle (no transient)."""
        self.reset()
        self.motor = [throttle] * self.n

    def _rpm_filter(self, g: list[float], rotor_hz: list[float]) -> list[float]:
        cfg = self.cfg
        nyquist = 0.48 * self.fs
        out = list(g)
        k = 0
        for i in range(self.n):
            for h in range(1, cfg.rpm_harmonics + 1):
                f0 = h * rotor_hz[i]
                if cfg.rpm_min_hz <= f0 < nyquist:
                    w0 = 2.0 * math.pi * f0 / self.fs
                    cw = math.cos(w0)
                    alpha = math.sin(w0) / (2.0 * cfg.rpm_q)
                    a0 = 1.0 + alpha
                    b0 = 1.0 / a0
                    a1 = -2.0 * cw / a0
                    a2 = (1.0 - alpha) / a0
                    for axis in range(3):
                        st = self.notch_state[3 * k + axis]
                        x = out[axis]
                        y = b0 * x + st[0]
                        st[0] = a1 * x - a1 * y + st[1]
                        st[1] = b0 * x - a2 * y
                        out[axis] = y
                k += 1
        return out

    def update(self, sticks: tuple[float, float, float, float], gyro: list[float], rotor_hz: list[float]) -> list[float]:
        """One PID loop. sticks = (roll, pitch, yaw, throttle); gyro in deg/s
        (body FRD); rotor_hz from motor telemetry. Returns motor commands in
        [0, 1] including idle (what is sent to the ESCs)."""
        cfg = self.cfg
        fs = self.fs
        roll, pitch, yaw, throttle = sticks
        sp_raw = (cfg.rates[0].rate(roll), -cfg.rates[1].rate(pitch), cfg.rates[2].rate(yaw))

        g = self._rpm_filter(gyro, rotor_hz) if cfg.rpm_harmonics else list(gyro)
        pid_low = not cfg.airmode and throttle < 0.05

        pidsum = [0.0, 0.0, 0.0]
        for a in range(3):
            x = g[a]
            for flt in self.gyro_filters[a]:
                x = flt.update(x)
            self.gyro_filtered[a] = x
            d_in = x
            for flt in self.dterm_filters[a]:
                d_in = flt.update(d_in)

            sp = self.sp_smooth[a].update(sp_raw[a])
            ff = self.ff_smooth[a].update((sp_raw[a] - self.prev_sp_raw[a]) * fs)
            self.prev_sp_raw[a] = sp_raw[a]
            self.setpoint[a] = sp

            err = sp - x
            p_term = self.kp[a] * err
            d_term = -self.kd[a] * (d_in - self.prev_d_input[a]) * fs
            self.prev_d_input[a] = d_in
            f_term = self.kf[a] * ff
            if pid_low:
                self.iterm[a] = 0.0
            elif not (self.saturated and err * self.iterm[a] > 0.0):
                self.iterm[a] += self.ki[a] * err * self.dt
                lim = cfg.iterm_limit
                self.iterm[a] = max(-lim, min(lim, self.iterm[a]))
            total = p_term + self.iterm[a] + d_term + f_term
            lim = self.limits[a]
            pidsum[a] = max(-lim, min(lim, total)) / 1000.0
            self.terms[a][0], self.terms[a][1], self.terms[a][2], self.terms[a][3] = p_term, self.iterm[a], d_term, f_term

        mix = [r * pidsum[0] + p * pidsum[1] + y * pidsum[2] for r, p, y in self.mixer]
        lo, hi = min(mix), max(mix)
        saturated = False
        span = hi - lo
        if span > 1.0:
            mix = [m / span for m in mix]
            lo, hi = lo / span, hi / span
            saturated = True
        thr = max(0.0, min(1.0, throttle))
        if cfg.airmode:
            thr = max(-lo, min(1.0 - hi, thr))
        motors = []
        for m in mix:
            v = thr + m
            if v < 0.0 or v > 1.0:
                saturated = True
                v = max(0.0, min(1.0, v))
            motors.append(v)
        self.saturated = saturated
        self.motor = [self.idle + (1.0 - self.idle) * v for v in motors]
        return self.motor


def dump_fc_config(cfg: FcConfig, cfg_id: str, name: str, note: str = "") -> str:
    """TOML text for a configuration, loadable with load_fc_config."""

    def chain(specs):
        return "[" + ", ".join(f'{{ type = "{s.kind}", cutoff_hz = {s.cutoff:g} }}' for s in specs) + "]"

    lines = [
        f"# {note}" if note else "# generated by fpvsim",
        f'schema = "{FC_SCHEMA}"',
        "",
        "[meta]",
        f'id = "{cfg_id}"',
        f'name = "{name}"',
        "",
        "[loop]",
        f"gyro_rate_hz = {cfg.gyro_rate:g}",
        f"pid_rate_hz = {cfg.pid_rate:g}",
        "",
        "[rc]",
        f"link_rate_hz = {cfg.rc_link_rate:g}",
        f"setpoint_smoothing_hz = {cfg.setpoint_smoothing:g}",
        f"feedforward_smoothing_hz = {cfg.feedforward_smoothing:g}",
        "",
        "[rates]",
    ]
    for axis, r in zip(("roll", "pitch", "yaw"), cfg.rates):
        lines.append(f"{axis} = {{ center = {r.center:g}, max = {r.max:g}, expo = {r.expo:g} }}")
    lines += ["", "[pid]"]
    for axis, p in zip(("roll", "pitch", "yaw"), cfg.pids):
        lines.append(f"{axis} = {{ p = {round(p.p)}, i = {round(p.i)}, d = {round(p.d)}, f = {round(p.f)} }}")
    lines += [
        "",
        "[pid_limits]",
        f"pidsum_limit = {cfg.pidsum_limit:g}",
        f"pidsum_limit_yaw = {cfg.pidsum_limit_yaw:g}",
        f"iterm_limit = {cfg.iterm_limit:g}",
        "",
        "[filters]",
        f"gyro_lowpass = {chain(cfg.gyro_lowpass)}",
        f"dterm_lowpass = {chain(cfg.dterm_lowpass)}",
        f"rpm_filter = {{ harmonics = {cfg.rpm_harmonics}, q = {cfg.rpm_q:g}, min_hz = {cfg.rpm_min_hz:g} }}",
        "",
        "[mixer]",
        f"airmode = {'true' if cfg.airmode else 'false'}",
        "",
    ]
    return "\n".join(lines)
