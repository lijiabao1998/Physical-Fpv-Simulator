"""Conditional charge-aligned comparison; no fit, solve, or true-SOC inference."""

import math

import numpy as np


def checked(array, columns):
    data = np.asarray(array, dtype=float)
    if data.ndim != 2 or data.shape[1] != columns or len(data) < 2:
        raise ValueError("Invalid curve schema")
    if not np.isfinite(data).all() or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError("Nonfinite values or nonincreasing clock")
    return data


def charge_axis(observed, command_start=False):
    """Columns: step seconds, raw negative discharge A, V, measured skin K."""
    data = checked(observed, 4)
    t, raw = data[:, 0], data[:, 1]
    if t[0] < 0 or np.any(raw >= 0):
        raise ValueError("Discharge requires nonnegative step time and negative raw current")
    current = -raw
    dq = np.diff(t) * (current[1:] + current[:-1]) / 7200
    charge = np.r_[0.0, np.cumsum(dq)]
    if command_start:
        charge += current[0] * t[0] / 3600
    if not np.isfinite(charge).all() or np.any(np.diff(charge) <= 0):
        raise ValueError("Nonincreasing or nonfinite charge")
    return charge


def below_intervals(q, values, threshold=0.0):
    """Exact open-negative sets for a piecewise-linear interpolant; plateau aware."""
    result = []
    for left, right, a, b in zip(q[:-1], q[1:], values[:-1], values[1:], strict=True):
        a, b = a - threshold, b - threshold
        if a >= 0 and b >= 0:
            continue
        start, stop = float(left), float(right)
        if a >= 0:
            start = float(left + (right - left) * a / (a - b))
        elif b >= 0:
            stop = float(left + (right - left) * a / (a - b))
        if stop > start:
            if result and result[-1][1] == start:
                result[-1][1] = stop
            else:
                result.append([start, stop])
    return result


def statistics(q, values):
    width = float(q[-1] - q[0])
    dq = np.diff(q)
    a, b = values[:-1], values[1:]
    negative = sum(right - left for left, right in below_intervals(q, values))
    zero = float(np.sum(dq[(a == 0) & (b == 0)]))
    return {
        "mean_v": float(np.sum(dq * (a + b) / 2) / width),
        "rms_v": math.sqrt(float(np.sum(dq * (a * a + a * b + b * b) / 3) / width)),
        "minimum_v": float(min(values)),
        "maximum_v": float(max(values)),
        "negative_charge_fraction": negative / width,
        "zero_plateau_charge_fraction": zero / width,
        "positive_charge_fraction": max(0.0, 1 - (negative + zero) / width),
    }


def compare(low, high, model, command_start=False):
    """Model columns: time_s, capacity_Ah, terminal_V, bulk_OCV_V, bulk_K."""
    low, high, model = checked(low, 4), checked(high, 4), checked(model, 5)
    ql, qh = charge_axis(low, command_start), charge_axis(high, command_start)
    if np.any(np.diff(model[:, 1]) <= 0):
        raise ValueError("Model charge must increase")
    if not model[0, 0] <= high[0, 0] <= model[-1, 0]:
        raise ValueError("First measured time is outside model support")
    qm = model[:, 1].copy()
    if not command_start:
        qm -= np.interp(high[0, 0], model[:, 0], qm)
    start, stop = max(ql[0], qh[0], qm[0]), min(ql[-1], qh[-1], qm[-1])
    if stop <= start:
        raise ValueError("Empty charge overlap; extrapolation forbidden")
    bounds = np.linspace(start, stop, 5)
    q = np.unique(
        np.concatenate(
            ([start, stop], bounds, *[x[(x > start) & (x < stop)] for x in (ql, qh, qm)])
        )
    )
    low_v, high_v = np.interp(q, ql, low[:, 2]), np.interp(q, qh, high[:, 2])
    m, u = np.interp(q, qm, model[:, 2]), np.interp(q, qm, model[:, 3])
    terms = {
        "static_reference": u - low_v,
        "measured_rate_difference": low_v - high_v,
        "model_bulk_to_terminal": u - m,
        "terminal_residual": m - high_v,
    }
    closure = float(
        max(
            abs(
                terms["static_reference"]
                + terms["measured_rate_difference"]
                - terms["model_bulk_to_terminal"]
                - terms["terminal_residual"]
            )
        )
    )
    if closure > 1e-12:
        raise ValueError("Charge-aligned arithmetic identity failed")
    windows = []
    for left, right in [(start, stop), *zip(bounds[:-1], bounds[1:], strict=True)]:
        mask = (q >= left) & (q <= right)
        windows.append(
            {
                "charge_interval_ah": [float(left), float(right)],
                "terms": {name: statistics(q[mask], value[mask]) for name, value in terms.items()},
            }
        )
    violations = below_intervals(q, terms["static_reference"], -1e-10)
    low_temp = np.interp(q, ql, low[:, 3])
    high_temp = np.interp(q, qh, high[:, 3])
    bulk_temp = np.interp(q, qm, model[:, 4])
    violation_details = []
    for left, right in violations:
        values = np.r_[
            np.interp(left, q, terms["static_reference"]),
            terms["static_reference"][(q > left) & (q < right)],
            np.interp(right, q, terms["static_reference"]),
        ]
        violation_details.append(
            {
                "interval_ah": [left, right],
                "width_ah": right - left,
                "minimum_v": float(min(values)),
            }
        )
    report = {
        "alignment": "command_start_hold" if command_start else "recorded_start",
        "absolute_soc_equivalence_established": False,
        "arithmetic_closure_max_v": closure,
        "common_charge_interval_ah": [float(start), float(stop)],
        "source_support": {
            name: {
                "interval_ah": [float(x[0]), float(x[-1])],
                "excluded_beginning_ah": float(start - x[0]),
                "excluded_end_ah": float(x[-1] - stop),
                "covered_charge_fraction": float((stop - start) / (x[-1] - x[0])),
            }
            for name, x in (("low_rate", ql), ("high_rate", qh), ("model", qm))
        },
        "temperature_ranges_k": {
            name: [float(min(x)), float(max(x))]
            for name, x in (
                ("low_rate_skin", np.interp(q, ql, low[:, 3])),
                ("high_rate_skin", np.interp(q, qh, high[:, 3])),
                ("model_bulk", np.interp(q, qm, model[:, 4])),
            )
        },
        "temperature_differences_k": {
            name: {
                "minimum_k": float(min(value)),
                "maximum_k": float(max(value)),
                "charge_weighted_mean_k": float(np.trapezoid(value, q) / (stop - start)),
            }
            for name, value in (
                ("high_skin_minus_low_skin", high_temp - low_temp),
                ("model_bulk_minus_high_skin", bulk_temp - high_temp),
                ("model_bulk_minus_low_skin", bulk_temp - low_temp),
            )
        },
        "upper_reference_violation_intervals_ah": violations,
        "upper_reference_violation_details": violation_details,
        "upper_reference_violation_charge_ah": sum(b - a for a, b in violations),
        "windows": windows,
    }
    arrays = np.column_stack((q, low_v, high_v, m, u, *terms.values()))
    return report, arrays
