"""Retrospective skin cooling prediction; not an identified cell thermal model."""

from __future__ import annotations

import numpy as np


def trace(time, temperature):
    t, y = np.asarray(time, dtype=float), np.asarray(temperature, dtype=float)
    if (
        t.ndim != 1
        or y.shape != t.shape
        or len(t) < 2
        or not np.isfinite(t).all()
        or not np.isfinite(y).all()
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("Expected finite, strictly increasing temperature trace")
    return t, y


def window(time, temperature, start, end):
    t, y = trace(time, temperature)
    if not np.isfinite([start, end]).all() or not t[0] <= start < end <= t[-1]:
        raise ValueError("Window outside measured coverage")
    knots = np.r_[start, t[(t > start) & (t < end)], end]
    return knots, np.interp(knots, t, y)


def prediction(time, baseline, anchor_temperature, rate, anchor_time=60.0):
    t = np.asarray(time, dtype=float)
    if (
        not np.isfinite([baseline, anchor_temperature, rate, anchor_time]).all()
        or rate < 0
        or not np.isfinite(t).all()
        or np.any(t < anchor_time)
    ):
        raise ValueError("Expected a finite nonnegative rate and forward prediction")
    return baseline + (anchor_temperature - baseline) * np.exp(-rate * (t - anchor_time))


def metrics(time, temperature, start, end, baseline, anchor_temperature, rate, order=8):
    """Integrate against linear source segments; check all residual extrema."""
    t, y = window(time, temperature, start, end)
    nodes, weights = np.polynomial.legendre.leggauss(order)
    dt = np.diff(t)
    q = (t[:-1, None] + t[1:, None]) / 2 + dt[:, None] * nodes / 2
    observed = y[:-1, None] + np.diff(y)[:, None] * (nodes + 1) / 2
    residual = prediction(q, baseline, anchor_temperature, rate) - observed
    mse = float(np.sum(dt[:, None] * weights * residual**2 / 2) / (end - start))
    mean = float(np.sum(dt[:, None] * weights * residual / 2) / (end - start))
    maximum = float(np.max(np.abs(prediction(t, baseline, anchor_temperature, rate) - y)))
    amplitude = anchor_temperature - baseline
    if rate > 0 and amplitude != 0:
        slopes = np.diff(y) / dt
        ratio = -slopes / (rate * amplitude)
        valid = ratio > 0
        roots = np.full(len(dt), np.nan)
        roots[valid] = 60.0 - np.log(ratio[valid]) / rate
        inside = valid & (roots > t[:-1]) & (roots < t[1:])
        if np.any(inside):
            r = roots[inside]
            actual = y[:-1][inside] + slopes[inside] * (r - t[:-1][inside])
            maximum = max(
                maximum,
                float(np.max(np.abs(prediction(r, baseline, anchor_temperature, rate) - actual))),
            )
    return {
        "interval_s": [start, end],
        "coverage_fraction": 1.0,
        "mse_k2": mse,
        "rmse_k": float(np.sqrt(mse)),
        "maximum_absolute_error_k": maximum,
        "mean_signed_error_k": mean,
        "historical_thermal_proxy_gates": {"rmse_2k": mse <= 4, "maximum_5k": maximum <= 5},
        "independent_thermal_validation": False,
    }


def fit_decay(time, temperature, baseline):
    """Fit only the fixed 60–600 s interval; never access a later observation."""
    source_t, source_y = trace(time, temperature)
    eligible = source_t <= 600.0
    if not np.any(eligible) or source_t[eligible][-1] < 599.0:
        raise ValueError("Calibration must reach an observed knot in [599,600] s")
    end = float(source_t[eligible][-1])
    t, y = window(source_t[eligible], source_y[eligible], 60.0, end)
    anchor = float(y[0])
    if not np.isfinite(baseline) or anchor <= baseline:
        raise ValueError("Cooling calibration requires positive initial excess temperature")

    def loss(log_tau):
        return metrics(t, y, 60.0, end, baseline, anchor, np.exp(-log_tau))["mse_k2"]

    grid = np.linspace(np.log(10.0), np.log(10000.0), 65)
    losses = [loss(z) for z in grid]
    best = int(np.argmin(losses))
    boundary = best in (0, len(grid) - 1)
    if boundary:
        z = grid[best]
    else:
        left, right = grid[best - 1], grid[best + 1]
        fraction = (np.sqrt(5) - 1) / 2
        x1 = right - fraction * (right - left)
        x2 = left + fraction * (right - left)
        f1, f2 = loss(x1), loss(x2)
        for _ in range(80):
            if f1 < f2:
                right, x2, f2 = x2, x1, f1
                x1 = right - fraction * (right - left)
                f1 = loss(x1)
            else:
                left, x1, f1 = x1, x2, f2
                x2 = left + fraction * (right - left)
                f2 = loss(x2)
        z = (left + right) / 2
    return {
        "baseline_c": float(baseline),
        "anchor_time_s": 60.0,
        "anchor_temperature_c": anchor,
        "tau_s": float(np.exp(z)),
        "rate_per_s": float(np.exp(-z)),
        "search_bounds_tau_s": [10.0, 10000.0],
        "boundary_optimum": boundary,
        "calibration": metrics(t, y, 60.0, end, baseline, anchor, np.exp(-z)),
        "identified_heat_transfer_coefficient": None,
    }
