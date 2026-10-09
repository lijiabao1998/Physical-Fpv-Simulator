"""Descriptive persistence of a frozen, rest-referenced specimen contrast."""

import numpy as np


def checked_trace(values, columns):
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or x.shape[1] != columns or len(x) < 2:
        raise ValueError("Unexpected trace shape")
    if not np.isfinite(x).all() or np.any(np.diff(x[:, 0]) <= 0):
        raise ValueError("Nonfinite or nonmonotone trace")
    return x


def charge_coordinates(measured):
    x = checked_trace(measured, 4)
    if np.any(x[:, 1] <= 0):
        raise ValueError("Strictly positive discharge current required")
    increments = np.diff(x[:, 0]) * (x[:-1, 1] + x[1:, 1]) / 7200
    q = np.r_[0.0, np.cumsum(increments)]
    if not np.isfinite(q).all() or np.any(np.diff(q) <= 0):
        raise ValueError("Charge coordinates are not finite and increasing")
    return q


def time_at_charge(measured, query_ah):
    x = checked_trace(measured, 4)
    q = charge_coordinates(x)
    target = float(query_ah)
    if not np.isfinite(target) or target < 0 or target > q[-1]:
        raise ValueError("Charge query outside recorded support")
    if target == q[-1]:
        return float(x[-1, 0])
    k = min(int(np.searchsorted(q, target, side="right") - 1), len(q) - 2)
    duration = x[k + 1, 0] - x[k, 0]
    current = x[k, 1]
    slope = (x[k + 1, 1] - current) / duration
    coulombs = (target - q[k]) * 3600
    discriminant = current * current + 2 * slope * coulombs
    if discriminant < 0 or not np.isfinite(discriminant):
        raise ValueError("Invalid charge inversion")
    elapsed = coulombs / current if slope == 0 else 2 * coulombs / (current + np.sqrt(discriminant))
    result = float(x[k, 0] + elapsed)
    tolerance = 64 * np.finfo(float).eps * max(1, abs(x[k + 1, 0]))
    if result < x[k, 0] - tolerance or result > x[k + 1, 0] + tolerance:
        raise ValueError("Charge inversion escaped interval")
    result = float(np.clip(result, x[k, 0], x[k + 1, 0]))
    returned_elapsed = result - x[k, 0]
    forward_ah = q[k] + (current * returned_elapsed + 0.5 * slope * returned_elapsed**2) / 3600
    if not np.isfinite(forward_ah) or abs(forward_ah - target) > 1e-12:
        raise ValueError("Charge inverse failed forward verification")
    return result


def linear_summary(time, values):
    t = np.asarray(time, dtype=float)
    y = np.asarray(values, dtype=float)
    if t.ndim != 1 or y.shape != t.shape or len(t) < 2:
        raise ValueError("Invalid summary shape")
    if not np.isfinite(t).all() or not np.isfinite(y).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Invalid summary support")
    dt = np.diff(t)
    length = t[-1] - t[0]
    return {
        "mean": float(np.sum(dt * (y[:-1] + y[1:]) / 2) / length),
        "rms": float(
            np.sqrt(np.sum(dt * (y[:-1] ** 2 + y[:-1] * y[1:] + y[1:] ** 2) / 3) / length)
        ),
        "max_abs": float(np.max(np.abs(y))),
        "start": float(y[0]),
        "end": float(y[-1]),
    }


def observables(measured, model, query, anchor, descriptor):
    x = checked_trace(measured, 4)
    m = checked_trace(model, 3)
    t = np.atleast_1d(np.asarray(query, dtype=float))
    if (
        not np.isfinite(t).all()
        or np.any(t < max(x[0, 0], m[0, 0]))
        or np.any(t > min(x[-1, 0], m[-1, 0]))
    ):
        raise ValueError("Time query outside common support")
    if not np.isfinite([anchor, descriptor]).all():
        raise ValueError("Invalid frozen descriptor or anchor")
    current, voltage, skin = [np.interp(t, x[:, 0], x[:, k]) for k in (1, 2, 3)]
    model_v, bulk = [np.interp(t, m[:, 0], m[:, k]) for k in (1, 2)]
    fall = anchor - voltage
    prediction = current * descriptor
    return {
        "current_a": current,
        "observed_fall_v": fall,
        "predicted_fall_v": prediction,
        "individual_discrepancy_v": fall - prediction,
        "original_residual_v": model_v - voltage,
        "model_voltage_v": model_v,
        "skin_temperature_k": skin,
        "bulk_temperature_k": bulk,
    }


