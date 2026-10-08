"""Recorded exposure chronology, without fitting or solving a battery model."""

from __future__ import annotations

import math
import re
from copy import deepcopy
from datetime import datetime

NAME = re.compile(r"NMC_(k[126])_(0_05|1|2|3|5)C_(05|25|35)degC\.xlsx")


def _bounded_nonnegative(value, maximum: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= maximum
    )


def _numeric_range(value) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(_bounded_nonnegative(v, float("inf")) for v in value):
        return None
    return tuple(value) if value[0] <= value[1] else None


def _date_range(value) -> tuple[datetime, datetime] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        start, end = (datetime.fromisoformat(v) for v in value)
    except (TypeError, ValueError):
        return None
    if start.tzinfo is not None or end.tzinfo is not None or start > end:
        return None
    return start, end


def _phase_clocks_qualified(steps: list[dict]) -> bool:
    previous_test_end = None
    first_date = first_test = None
    for step in steps:
        source_time = _numeric_range(step.get("commanded_step_time_range_s"))
        test_time = _numeric_range(step.get("test_time_range_s"))
        dates = _date_range(step.get("measurement_dates_naive_local"))
        if (
            not _bounded_nonnegative(step.get("backwards_step_clock_intervals"), 0)
            or not _bounded_nonnegative(step.get("negative_step_clock_records"), 0)
            or not _bounded_nonnegative(step.get("clock_relation_max_deviation_s"), 1)
            or not _bounded_nonnegative(step.get("exact_duplicate_times"), 0)
            or not _bounded_nonnegative(step.get("duplicate_time_conflicts"), 0)
            or source_time is None
            or test_time is None
            or dates is None
        ):
            return False
        if previous_test_end is not None and test_time[0] <= previous_test_end:
            return False
        if first_date is None:
            first_date, first_test = dates[0], test_time[0]
        if any(
            abs((date - first_date).total_seconds() - (test - first_test)) > 1
            for date, test in zip(dates, test_time, strict=True)
        ):
            return False
        test_duration = test_time[1] - test_time[0]
        # Each origin can lie on either side of the reported median. Do not turn
        # the 1 s deviation tolerance into an unintended 1 s peak-to-peak gate.
        origin_span = abs(test_duration - (source_time[1] - source_time[0]))
        if origin_span > 2 * step["clock_relation_max_deviation_s"] + 1e-9:
            return False
        previous_test_end = test_time[1]
    return bool(steps)


