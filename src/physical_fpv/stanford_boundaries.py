"""Data-only finite differences at four recorded Stanford protocol boundaries.

No samples are interpolated, dropped, fitted, or shifted to a common delay. The
ratios describe recorded pairs; they do not isolate an ohmic/contact resistance.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime

from physical_fpv.stanford_data import HEADERS, STEP_NAMES

BOUNDARY_STEPS = (
    ("charge_start", 1, 2),
    ("cv_stop", 3, 4),
    ("discharge_start", 4, 5),
    ("discharge_stop", 5, 6),
)
CLOCK_TOLERANCE_S = 1.0
SMALL_DELTA_CURRENT_A = 0.5
ARITHMETIC_ABSOLUTE_TOLERANCE_OHM = 1e-12


def _sample(row, excel_row):
    if len(row) != len(HEADERS) or not isinstance(row[0], datetime):
        raise ValueError("Unsupported source record schema or date type")
    if row[0].utcoffset() is not None:
        raise ValueError("Expected source dates with unspecified local timezone")
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        for value in row[1:]
    ):
        raise ValueError("Nonfinite or missing numerical source value")
    if row[3] != int(row[3]):
        raise ValueError("Nonintegral source step")
    if row[2] < 0:
        raise ValueError("Negative source step clock")
    return {
        "excel_row": excel_row,
        "date_naive_local": row[0].isoformat(),
        "test_time_s": float(row[1]),
        "step_time_s": float(row[2]),
        "step": int(row[3]),
        "voltage_v": float(row[4]),
        "current_a": float(row[5]),
        "skin_temperature_c": float(row[6]),
    }


def _phase_context(samples):
    first, last = samples[0], samples[-1]
    origins = [sample["test_time_s"] - sample["step_time_s"] for sample in samples]
    origin = statistics.median(origins)
    deviation = max(abs(value - origin) for value in origins)
    if deviation > CLOCK_TOLERANCE_S:
        raise ValueError("Source Test_Time minus Step_Time origin drifts by more than 1s")
    duration = last["test_time_s"] - first["test_time_s"]
    charge_as = math.fsum(
        (a["current_a"] + b["current_a"]) / 2 * (b["test_time_s"] - a["test_time_s"])
        for a, b in zip(samples[:-1], samples[1:], strict=True)
    )
    return {
        "step": first["step"],
        "name": STEP_NAMES[first["step"]],
        "measurement_rows": len(samples),
        "excel_rows_inclusive": [first["excel_row"], last["excel_row"]],
        "test_time_range_s": [first["test_time_s"], last["test_time_s"]],
        "commanded_step_time_range_s": [first["step_time_s"], last["step_time_s"]],
        "inferred_commanded_step_start_test_time_s": origin,
        "inferred_origin_range_test_time_s": [min(origins), max(origins)],
        "clock_relation_max_deviation_s": deviation,
        "observed_duration_s": duration,
        "unobserved_initial_interval_s": first["step_time_s"],
        "current_a": {
            "min": min(sample["current_a"] for sample in samples),
            "max": max(sample["current_a"] for sample in samples),
            "time_weighted_mean": charge_as / duration if duration else None,
        },
        "signed_observed_charge_ah": charge_as / 3600,
        "charge_integration": "Trapezoidal over recorded within-phase intervals only",
        "endpoint_voltage_v": [first["voltage_v"], last["voltage_v"]],
        "observed_voltage_change_v": last["voltage_v"] - first["voltage_v"],
        "endpoint_skin_temperature_c": [first["skin_temperature_c"], last["skin_temperature_c"]],
    }


def _comparison(pre, post, next_phase):
    di = post["current_a"] - pre["current_a"]
    dv = post["voltage_v"] - pre["voltage_v"]
    small = abs(di) < SMALL_DELTA_CURRENT_A
    ratio = dv / di if di else None
    status = "finite" if di else "undefined_zero_delta_current"
    warnings = ["Small current difference: ill-conditioned ratio"] if small else []
    if ratio is not None and not math.isfinite(ratio):
        ratio, status = None, "nonfinite_derived_ratio"
        warnings.append("Finite input samples produced a nonfinite numerical ratio")
    origin = next_phase["inferred_commanded_step_start_test_time_s"]
    return {
        "pre_sample": pre,
        "post_sample": post,
        "excel_row_pair": [pre["excel_row"], post["excel_row"]],
        "test_time_bracket_s": [pre["test_time_s"], post["test_time_s"]],
        "sample_gap_s": post["test_time_s"] - pre["test_time_s"],
        "next_commanded_step_origin_test_time_s": origin,
        "post_elapsed_since_inferred_commanded_origin_s": post["test_time_s"] - origin,
        "post_recorded_step_time_s": post["step_time_s"],
        "delta_current_a": di,
        "delta_voltage_v": dv,
        "delta_skin_temperature_c": (post["skin_temperature_c"] - pre["skin_temperature_c"]),
        "apparent_transient_ratio_ohm": ratio,
        "ratio_status": status,
        "ill_conditioned": small,
        "warnings": warnings,
        "ratio_is_intrinsic_resistance": False,
    }


def _voltage_trend(samples):
    first, last = samples[0], samples[-1]
    duration = last["test_time_s"] - first["test_time_s"]
    dv = last["voltage_v"] - first["voltage_v"]
    return {
        "first_sample": first,
        "last_sample": last,
        "measurement_rows": len(samples),
        "observed_duration_s": duration,
        "voltage_change_v": dv,
        "endpoint_secant_v_per_s": dv / duration if duration else None,
        "direction": (
            "unavailable"
            if not duration
            else "rising"
            if dv > 0
            else "falling"
            if dv < 0
            else "unchanged"
        ),
    }


def _fixed_r_audit(boundaries):
    primary = [boundary["primary"] for boundary in boundaries]
    ratios = [pair["apparent_transient_ratio_ohm"] for pair in primary]
    finite = [value for value in ratios if value is not None]
    large_delta = [
        pair["apparent_transient_ratio_ohm"]
        for pair in primary
        if not pair["ill_conditioned"] and pair["apparent_transient_ratio_ohm"] is not None
    ]
    complete = len(finite) == len(BOUNDARY_STEPS)
    span = max(finite) - min(finite) if finite else None
    equal = span <= ARITHMETIC_ABSOLUTE_TOLERANCE_OHM if complete else None
    nonnegative = all(value >= 0 for value in finite) if complete else None
    return {
        "hypothesis": (
            "A single fixed nonnegative R alone gives delta_V = R * delta_I at all four pairs, "
            "conditional on unchanged internal voltage within each pair."
        ),
        "primary_ratios": [
            {
                "boundary": boundary["id"],
                "ratio_ohm": pair["apparent_transient_ratio_ohm"],
                "ratio_status": pair["ratio_status"],
                "ill_conditioned": pair["ill_conditioned"],
            }
            for boundary, pair in zip(boundaries, primary, strict=True)
        ],
        "all_four_ratios_available": complete,
        "finite_ratio_count": len(finite),
        "finite_ratio_range_ohm": [min(finite), max(finite)] if finite else None,
        "finite_ratio_span_ohm": span,
        "large_delta_current_finite_ratio_count": len(large_delta),
        "large_delta_current_ratio_range_ohm": (
            [min(large_delta), max(large_delta)] if large_delta else None
        ),
        "large_delta_current_ratio_span_ohm": (
            max(large_delta) - min(large_delta) if large_delta else None
        ),
        "ill_conditioned_boundaries": [
            boundary["id"] for boundary in boundaries if boundary["primary"]["ill_conditioned"]
        ],
        "unavailable_ratio_boundaries": [
            boundary["id"]
            for boundary in boundaries
            if boundary["primary"]["apparent_transient_ratio_ohm"] is None
        ],
        "all_four_ratios_equal_within_computational_tolerance": equal,
        "all_four_ratios_nonnegative": nonnegative,
        "nonnegative_fixed_r_alone_arithmetic_compatible": (
            equal and nonnegative if complete else None
        ),
        "computational_absolute_tolerance_ohm": ARITHMETIC_ABSOLUTE_TOLERANCE_OHM,
        "computational_relative_tolerance": 0.0,
        "tolerance_interpretation": (
            "Floating-point arithmetic comparison only; not measurement uncertainty, "
            "a statistical test, or an empirical acceptance threshold. Available-ratio "
            "range/span is descriptive and is not a resistance bound."
        ),
        "fixed_r_alone_physical_falsification_established": False,
        "physical_interpretation": (
            "Unknown measurement uncertainty, unequal delays, relaxation, SOC and other "
            "state changes prevent statistical physical falsification from these ratios."
        ),
        "fixed_r_component": (
            "A fixed R may be one component of a richer electrochemical response; its "
            "value and contribution are unidentifiable from this diagnostic."
        ),
        "fixed_r_component_ruled_out": False,
        "component_resistance_bounds_established": False,
        "true_ohmic_or_contact_resistance_identified": False,
    }


def inspect_boundaries(rows):
    """Inspect one cell's unmodified, canonical six-step source rows in HEADERS order.

    The caller selects and verifies the approved workbook. Excel provenance assumes
    the header is row 1 and the supplied rows are its complete original data stream.
    Date/test discrepancy is relative to the first row; per-step origin stability
    means maximum absolute deviation from its median, both inclusively within 1s.
    Every row is audited without altering the input; the report exports only the
    selected observations. Phases with fewer than ten rows retain all available
    records rather than fabricating observations.
    """
    samples, blocks, dates = [], [], []
    for excel_row, row in enumerate(rows, 2):
        sample = _sample(row, excel_row)
        if samples:
            previous = samples[-1]
            if sample["test_time_s"] <= previous["test_time_s"]:
                raise ValueError(
                    "Source test clock must be strictly increasing; duplicates rejected"
                )
            if row[0] < dates[-1]:
                raise ValueError("Source date clock reverses")
            if (
                sample["step"] == previous["step"]
                and sample["step_time_s"] < previous["step_time_s"]
            ):
                raise ValueError("Source step clock reverses")
        if not blocks or blocks[-1][0]["step"] != sample["step"]:
            blocks.append([])
        blocks[-1].append(sample)
        samples.append(sample)
        dates.append(row[0])
    if [block[0]["step"] for block in blocks] != list(range(1, 7)):
        raise ValueError("Expected canonical source steps 1, 2, 3, 4, 5, 6 exactly once")
    discrepancy = max(
        abs((date - dates[0]).total_seconds() - (sample["test_time_s"] - samples[0]["test_time_s"]))
        for date, sample in zip(dates, samples, strict=True)
    )
    if discrepancy > CLOCK_TOLERANCE_S:
        raise ValueError("Source date-versus-test clock discrepancy exceeds 1s")
    phases = [_phase_context(block) for block in blocks]
    boundaries = []
    for name, before, after in BOUNDARY_STEPS:
        pre, post = blocks[before - 1], blocks[after - 1]
        comparisons = [_comparison(pre[-1], sample, phases[after - 1]) for sample in post[:10]]
        boundaries.append(
            {
                "id": name,
                "steps": [before, after],
                "last_ten_pre_samples": pre[-10:],
                "first_ten_post_samples": post[:10],
                "primary": comparisons[0],
                "delayed_comparisons": comparisons,
                "pre_phase_context": phases[before - 1],
            }
        )
    return {
        "measurement_rows": len(samples),
        "columns": list(HEADERS),
        "audited_excel_rows_inclusive": [2, len(samples) + 1],
        "recorded_steps": list(range(1, 7)),
        "contiguous_steps": phases,
        "clock_audit": {
            "strictly_increasing_test_time": True,
            "nondecreasing_source_dates": True,
            "max_relative_date_test_clock_discrepancy_s": discrepancy,
            "clock_tolerance_s": CLOCK_TOLERANCE_S,
            "origin_stability_reference": "Per-step median of Test_Time minus Step_Time",
            "timezone": "Unspecified source local timezone; no UTC conversion",
        },
        "boundaries": boundaries,
        "final_rest_context": {
            "phase": phases[-1],
            "whole_observed_rest": _voltage_trend(blocks[-1]),
            "last_ten_samples": _voltage_trend(blocks[-1][-10:]),
            "interpretation": "Endpoint secants only; no trend fit or equilibrium-voltage claim",
        },
        "small_delta_current_threshold_a": SMALL_DELTA_CURRENT_A,
        "conditioning_policy": (
            "abs(delta_I) < 0.5 A is ill-conditioned. Retain finite ratios with a warning; "
            "zero delta_I gives null. This threshold is only a conditioning annotation, "
            "not a physical gate."
        ),
        "current_sign_convention": "Raw source current: charge positive, discharge negative",
        "sampling_policy": (
            "All source rows audited without alteration. Last-pre to first-post is primary; "
            "the same last-pre "
            "sample is compared separately to each of the first ten actual post samples. "
            "Each pair retains its own bracket and delay; no equal-delay assumption."
        ),
        "fixed_r_alone_audit": _fixed_r_audit(boundaries),
        "model_runs": 0,
        "fitting_performed": False,
        "parameter_corrections_performed": False,
        "independent_validation_established": False,
    }
