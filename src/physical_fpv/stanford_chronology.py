"""Recorded exposure chronology, without fitting or solving a battery model."""

from __future__ import annotations

import re
from datetime import datetime

NAME = re.compile(r"NMC_k1_(0_05|1|2|3|5)C_(05|25|35)degC\.xlsx")


def summarize_chronology(reports: list[dict], manifest: dict) -> dict:
    expected = {f["filename"] for f in manifest["files"]}
    names = [r["source"]["filename"] for r in reports]
    if len(names) != len(set(names)) or set(names) - expected:
        raise ValueError("Duplicate or unselected workbook report")
    intervals = []
    for report in reports:
        filename = report["source"]["filename"]
        match = NAME.fullmatch(filename)
        if match is None:
            raise ValueError("Unqualified sample/rate/temperature filename")
        rate, temperature = match.groups()
        steps = report["contiguous_steps"]
        audit = report["measurement_clock_audit"]
        discharges = [s for s in steps if s["step"] == 5]
        intervals.append(
            {
                "filename": filename,
                "source_sha256": report["source"]["sha256"],
                "nominal_rate_c": float(rate.replace("_", ".")),
                "nominal_ambient_c": int(temperature),
                "start_naive_local": steps[0]["measurement_dates_naive_local"][0],
                "end_naive_local": steps[-1]["measurement_dates_naive_local"][1],
                "clock_qualified": (
                    audit["backwards_date_intervals"] == 0
                    and audit["max_relative_date_test_clock_discrepancy_s"] <= 1.0
                ),
                "measurement_clock_audit": audit,
                "canonical_six_step_sequence": report["canonical_six_step_sequence"],
                "measurement_rows": report["measurement_rows"],
                "discharges": [
                    {
                        "current_a": d["current_a"],
                        "surface_temperature_c": d["surface_temperature_c"],
                        "endpoint_voltage_v": d["endpoint_voltage_v"],
                        "observed_charge_ah": -d["signed_observed_charge_ah"],
                        "duplicate_time_conflicts": d["duplicate_time_conflicts"],
                    }
                    for d in discharges
                ],
            }
        )
    intervals.sort(key=lambda r: (r["start_naive_local"], r["filename"]))
    overlaps = []
    for i, first in enumerate(intervals):
        for second in intervals[i + 1 :]:
            duration = (
                min(
                    datetime.fromisoformat(first["end_naive_local"]),
                    datetime.fromisoformat(second["end_naive_local"]),
                )
                - max(
                    datetime.fromisoformat(first["start_naive_local"]),
                    datetime.fromisoformat(second["start_naive_local"]),
                )
            ).total_seconds()
            if duration > 0:
                overlaps.append(
                    {"files": [first["filename"], second["filename"]], "overlap_s": duration}
                )
    target = next((r for r in intervals if r["filename"] == manifest["target_filename"]), None)
    complete = set(names) == expected
    qualified = complete and all(r["clock_qualified"] for r in intervals) and not overlaps
    earlier = []
    if target is not None:
        earlier = [r for r in intervals if r["end_naive_local"] < target["start_naive_local"]]
    return {
        "dataset_doi": manifest["dataset_doi"],
        "license": manifest["license"],
        "authors": manifest["authors"],
        "target_filename": manifest["target_filename"],
        "expected_files": len(expected),
        "inspected_files": len(names),
        "missing_files": sorted(expected - set(names)),
        "complete": complete,
        "recorded_order_qualified": qualified,
        "ordered_intervals": intervals,
        "overlaps": overlaps,
        "provisional_earlier_files": [r["filename"] for r in earlier],
        "provisional_earlier_high_rate_files": [
            r["filename"] for r in earlier if r["nominal_rate_c"] > 1
        ],
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