def summarize_chronology(reports: list[dict], manifest: dict, *, cell_id: str = "k1") -> dict:
    """Summarize one explicitly selected cell, preserving source identities and phases.

    ``recorded_order_qualified`` retains the legacy k1 date-order meaning. It is
    insufficient for an exposure claim. ``history_qualified`` additionally needs
    the target, source-step clocks, source integrity, supported complete phases,
    and strict target boundaries. Missing support is never evidence of absence.
    """
    if cell_id not in {"k1", "k2", "k6"}:
        raise ValueError("Unselected cell: expected k1, k2 or k6")
    entries = {f["filename"]: f for f in manifest["files"]}
    expected = set(entries)
    if len(entries) != len(manifest["files"]):
        raise ValueError("Duplicate selected workbook in manifest")
    for filename in expected:
        match = NAME.fullmatch(filename)
        if match is None or match[1] != cell_id:
            raise ValueError("Unqualified or cross-cell selected workbook filename")
    target_filename = manifest.get("target_filename")
    if target_filename is not None:
        match = NAME.fullmatch(target_filename)
        if match is None or match[1] != cell_id:
            raise ValueError("Unqualified or cross-cell target filename")
    names = [r["source"]["filename"] for r in reports]
    if len(names) != len(set(names)) or set(names) - expected:
        raise ValueError("Duplicate or unselected workbook report")
    intervals = []
    bounds = {}
    for report in reports:
        filename = report["source"]["filename"]
        _, rate, temperature = NAME.fullmatch(filename).groups()
        steps = report.get("contiguous_steps") or []
        audit = report.get("measurement_clock_audit") or {}
        phase_dates = [_date_range(s.get("measurement_dates_naive_local")) for s in steps]
        dates_qualified = bool(steps) and all(d is not None for d in phase_dates)
        if dates_qualified:
            dates_qualified = all(
                first[1] <= second[0]
                for first, second in zip(phase_dates, phase_dates[1:], strict=False)
            )
        raw_start = steps[0].get("measurement_dates_naive_local", [None, None]) if steps else []
        raw_end = steps[-1].get("measurement_dates_naive_local", [None, None]) if steps else []
        start = raw_start[0] if isinstance(raw_start, (list, tuple)) and raw_start else None
        end = raw_end[-1] if isinstance(raw_end, (list, tuple)) and raw_end else None
        bounds[filename] = _date_range([start, end]) if dates_qualified else None
        expected_hash = entries[filename].get("content_details", {}).get("sha256_hash")
        source_hash = report["source"].get("sha256")
        integrity = (
            isinstance(expected_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None
            and source_hash == expected_hash
        )
        if "size" in entries[filename]:
            integrity = integrity and report["source"].get("bytes") == entries[filename]["size"]
        sequence = [s.get("step") for s in steps]
        discharges = [s for s in steps if s.get("step") == 5]
        intervals.append(
            {
                "filename": filename,
                "cell_id": cell_id,
                "source_sha256": source_hash,
                "source_integrity_qualified": integrity,
                "nominal_rate_c": float(rate.replace("_", ".")),
                "nominal_ambient_c": int(temperature),
                "start_naive_local": start,
                "end_naive_local": end,
                "clock_qualified": (
                    dates_qualified
                    and _bounded_nonnegative(audit.get("backwards_date_intervals"), 0)
                    and _bounded_nonnegative(
                        audit.get("max_relative_date_test_clock_discrepancy_s"), 1
                    )
                ),
                "measurement_clock_audit": deepcopy(audit),
                "source_step_clock_qualified": _phase_clocks_qualified(steps),
                "canonical_six_step_sequence": report.get("canonical_six_step_sequence", False),
                "source_step_sequence": sequence,
                "source_protocol_qualified": sequence in ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6]),
                "final_rest_recorded": 6 in sequence,
                "measurement_rows": report.get("measurement_rows"),
                # Keep every actual phase, including current, charge, voltage and temperature.
                # A missing final rest is never fabricated or treated as zero duration.
                "contiguous_steps": deepcopy(steps),
                "discharges": [
                    {
                        "current_a": deepcopy(d.get("current_a")),
                        "measurement_dates_naive_local": deepcopy(
                            d.get("measurement_dates_naive_local")
                        ),
                        "commanded_step_time_range_s": deepcopy(
                            d.get("commanded_step_time_range_s")
                        ),
                        "surface_temperature_c": deepcopy(d.get("surface_temperature_c")),
                        "endpoint_voltage_v": deepcopy(d.get("endpoint_voltage_v")),
                        "observed_charge_ah": (
                            -d["signed_observed_charge_ah"]
                            if isinstance(d.get("signed_observed_charge_ah"), (int, float))
                            else None
                        ),
                        "duplicate_time_conflicts": d.get("duplicate_time_conflicts"),
                    }
                    for d in discharges
                ],
            }
        )
    intervals.sort(
        key=lambda r: (
            bounds[r["filename"]][0] if bounds[r["filename"]] else datetime.max,
            r["filename"],
        )
    )
    overlaps = []
    touching = []
    for i, first in enumerate(intervals):
        for second in intervals[i + 1 :]:
            first_bounds, second_bounds = bounds[first["filename"]], bounds[second["filename"]]
            if first_bounds is None or second_bounds is None:
                continue
            duration = (
                min(first_bounds[1], second_bounds[1]) - max(first_bounds[0], second_bounds[0])
            ).total_seconds()
            if duration > 0:
                overlaps.append(
                    {"files": [first["filename"], second["filename"]], "overlap_s": duration}
                )
            elif duration == 0:
                touching.append({"files": [first["filename"], second["filename"]]})
    target = next((r for r in intervals if r["filename"] == target_filename), None)
    target_bounds = bounds.get(target_filename)
    complete = set(names) == expected
    qualified = complete and all(r["clock_qualified"] for r in intervals) and not overlaps
    earlier = []
    for interval in intervals:
        own_bounds = bounds[interval["filename"]]
        if interval is target:
            relation = "target"
        elif target is None or not interval["clock_qualified"] or not target["clock_qualified"]:
            relation = "unresolved"
        elif own_bounds[1] < target_bounds[0]:
            relation = "recorded before target"
        elif own_bounds[0] > target_bounds[1]:
            relation = "recorded after target"
        else:
            # This includes a shared endpoint: strict before/after cannot be established.
            relation = "overlapping target"
        interval["relation_to_target"] = relation
        if (
            own_bounds is not None
            and target_bounds is not None
            and own_bounds[1] < target_bounds[0]
        ):
            earlier.append(interval)
    reasons = []
    if not complete:
        reasons.append("missing_selected_workbooks")
    if target is None:
        reasons.append("missing_target_workbook")
    for interval in intervals:
        filename = interval["filename"]
        for field in (
            "clock_qualified",
            "source_step_clock_qualified",
            "source_integrity_qualified",
            "source_protocol_qualified",
        ):
            if not interval[field]:
                reasons.append(f"{filename}: {field} is false or supporting audit is missing")
    if overlaps:
        reasons.append("same_cell_workbook_intervals_overlap")
    if any(r["relation_to_target"] == "overlapping target" for r in intervals):
        reasons.append("ambiguous_target_boundary")
    history_qualified = bool(expected) and not reasons
    earlier_high_rate = [r["filename"] for r in earlier if r["nominal_rate_c"] >= 2]
    return {
        "dataset_doi": manifest["dataset_doi"],
        "license": manifest["license"],
        "authors": manifest["authors"],
        "cell_id": cell_id,
        "target_filename": target_filename,
        "expected_files": len(expected),
        "inspected_files": len(names),
        "missing_files": sorted(expected - set(names)),
        "complete": complete,
        "recorded_order_qualified": qualified,
        "recorded_order_qualification_scope": (
            "Legacy date/test-clock ordering only; exposure classification requires "
            "history_qualified"
        ),
        "history_qualified": history_qualified,
        "history_unresolved_reasons": reasons,
        "ordered_intervals": intervals,
        "overlaps": overlaps,
        "touching_boundaries": touching,
        "provisional_earlier_files": [r["filename"] for r in earlier],
        "provisional_earlier_high_rate_files": earlier_high_rate,
        "qualified_earlier_high_rate_files": earlier_high_rate if history_qualified else None,
        "recorded_prior_high_rate_exposure": bool(earlier_high_rate) if history_qualified else None,
        "fresh_target_established": False,
        "unrecorded_history": "Unknown manufacturing, storage and unpublished exposure history",
        "termination_note": (
            "The publication specifies 2.5V discharge cutoff and 75C emergency skin-temperature "
            "stop. Endpoint voltage and temperature are retained; a low-capacity high-rate "
            "record may be thermally censored. No termination cause is inferred from filename."
        ),
        "model_runs": 0,
        "independent_validation_established": False,
    }
