"""Descriptive source-to-source comparisons of observed Stanford discharges.

Columns are commanded step time (s), raw signed current (A; discharge negative),
voltage (V), and measured skin temperature (K). No source clock is reset, no
unobserved interval is filled, and neither charge nor state of charge is used
to align traces. This module does not import or run a battery model.
"""

from __future__ import annotations

import numpy as np


def _observed_trace(observed: np.ndarray) -> np.ndarray:
    """Require an unambiguous, finite discharge on its original increasing clock."""
    if np.ma.isMaskedArray(observed) and np.any(np.ma.getmaskarray(observed)):
        raise ValueError("Missing or masked observed measurements are unsupported")
    try:
        values = np.asarray(observed)
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected a rectangular numerical observed trace") from exc
    if (
        values.ndim != 2
        or values.shape[1] != 4
        or len(values) < 2
        or values.dtype.kind not in "iuf"
    ):
        raise ValueError("Expected at least two numerical rows with four observed columns")
    values = values.astype(float, copy=False)
    if not np.isfinite(values).all():
        raise ValueError("Observed measurements must all be finite")
    if values[0, 0] < 0 or np.any(np.diff(values[:, 0]) <= 0):
        raise ValueError("Commanded step times must be nonnegative and strictly increasing")
    if np.any(values[:, 1] > 0) or not np.any(values[:, 1] < 0):
        raise ValueError("Raw signed discharge current must be nonpositive and deliver charge")
    return values


def _cell_id(cell_id: str) -> str:
    if not isinstance(cell_id, str) or not cell_id.strip():
        raise ValueError("A nonempty cell identifier is required")
    return cell_id


def _summary(values: np.ndarray, cell_id: str) -> dict:
    time, current, voltage, skin = values.T
    duration = float(time[-1] - time[0])
    charge_as = float(-np.trapezoid(current, time))
    if not np.isfinite(charge_as):
        raise ValueError("Observed delivered-charge integral is not finite")
    return {
        "cell_id": cell_id,
        "measurement_rows": len(time),
        "first_observed_step_time_s": float(time[0]),
        "last_observed_step_time_s": float(time[-1]),
        "observed_duration_s": duration,
        "observed_delivered_charge_ah": charge_as / 3600.0,
        "raw_signed_current": {
            "time_mean_a": -charge_as / duration,
            "min_a": float(np.min(current)),
            "max_a": float(np.max(current)),
        },
        "first_observed_voltage_v": float(voltage[0]),
        "last_observed_voltage_v": float(voltage[-1]),
        "first_observed_skin_temperature_k": float(skin[0]),
        "last_observed_skin_temperature_k": float(skin[-1]),
    }


def summary_discharge(observed: np.ndarray, cell_id: str) -> dict:
    """Summarize the full observed interval, excluding any unmeasured prefix.

    Delivered charge is minus the exact integral of piecewise-linear raw current
    over [first observed step time, last observed step time], in Ah. It is not a
    capacity extrapolation to command time zero or to an inferred cutoff.
    """
    return _summary(_observed_trace(observed), _cell_id(cell_id))


def _difference_metrics(time: np.ndarray, difference: np.ndarray, unit: str) -> dict:
    """Exact time integrals for a difference linear between the union knots."""
    maximum = float(np.max(np.abs(difference)))
    peak = int(np.argmax(np.abs(difference)))  # First knot, including tied plateaus.
    if maximum == 0:
        mean, rmse = 0.0, 0.0
    else:
        weights = np.diff(time) / (time[-1] - time[0])
        scaled = difference / maximum
        left, right = scaled[:-1], scaled[1:]
        mean = maximum * float(np.sum(weights * (left + right) / 2))
        # The integral of a squared line is dt*(a*a + a*b + b*b)/3,
        # not the trapezoidal integral of its squared endpoint values.
        rmse = maximum * float(
            np.sqrt(np.sum(weights * (left * left + left * right + right * right) / 3))
        )
    return {
        f"signed_time_mean_{unit}": mean,
        f"rmse_{unit}": rmse,
        f"max_absolute_{unit}": maximum,
        "first_max_absolute_step_time_s": float(time[peak]),
        f"signed_value_at_first_maximum_{unit}": float(difference[peak]),
    }


def compare_discharge_pair(
    reference: np.ndarray,
    candidate: np.ndarray,
    reference_id: str,
    candidate_id: str,
) -> dict:
    """Describe candidate minus reference on their common observed time interval.

    All actual time knots inside the overlap, plus its endpoints, define the
    integration partition. Both measured traces are linearly interpolated there;
    no extrapolation, smoothing, deduplication, time shift, or normalization occurs.
    Each coverage fraction uses that cell's own full observed duration. Full-trace
    charge and current summaries remain visible even when the overlap is short.

    The first knot attaining the maximum absolute difference is reported when
    there are ties. Results are descriptive measurements, without acceptance gates
    or a statistical outlier classification.
    """
    reference, candidate = _observed_trace(reference), _observed_trace(candidate)
    reference_id, candidate_id = _cell_id(reference_id), _cell_id(candidate_id)
    if reference_id == candidate_id:
        raise ValueError("Pair comparison requires distinct cell identifiers")
    reference_time, candidate_time = reference[:, 0], candidate[:, 0]
    start = max(reference_time[0], candidate_time[0])
    stop = min(reference_time[-1], candidate_time[-1])
    if stop <= start:
        raise ValueError("Observed discharges need a positive-duration common interval")
    common = np.union1d(
        reference_time[(reference_time >= start) & (reference_time <= stop)],
        candidate_time[(candidate_time >= start) & (candidate_time <= stop)],
    )
    reference_summary = _summary(reference, reference_id)
    candidate_summary = _summary(candidate, candidate_id)
    duration = float(stop - start)
    report = {
        "reference_id": reference_id,
        "candidate_id": candidate_id,
        "difference_convention": "candidate minus reference",
        "reference": reference_summary,
        "candidate": candidate_summary,
        "common_observed_interval_s": [float(start), float(stop)],
        "common_observed_duration_s": duration,
        "common_knot_count": len(common),
        "reference_common_duration_fraction": duration / reference_summary["observed_duration_s"],
        "candidate_common_duration_fraction": duration / candidate_summary["observed_duration_s"],
    }
    for column, name, unit in (
        (2, "voltage_difference", "v"),
        (3, "measured_skin_temperature_difference", "k"),
        (1, "raw_signed_current_difference", "a"),
    ):
        difference = np.interp(common, candidate_time, candidate[:, column]) - np.interp(
            common, reference_time, reference[:, column]
        )
        if not np.isfinite(difference).all():
            raise ValueError("Source-to-source differences are not finite")
        report[name] = _difference_metrics(common, difference, unit)
    return report
