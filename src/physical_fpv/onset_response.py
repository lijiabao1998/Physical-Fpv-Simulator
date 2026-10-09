"""Rest-referenced finite-time voltage response, with no parameter identification."""

import numpy as np


def curve(values, columns):
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or data.shape[1] != columns or len(data) < 2:
        raise ValueError("Invalid curve schema")
    if not np.isfinite(data).all() or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError("Nonfinite values or nonincreasing clock")
    if data[0, 0] < 0:
        raise ValueError("Negative step clock")
    return data


def query(data, times):
    if not np.isfinite(times).all() or min(times) < data[0, 0] or max(times) > data[-1, 0]:
        raise ValueError("Query outside supported observations")
    return np.column_stack(
        [np.interp(times, data[:, 0], data[:, j]) for j in range(1, data.shape[1])]
    )


def brackets(data, times):
    result = []
    for time in times:
        right = int(np.searchsorted(data[:, 0], time, side="left"))
        if data[right, 0] == time:
            left = right
        else:
            left = right - 1
        result.append(
            {
                "neighbor_indices": [left, right],
                "step_times_s": [float(data[left, 0]), float(data[right, 0])],
                "interval_width_s": float(data[right, 0] - data[left, 0]),
            }
        )
    return result


def rest_summary(rest):
    """Columns are step seconds, voltage V, raw current A, skin K."""
    rest = curve(rest, 4)
    if np.any(rest[:, 2] != 0):
        raise ValueError("Recorded rest current must be zero")
    summaries = {}
    for duration in (10, 60):
        start, stop = rest[-1, 0] - duration, rest[-1, 0]
        if start < rest[0, 0]:
            raise ValueError("Insufficient rest-tail support")
        t = np.unique(np.r_[start, rest[(rest[:, 0] > start) & (rest[:, 0] < stop), 0], stop])
        v = query(rest, t)[:, 0]
        summaries[str(duration)] = {
            "interval_s": [float(start), float(stop)],
            "mean_v": float(np.trapezoid(v, t) / duration),
            "minimum_v": float(min(v)),
            "maximum_v": float(max(v)),
            "endpoint_change_v": float(v[-1] - v[0]),
            "endpoint_change_per_second_v": float((v[-1] - v[0]) / duration),
        }
    return {
        "endpoint_v": float(rest[-1, 1]),
        "endpoint_skin_k": float(rest[-1, 3]),
        "tails_s": summaries,
        "equilibrium_certified": False,
    }


def observed_response(rest, load, times):
    rest, load = curve(rest, 4), curve(load, 4)
    baseline = rest_summary(rest)
    if np.any(load[:, 2] >= 0):
        raise ValueError("Discharge raw current must be negative")
    measured = query(load, times)
    fall = baseline["endpoint_v"] - measured[:, 0]
    return {
        "rest": baseline,
        "query_times_s": [float(t) for t in times],
        "voltage_v": measured[:, 0].tolist(),
        "positive_current_a": (-measured[:, 1]).tolist(),
        "skin_k": measured[:, 2].tolist(),
        "voltage_fall_v": fall.tolist(),
        "finite_time_apparent_response_ohm": (fall / -measured[:, 1]).tolist(),
        "sampling_brackets": brackets(load, times),
        "pure_ohmic_identification": False,
    }


def model_comparison(high_response, model, forcing):
    """Model columns time, terminal V, bulk OCV V, bulk K; forcing time, positive A."""
    model, forcing = curve(model, 4), curve(forcing, 2)
    if model[0, 0] != 0 or np.any(forcing[:, 1] <= 0):
        raise ValueError("Require model initial reference and positive discharge forcing")
    times = np.array(high_response["query_times_s"])
    sampled = query(model, times)
    current = query(forcing, times)[:, 0]
    initial = float(model[0, 2])
    offset = initial - high_response["rest"]["endpoint_v"]
    observed_fall = np.array(high_response["voltage_fall_v"])
    model_fall = initial - sampled[:, 0]
    residual = sampled[:, 0] - np.array(high_response["voltage_v"])
    remaining = residual - offset
    closure = float(max(abs(residual - (offset + observed_fall - model_fall))))
    if closure > 1e-12:
        raise ValueError("Initial-reference arithmetic does not close")
    return {
        "initial_bulk_ocv_v": initial,
        "initial_reference_offset_v": offset,
        "terminal_voltage_v": sampled[:, 0].tolist(),
        "bulk_ocv_v": sampled[:, 1].tolist(),
        "bulk_temperature_k": sampled[:, 2].tolist(),
        "applied_current_a": current.tolist(),
        "model_initial_reference_voltage_fall_v": model_fall.tolist(),
        "finite_time_apparent_response_ohm": (model_fall / current).tolist(),
        "terminal_residual_v": residual.tolist(),
        "residual_minus_constant_offset_v": remaining.tolist(),
        "offset_only_arithmetic_compatible": (abs(remaining) <= 1e-10).tolist(),
        "arithmetic_closure_max_v": closure,
        "physical_initial_state_falsified": False,
        "pure_ohmic_identification": False,
        "sampling_brackets": brackets(model, times),
    }


def qualify_phase(rows, phase):
    selected = [(index, row) for index, row in rows if int(row[3]) == phase]
    if len(selected) < 2:
        raise ValueError("Insufficient phase records")
    values = np.array([row[1:] for _, row in selected], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite phase")
    dates = [row[0] for _, row in selected]
    if any(b <= a for a, b in zip(dates[:-1], dates[1:], strict=True)):
        raise ValueError("Phase dates must strictly increase")
    if (
        np.any(np.diff(values[:, 0]) <= 0)
        or np.any(np.diff(values[:, 1]) <= 0)
        or min(values[:, 1]) < 0
    ):
        raise ValueError("Phase clocks must strictly increase")
    origins = values[:, 0] - values[:, 1]
    if max(abs(origins - origins[0])) > 1e-6:
        raise ValueError("Phase command origin inconsistent")
    if phase == 4 and np.any(values[:, 4] != 0):
        raise ValueError("Nonzero rest current")
    if phase == 5 and np.any(values[:, 4] >= 0):
        raise ValueError("Invalid discharge sign")
    elapsed = np.array([(d - dates[0]).total_seconds() for d in dates])
    if max(abs(elapsed - (values[:, 0] - values[0, 0]))) > 1:
        raise ValueError("Date clock discrepancy")
    return selected
