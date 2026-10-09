"""Battery parameter identification from test data.

Two sources:

* An HPPC bench test (``battery_test.py`` or a real one): each discharge
  pulse and the relaxation after it are fitted with the Thevenin model

      V(t) = a - b q(t) - I(t) R0 - v_rc(t),
      v_rc[k+1] = v_rc[k] e^(-dt/tau) + R1 I[k] (1 - e^(-dt/tau)),

  where q is the charge drawn since the segment start and a, b describe the
  open-circuit voltage locally (a straight line over the few percent of
  state of charge a pulse spans). Nonlinear least squares gives R0, R1 and
  tau with standard errors from the Jacobian. The pack's constant-resistance
  model does not hold exactly across state of charge, so the combined value
  uses the spread between pulses as part of its uncertainty (model form),
  not just the fit's statistical error. The relaxed voltage before each
  pulse is the open-circuit voltage at that state of charge.

  Tests at two or more chamber temperatures give the Arrhenius activation
  energy by regression of ln R0 on 1/T (HC3 standard errors, sysid.py).

* A flight log (Blackbox: time, vbat, current): the same model over the
  whole flight with the open-circuit voltage taken from the build's OCV
  curve and state of charge from coulomb counting. The resistance found is
  the pack plus the wiring up to where vbat is measured, at the flight's
  temperatures; it is an in-flight check, not a substitute for a bench test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import lfilter

from .battery import R_GAS
from .sysid import _ols


@dataclass(frozen=True)
class PulseFit:
    soc: float  # state of charge at the pulse start
    ocv: float  # V, pack, relaxed voltage before the pulse
    current: float  # A, pulse current
    r0: float  # ohm, pack
    r1: float
    tau: float  # s
    r0_se: float
    r1_se: float
    tau_se: float
    residual_rms: float  # V
    segment: tuple  # (t, v_measured, v_model) for plotting


@dataclass(frozen=True)
class Estimate:
    value: float
    u: float  # standard uncertainty
    note: str = ""


@dataclass(frozen=True)
class HppcFit:
    series: int
    temperature: float  # K, mean chamber temperature
    capacity: float  # C, used for state of charge
    pulses: list[PulseFit]
    r0_cell: Estimate
    r1_cell: Estimate
    tau1: Estimate
    ocv_soc: np.ndarray
    ocv_cell: np.ndarray


def _segments(t: np.ndarray, current: np.ndarray, threshold: float) -> list[tuple[int, int, int]]:
    """(pre-rest start, pulse start, segment end) for each discharge pulse
    that is preceded and followed by a rest. A rest is |I| < 5 % of the
    threshold; a pulse is I > threshold."""
    rest = np.abs(current) < 0.05 * threshold
    high = current > threshold
    out = []
    k = 1
    n = len(t)
    while k < n:
        if high[k] and rest[k - 1]:
            start = k
            j = k - 1
            while j > 0 and rest[j - 1]:
                j -= 1
            end_pulse = k
            while end_pulse < n and high[end_pulse]:
                end_pulse += 1
            end = end_pulse
            while end < n and rest[end]:
                end += 1
            if end_pulse < n and end > end_pulse + 5 and start - j > 5:
                out.append((j, start, end))
            k = end
        else:
            k += 1
    return out


def _rc_voltage(t: np.ndarray, current: np.ndarray, r1: float, tau: float) -> np.ndarray:
    """Polarisation voltage of the R1-C1 pair driven by the measured current
    (zero-order hold between samples), starting relaxed."""
    dt = np.diff(t)
    if len(dt) and np.allclose(dt, dt[0], rtol=1e-3):  # uniform sampling: a first-order filter
        d = math.exp(-dt[0] / tau)
        v = lfilter([0.0, r1 * (1.0 - d)], [1.0, -d], current)
        return v
    decay = np.exp(-np.diff(t, prepend=t[0]) / tau)
    v_rc = np.zeros_like(current)
    for k in range(1, len(current)):
        v_rc[k] = v_rc[k - 1] * decay[k] + r1 * current[k - 1] * (1.0 - decay[k])
    return v_rc


def _model(params, t, current, q):
    a, b, r0, r1, tau = params
    return a - b * q - current * r0 - _rc_voltage(t, current, r1, tau)


def fit_pulse(t: np.ndarray, current: np.ndarray, voltage: np.ndarray, pre_rest: float = 5.0) -> tuple:
    """Fit one rest -> pulse -> rest segment. Returns (params, stderr, rms, model)."""
    t = t - t[0]
    q = np.concatenate([[0.0], np.cumsum(0.5 * (current[1:] + current[:-1]) * np.diff(t))])
    before = t < pre_rest
    v0 = float(np.mean(voltage[before])) if before.any() else float(voltage[0])
    edge = int(np.argmax(current > 0.5 * current.max()))
    i_pulse = float(np.median(current[current > 0.5 * current.max()]))
    r0_guess = max((v0 - voltage[edge]) / i_pulse, 1e-5)
    x0 = [v0, 0.0, r0_guess, r0_guess, 20.0]
    lower = [v0 - 1.0, -1e-2, 0.0, 0.0, 0.5]
    upper = [v0 + 1.0, 1e-2, 1.0, 1.0, 500.0]
    res = least_squares(lambda p: _model(p, t, current, q) - voltage, x0, bounds=(lower, upper), x_scale="jac")
    resid = res.fun
    dof = max(1, len(voltage) - len(x0))
    s2 = float(resid @ resid) / dof
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * s2
        se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    except np.linalg.LinAlgError:
        se = np.full(len(x0), math.nan)
    return res.x, se, math.sqrt(float(resid @ resid) / len(resid)), _model(res.x, t, current, q), i_pulse


def fit_hppc(data: dict[str, np.ndarray], series: int, capacity: float) -> HppcFit:
    """Identify the pack from an HPPC record (SI arrays: time, current, voltage[, temperature])."""
    t, current, voltage = data["time"], data["current"], data["voltage"]
    temperature = float(np.mean(data["temperature"])) if "temperature" in data else 298.15
    q_total = np.concatenate([[0.0], np.cumsum(0.5 * (current[1:] + current[:-1]) * np.diff(t))])
    threshold = 0.5 * float(np.max(current))
    pulses = []
    for j, start, end in _segments(t, current, threshold):
        sl = slice(max(j, start - int(5.0 / max(np.median(np.diff(t)), 1e-6))), end)
        params, se, rms, model, i_pulse = fit_pulse(t[sl], current[sl], voltage[sl])
        soc = 1.0 - q_total[start] / capacity
        ocv = float(np.mean(voltage[max(j, start - 20):start]))
        pulses.append(PulseFit(soc, ocv, i_pulse, params[2], params[3], params[4], se[2], se[3], se[4], rms,
                               (t[sl] - t[sl][0], voltage[sl], model)))
    if len(pulses) < 2:
        raise ValueError("found fewer than two rest-pulse-rest segments; is this an HPPC record?")

    def combine(values, errors, scale):
        values, errors = np.asarray(values) / scale, np.asarray(errors) / scale
        mean = float(np.mean(values))
        spread = float(np.std(values, ddof=1))
        u = math.sqrt(float(np.mean(errors**2)) + spread**2)
        return Estimate(mean, u, f"{len(values)} 個脈衝的平均；不確定度含脈衝之間（不同電量）的差異")

    r0 = combine([p.r0 for p in pulses], [p.r0_se for p in pulses], series)
    r1 = combine([p.r1 for p in pulses], [p.r1_se for p in pulses], series)
    tau = combine([p.tau for p in pulses], [p.tau_se for p in pulses], 1.0)
    order = np.argsort([p.soc for p in pulses])
    return HppcFit(series, temperature, capacity, pulses, r0, r1, tau,
                   np.array([pulses[i].soc for i in order]), np.array([pulses[i].ocv / series for i in order]))


@dataclass(frozen=True)
class ArrheniusFit:
    activation_energy: Estimate  # J/mol
    r0_ref: Estimate  # ohm per cell at t_ref
    t_ref: float
    points: list[tuple[float, float]]  # (temperature K, r0_cell ohm)


def fit_arrhenius(fits: list[HppcFit], t_ref: float = 298.15) -> ArrheniusFit:
    """ln R0 = ln R_ref + (Ea/R)(1/T - 1/T_ref) across tests at different temperatures."""
    temps = np.array([f.temperature for f in fits])
    if len(set(np.round(temps, 1))) < 2:
        raise ValueError("need HPPC tests at two or more temperatures for the activation energy")
    r0 = np.array([f.r0_cell.value for f in fits])
    x = 1.0 / temps - 1.0 / t_ref
    A = np.column_stack([np.ones_like(x), x])
    rel = np.array([f.r0_cell.u / f.r0_cell.value for f in fits])  # 1 sigma of each ln R0
    # uncertainty propagated from each test's own uncertainty (weighted least squares covariance)
    known = np.linalg.inv(A.T @ (A / rel[:, None] ** 2))
    if len(fits) > 2:  # also the scatter about the line (HC3); keep the larger of the two
        fit = _ols(A, np.log(r0), ("ln_r", "slope"))
        ln_r, slope = fit.values["ln_r"], fit.values["slope"]
        se_ln = max(fit.stderr["ln_r"], math.sqrt(known[0, 0]))
        se_slope = max(fit.stderr["slope"], math.sqrt(known[1, 1]))
    else:  # two points: the exact line
        slope = (np.log(r0[1]) - np.log(r0[0])) / (x[1] - x[0])
        ln_r = np.log(r0[0]) - slope * x[0]
        se_ln, se_slope = math.sqrt(known[0, 0]), math.sqrt(known[1, 1])
    ea = slope * R_GAS
    return ArrheniusFit(Estimate(ea, se_slope * R_GAS, "ln R0 對 1/T 的迴歸"),
                        Estimate(math.exp(ln_r), math.exp(ln_r) * se_ln, f"{t_ref - 273.15:.0f} °C 時的單芯 R0"),
                        t_ref, list(zip(temps.tolist(), r0.tolist())))


@dataclass(frozen=True)
class FlightFit:
    r_total: Estimate  # ohm, pack + wiring to the vbat sense point
    r1: Estimate  # ohm, pack
    tau: Estimate
    residual_rms: float
    t: np.ndarray
    v_measured: np.ndarray
    v_model: np.ndarray


def fit_flight(t: np.ndarray, vbat: np.ndarray, current: np.ndarray, ocv_soc: np.ndarray, ocv_pack: np.ndarray,
               capacity: float, soc0: float = 1.0, max_points: int = 20000) -> FlightFit:
    """Resistance from a flight log, with the OCV curve known and the pack full at the start."""
    stride = max(1, len(t) // max_points)
    t, vbat, current = t[::stride], vbat[::stride], current[::stride]
    q = np.concatenate([[0.0], np.cumsum(0.5 * (current[1:] + current[:-1]) * np.diff(t))])
    ocv = np.interp(soc0 - q / capacity, ocv_soc, ocv_pack)

    def model(p):
        r, r1, tau = p
        return ocv - current * r - _rc_voltage(t, current, r1, tau)

    res = least_squares(lambda p: model(p) - vbat, [0.03, 0.02, 20.0], bounds=([0, 0, 0.5], [1.0, 1.0, 500.0]))
    resid = res.fun
    s2 = float(resid @ resid) / max(1, len(resid) - 3)
    cov = np.linalg.pinv(res.jac.T @ res.jac) * s2
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    note = "Jacobian 估計的統計誤差；飛行中溫度與電量都在變，實際不確定度更大"
    return FlightFit(Estimate(res.x[0], se[0], note), Estimate(res.x[1], se[1], note), Estimate(res.x[2], se[2], note),
                     math.sqrt(float(resid @ resid) / len(resid)), t, vbat, model(res.x))
