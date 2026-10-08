"""Summarize original protocol boundaries without inferring instantaneous resistance."""

from __future__ import annotations

import math
from datetime import datetime

from physical_fpv.stanford_data import HEADERS


def record(row, excel_row):
    if len(row) != len(HEADERS) or not isinstance(row[0], datetime):
        raise ValueError("Unsupported source record schema")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in row[1:]):
        raise ValueError("Nonfinite or missing source value")
    if row[3] != int(row[3]):
        raise ValueError("Nonintegral protocol step")
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


def inspect_transitions(rows):
    """Read every row once, retaining boundary records and reported anomalies."""
    blocks = []
    previous = None
    duplicate_times = 0
    duplicate_conflicts = 0
    for number, row in enumerate(rows, 2):
        value = record(row, number)
        if previous is not None:
            dt = value["test_time_s"] - previous["test_time_s"]
            if dt < 0:
                raise ValueError("Source test clock reverses")
            if dt == 0:
                duplicate_times += 1
                duplicate_conflicts += any(
                    value[k] != previous[k]
                    for k in ("step", "step_time_s", "voltage_v", "current_a", "skin_temperature_c")
                )
        if not blocks or blocks[-1]["step"] != value["step"]:
            blocks.append(
                {
                    "step": value["step"],
                    "first": value,
                    "last": value,
                    "rows": 0,
                    "maximum_absolute_current_a": 0.0,
                    "voltage_min_v": value["voltage_v"],
                    "voltage_max_v": value["voltage_v"],
                    "first_ten_samples": [],
                    "last_ten_samples": [],
                }
            )
        block = blocks[-1]
        if value["step_time_s"] < block["last"]["step_time_s"]:
            raise ValueError("Source step clock reverses")
        block["last"] = value
        block["rows"] += 1
        if len(block["first_ten_samples"]) < 10:
            block["first_ten_samples"].append(value)
        block["last_ten_samples"].append(value)
        block["last_ten_samples"] = block["last_ten_samples"][-10:]
        block["maximum_absolute_current_a"] = max(
            block["maximum_absolute_current_a"], abs(value["current_a"])
        )
        block["voltage_min_v"] = min(block["voltage_min_v"], value["voltage_v"])
        block["voltage_max_v"] = max(block["voltage_max_v"], value["voltage_v"])
        previous = value
    steps = [b["step"] for b in blocks]
    if steps not in ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6]):
        raise ValueError("Expected the five-step source prefix and optional recorded final rest")
    transitions = []
    for left, right in zip(blocks[:-1], blocks[1:], strict=True):
        a, b = left["last"], right["first"]
        di, dv = b["current_a"] - a["current_a"], b["voltage_v"] - a["voltage_v"]
        transitions.append(
            {
                "steps": [left["step"], right["step"]],
                "left": a,
                "right": b,
                "source_sample_gap_s": b["test_time_s"] - a["test_time_s"],
                "current_change_a": di,
                "voltage_change_v": dv,
                "apparent_transition_ratio_ohm": dv / di if di else None,
                "ratio_is_intrinsic_resistance": False,
            }
        )
    pre, loaded = blocks[3], blocks[4]
    if pre["maximum_absolute_current_a"] != 0 or loaded["first"]["current_a"] >= 0:
        raise ValueError("The selected transition is not recorded zero-current rest to discharge")
    return {
        "measurement_rows": sum(b["rows"] for b in blocks),
        "recorded_steps": steps,
        "post_discharge_rest_recorded": 6 in steps,
        "blocks": blocks,
        "transitions": transitions,
        "rest_to_discharge": transitions[3],
        "exact_duplicate_times": duplicate_times,
        "duplicate_time_conflicts": duplicate_conflicts,
        "duplicate_policy": (
            "Retain both sides, including equal-time current steps; no deduplication"
        ),
        "interpretation": (
            "Each ratio is the finite difference between adjacent recorded samples, not a fitted "
            "or isolated ohmic/contact resistance. Sampling delay, electrochemical polarization, "
            "temperature, SOC/history and measurement boundary remain confounded."
        ),
    }
