"""Flight-log analysis, the toolbox of a tuning session.

All functions take plain arrays, so they work on simulated logs and on real
Blackbox data converted to the same columns.

* Noise: Welch power spectral density, band-limited RMS, and a throttle vs
  frequency map (noise lines that move with motor rpm show up as diagonals).
* Step response from ordinary flight data by Wiener deconvolution of the
  setpoint -> gyro relation over short windows (the approach popularised by
  PIDtoolbox), averaged over windows with enough stick activity.
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
    window: float = 1.0,
    length: float = 0.5,
    min_setpoint: float = 40.0,
    regularisation: float = 1e-4,
) -> StepResponse | None:
    """Closed-loop step response (setpoint -> gyro) by Wiener deconvolution.

    Windows of ``window`` seconds with 50 % overlap; only windows whose peak
    setpoint exceeds ``min_setpoint`` (deg/s) are used. Each window's
    impulse response is h = IFFT(G S* / (|S|^2 + lambda)), with lambda a
    fraction of the window's mean input power; its running sum is the step
    response. Windows whose response does not settle near 1 are rejected.
    """
    n = int(window * fs)
    m = int(length * fs)
    taper = np.hanning(n)
    responses = []
    for start in range(0, len(setpoint) - n + 1, n // 2):
        sp = setpoint[start : start + n]
        if np.max(np.abs(sp)) < min_setpoint:
            continue
        gy = gyro[start : start + n]
        S = np.fft.rfft(sp * taper)
        G = np.fft.rfft(gy * taper)
        power = np.abs(S) ** 2
        H = G * np.conj(S) / (power + regularisation * power.mean())
        step = np.cumsum(np.fft.irfft(H, n)[:m])
        tail = step[int(0.6 * m) :].mean()
        if 0.5 < tail < 1.5:
            responses.append(step)
    if not responses:
        return None
    arr = np.array(responses)
    return StepResponse(np.arange(m) / fs, arr.mean(axis=0), arr.std(axis=0), len(responses))


def step_metrics(t: np.ndarray, y: np.ndarray, band: float = 0.05) -> dict[str, float]:
    """Rise time (10-90 %), overshoot, peak time and settling time (+/-band),
    relative to the final value (mean of the last 20 %)."""
    final = float(y[int(0.8 * len(y)) :].mean())
    if final <= 0:
        return {"rise_time": math.nan, "overshoot": math.nan, "peak_time": math.nan, "settling_time": math.nan, "final": final}
    yn = y / final
    i10 = int(np.argmax(yn >= 0.1))
    i90 = int(np.argmax(yn >= 0.9))
    outside = np.nonzero(np.abs(yn - 1.0) > band)[0]
    settle = t[outside[-1] + 1] if len(outside) and outside[-1] + 1 < len(t) else (t[-1] if len(outside) else 0.0)
    return {
        "rise_time": float(t[i90] - t[i10]),
        "overshoot": float(max(0.0, yn.max() - 1.0)),
        "peak_time": float(t[int(np.argmax(yn))]),
        "settling_time": float(settle),
        "final": final,
    }


def latency(setpoint: np.ndarray, gyro: np.ndarray, fs: float, max_lag: float = 0.1) -> float:
    """Delay (s) that best aligns gyro with setpoint (peak of cross-correlation)."""
    a = setpoint - setpoint.mean()
    b = gyro - gyro.mean()
    lags = np.arange(0, int(max_lag * fs) + 1)
    corr = [np.dot(a[: len(a) - k], b[k:]) for k in lags]
    return float(lags[int(np.argmax(corr))] / fs)


def tracking_rms(setpoint: np.ndarray, gyro: np.ndarray) -> float:
    return float(np.sqrt(np.mean((setpoint - gyro) ** 2)))