def contrast(first, second, anchor_difference):
    out = {
        "observed_fall_contrast_v": first["observed_fall_v"] - second["observed_fall_v"],
        "predicted_fall_contrast_v": first["predicted_fall_v"] - second["predicted_fall_v"],
        "original_residual_contrast_v": first["original_residual_v"]
        - second["original_residual_v"],
        "model_voltage_contrast_v": first["model_voltage_v"] - second["model_voltage_v"],
        "skin_temperature_contrast_k": first["skin_temperature_k"] - second["skin_temperature_k"],
        "bulk_temperature_contrast_k": first["bulk_temperature_k"] - second["bulk_temperature_k"],
    }
    out["discrepancy_v"] = out["observed_fall_contrast_v"] - out["predicted_fall_contrast_v"]
    out["identity_closure_v"] = out["original_residual_contrast_v"] - (
        out["model_voltage_contrast_v"] - anchor_difference + out["observed_fall_contrast_v"]
    )
    if np.max(np.abs(out["identity_closure_v"])) > 1e-12:
        raise ValueError("Voltage identity closure failed")
    return out


def evaluate(cases, descriptors, anchors):
    if set(cases) != {"k1", "k2"} or set(descriptors) != set(cases) or set(anchors) != set(cases):
        raise ValueError("Both specimens required")
    for measured, model in cases.values():
        charge_coordinates(measured)
        checked_trace(model, 3)
    starts = [trace[0, 0] for pair in cases.values() for trace in pair]
    ends = [trace[-1, 0] for pair in cases.values() for trace in pair]
    start, end = max(starts), min(ends)
    if end <= max(start, 10):
        raise ValueError("No later common support")
    windows = []
    for lo, hi in ((10, 60), (60, 300), (300, 900), (900, 1800), (1800, end)):
        left, right = max(lo, start), min(hi, end)
        row = {"requested_interval_s": [float(lo), float(hi)], "empty": bool(right <= left)}
        if right > left:
            knots = np.unique(
                np.r_[
                    left,
                    right,
                    *[
                        x[(x > left) & (x < right)]
                        for pair in cases.values()
                        for x in (pair[0][:, 0], pair[1][:, 0])
                    ],
                ]
            )
            obs = {
                name: observables(*pair, knots, anchors[name], descriptors[name])
                for name, pair in cases.items()
            }
            signals = contrast(obs["k1"], obs["k2"], anchors["k1"] - anchors["k2"])
            for name, values in obs.items():
                for key in ("individual_discrepancy_v", "original_residual_v"):
                    signals[name + "_" + key] = values[key]
            row.update(
                interval_s=[float(left), float(right)],
                knots=len(knots),
                summaries={key: linear_summary(knots, value) for key, value in signals.items()},
            )
        windows.append(row)
    charge_points = []
    for q in (0.5, 1.0, 2.0, 3.0, 4.0):
        times = {}
        unavailable = {}
        for name, (measured, model) in cases.items():
            if q <= charge_coordinates(measured)[-1]:
                t = time_at_charge(measured, q)
                if model[0, 0] <= t <= model[-1, 0]:
                    times[name] = t
                else:
                    unavailable[name] = "Charge-matched time outside archived model support"
            else:
                unavailable[name] = "Charge target outside measured support"
        row = {
            "conditional_charge_ah": q,
            "supported": len(times) == 2,
            "times_s": times,
            "unavailable_reasons": unavailable,
        }
        if len(times) == 2:
            obs = {
                name: observables(*pair, times[name], anchors[name], descriptors[name])
                for name, pair in cases.items()
            }
            signals = contrast(obs["k1"], obs["k2"], anchors["k1"] - anchors["k2"])
            row["contrast"] = {key: float(value[0]) for key, value in signals.items()}
            row["cases"] = {
                name: {key: float(value[0]) for key, value in values.items()}
                for name, values in obs.items()
            }
        charge_points.append(row)
    return {
        "common_support_s": [float(start), float(end)],
        "frozen_descriptor_ohm": descriptors,
        "rest_anchor_v": anchors,
        "time_windows": windows,
        "conditional_charge_points": charge_points,
    }
