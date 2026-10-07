"""Flight-log analysis, the toolbox of a tuning session.

All functions take plain arrays, so they work on simulated logs and on real
Blackbox data converted to the same columns.

* Noise: Welch power spectral density, band-limited RMS, and a throttle vs
  frequency map (noise lines that move with motor rpm show up as diagonals).
* Step response from ordinary flight data by Wiener deconvolution of the
  setpoint -> gyro relation over short windows (the approach popularised by
  PIDtoolbox), combined over the windows where the axis was actually stepped.
* Step-response metrics, tracking error and latency (cross-correlation lag).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import welch


def psd(x: np.ndarray, fs: float, nperseg: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """One-sided PSD in (unit)^2/Hz."""
    nperseg = min(nperseg, len(x))
    return welch(x, fs=fs, nperseg=nperseg, window="hann", detrend="constant")


def band_rms(x: np.ndarray, fs: float, f_lo: float, f_hi: float) -> float:
    """RMS of the signal content between f_lo and f_hi, from the PSD."""
    f, p = psd(x, fs)
    mask = (f >= f_lo) & (f <= f_hi)
    return float(math.sqrt(np.trapezoid(p[mask], f[mask]))) if mask.sum() > 1 else 0.0


@dataclass(frozen=True)
class ThrottleMap:
    freqs: np.ndarray  # Hz
    throttle: np.ndarray  # bin centres, %
    power_db: np.ndarray  # [throttle bin, frequency], dB re 1 (unit)^2/Hz; NaN where no data
    frames: np.ndarray  # frames per throttle bin


def throttle_map(x: np.ndarray, throttle_pct: np.ndarray, fs: float, nfft: int = 256, bin_width: float = 5.0) -> ThrottleMap:
    window = np.hanning(nfft)
    scale = 1.0 / (fs * np.sum(window**2))
    edges = np.arange(0.0, 100.0 + bin_width, bin_width)
    acc = np.zeros((len(edges) - 1, nfft // 2 + 1))
    count = np.zeros(len(edges) - 1)
    for start in range(0, len(x) - nfft + 1, nfft // 2):
        seg = x[start : start + nfft]
        spec = np.abs(np.fft.rfft((seg - seg.mean()) * window)) ** 2 * scale
        spec[1:-1] *= 2.0
        k = int(np.clip(np.searchsorted(edges, throttle_pct[start : start + nfft].mean(), side="right") - 1, 0, len(count) - 1))
        acc[k] += spec
        count[k] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        power = 10.0 * np.log10(acc / count[:, None])
    power[count == 0] = np.nan
    return ThrottleMap(np.fft.rfftfreq(nfft, 1.0 / fs), 0.5 * (edges[:-1] + edges[1:]), power, count)


@dataclass(frozen=True)
class StepResponse:
    t: np.ndarray  # s
    mean: np.ndarray
    std: np.ndarray
    segments: int


def step_response(
    setpoint: np.ndarray,
    gyro: np.ndarray,
    fs: float,
    window: float = 2.0,
    length: float = 0.5,
    min_setpoint: float = 100.0,
    regularisation: float = 1e-4,
    spans: list[tuple[float, float]] | None = None,
) -> StepResponse | None:
    """Closed-loop step response (setpoint -> gyro) by Wiener deconvolution.

    Windows of ``window`` seconds with 75 % overlap; a window several times
    longer than the response keeps truncation bias small (with 1 s windows
    the settled level came out ~5 % low on a known system, 2 s gives ~1 %).
    A window is used only if
    its peak setpoint exceeds ``min_setpoint`` (deg/s) and, when ``spans``
    is given (seconds from the start of the arrays), it lies inside one of
    them: for a scripted test flight, the stretches where this axis is being
    stepped, so the test pilot's small corrections do not count as steps.

    Windows are combined H1-style: H = sum(G S*) / (sum |S|^2 + lambda), so
    each window counts in proportion to how strongly it was excited and a
    single poorly excited window cannot dominate. The step response is the
    running sum of the impulse response IFFT(H). ``std`` is the spread of
    the per-window estimates, for display.
    """
    n = int(window * fs)
    m = int(length * fs)
    taper = np.hanning(n)
    cross = np.zeros(n // 2 + 1, dtype=complex)
    power = np.zeros(n // 2 + 1)
    singles = []
    for start in range(0, len(setpoint) - n + 1, n // 4):
        if spans is not None and not any(t0 <= start / fs and (start + n) / fs <= t1 for t0, t1 in spans):
            continue
        sp = setpoint[start : start + n]
        if np.max(np.abs(sp)) < min_setpoint:
            continue
        S = np.fft.rfft(sp * taper)
        G = np.fft.rfft(gyro[start : start + n] * taper)
        cross += G * np.conj(S)
        power += np.abs(S) ** 2
        p = np.abs(S) ** 2
        singles.append(np.cumsum(np.fft.irfft(G * np.conj(S) / (p + regularisation * p.mean()), n)[:m]))
    if not singles:
        return None
    H = cross / (power + regularisation * power.mean())
    mean = np.cumsum(np.fft.irfft(H, n)[:m])
    return StepResponse(np.arange(m) / fs, mean, np.array(singles).std(axis=0), len(singles))


def step_metrics(t: np.ndarray, y: np.ndarray, band: float = 0.05, reference: float | None = 1.0) -> dict[str, float]:
    """Rise time (10-90 %), overshoot, peak time and settling time (+/-band).

    The reference level is the step size, 1: a rate loop with an I-term
    settles there, and dividing by an estimated final value would turn any
    estimator bias in the tail into overshoot. ``reference=None`` uses the
    mean of the last 20 % instead (for systems without integral action).
    ``final`` is reported either way. ``settled`` is 0 when the response is
    still outside the band at the end of the record; the settling time is
    then only a lower bound."""
    final = float(y[int(0.8 * len(y)) :].mean())
    ref = final if reference is None else reference
    if ref <= 0:
        return {"rise_time": math.nan, "overshoot": math.nan, "peak_time": math.nan, "settling_time": math.nan,
                "final": final, "settled": 0.0}
    yn = y / ref
    i10 = int(np.argmax(yn >= 0.1))
    i90 = int(np.argmax(yn >= 0.9))
    outside = np.nonzero(np.abs(yn - 1.0) > band)[0]
    settled = not len(outside) or outside[-1] + 1 < len(t)
    settle = t[outside[-1] + 1] if len(outside) and settled else (t[-1] if len(outside) else 0.0)
    return {
        "rise_time": float(t[i90] - t[i10]),
        "overshoot": float(max(0.0, yn.max() - 1.0)),
        "peak_time": float(t[int(np.argmax(yn))]),
        "settling_time": float(settle),
        "final": final,
        "settled": 1.0 if settled else 0.0,
    }


@dataclass(frozen=True)
class EdgeSteps:
    """Step response measured directly at known stick edges."""

    response: StepResponse  # normalised response (0 before, 1 = new setpoint), mean and spread over edges
    overshoot: np.ndarray  # per edge
    rise_time: np.ndarray  # per edge, s
    settling_time: np.ndarray  # per edge, s (inf if never within the band)


def edge_steps(
    t: np.ndarray,
    setpoint: np.ndarray,
    gyro: np.ndarray,
    edges: list[tuple[float, float]],
    min_step: float = 20.0,
    band: float = 0.05,
) -> EdgeSteps | None:
    """Step response from scripted steps whose timing is known.

    ``edges`` are (start, end) of constant-stick segments. For each, the
    setpoint before the edge and its plateau at the end of the segment give
    the step; the gyro is normalised to it (0 = old level, 1 = new level),
    so overshoot, rise time and settling time are read directly with no
    deconvolution. Steps smaller than ``min_step`` deg/s are skipped.
    The steps should stay out of mixer saturation, or the result describes
    the saturated (non-linear) response instead.
    """
    curves, overshoot, rise, settle = [], [], [], []
    dt = float(np.median(np.diff(t)))
    for t0, t1 in edges:
        before = (t >= t0 - 0.03) & (t < t0)
        plateau = (t >= t1 - 0.08) & (t < t1)
        window = (t >= t0) & (t < t1)
        if not before.any() or not plateau.any():
            continue
        start, final = setpoint[before].mean(), setpoint[plateau].mean()
        step = final - start
        if abs(step) < min_step:
            continue
        y = (gyro[window] - start) / step
        tt = t[window] - t0
        overshoot.append(max(0.0, float(y.max()) - 1.0))
        i10, i90 = int(np.argmax(y >= 0.1)), int(np.argmax(y >= 0.9))
        rise.append(float(tt[i90] - tt[i10]))
        outside = np.nonzero(np.abs(y - 1.0) > band)[0]
        settle.append(float(tt[outside[-1] + 1]) if len(outside) and outside[-1] + 1 < len(tt) else
                      (0.0 if not len(outside) else math.inf))
        curves.append(y)
    if not curves:
        return None
    n = min(len(c) for c in curves)
    arr = np.array([c[:n] for c in curves])
    response = StepResponse(np.arange(n) * dt, arr.mean(axis=0), arr.std(axis=0), len(curves))
    return EdgeSteps(response, np.array(overshoot), np.array(rise), np.array(settle))


def latency(setpoint: np.ndarray, gyro: np.ndarray, fs: float, max_lag: float = 0.1) -> float:
    """Delay (s) that best aligns gyro with setpoint (peak of cross-correlation)."""
    a = setpoint - setpoint.mean()
    b = gyro - gyro.mean()
    lags = np.arange(0, int(max_lag * fs) + 1)
    corr = [np.dot(a[: len(a) - k], b[k:]) for k in lags]
    return float(lags[int(np.argmax(corr))] / fs)


def tracking_rms(setpoint: np.ndarray, gyro: np.ndarray) -> float:
    return float(np.sqrt(np.mean((setpoint - gyro) ** 2)))
