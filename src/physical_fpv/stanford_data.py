"""Checksum-pinned acquisition and protocol inspection of the external M50 source."""

from __future__ import annotations

import hashlib
import io
import math
import statistics
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np

HEADERS = (
    "Date_Time",
    "Test_Time(s)",
    "Step_Time(s)",
    "Step_Index",
    "Voltage(V)",
    "Current(A)",
    "Surface_Temp(degC)",
)
STEP_NAMES = {
    1: "thermal rest",
    2: "CC charge",
    3: "CV charge",
    4: "pre-discharge rest",
    5: "constant-current discharge",
    6: "post-discharge rest",
}
PROTOCOL_SHA256 = "2dd7ce381d3bf48825e27c923761249ec0d9f15df9e18df50e94eec8fc96913b"


def validate_workbook_bytes(content: bytes, entry: dict) -> dict:
    expected = entry["content_details"]["sha256_hash"]
    if len(content) != entry["size"] or hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Workbook length or SHA256 mismatch")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        if any(m.flag_bits & 1 or "vbaproject" in m.filename.lower() for m in members):
            raise ValueError("Encrypted or macro-bearing workbook is unsupported")
        inflated = sum(m.file_size for m in members)
        if inflated > 50_000_000 or len(members) > 1000:
            raise ValueError("Workbook exceeds declared inflated-content limit")
        if any("/externallinks/" in m.filename.lower() for m in members):
            raise ValueError("External workbook links are unsupported")
    return {
        "filename": entry["filename"],
        "bytes": len(content),
        "sha256": expected,
        "inflated_bytes": inflated,
    }


def fetch_pilot(manifest: dict, output_dir: Path) -> list[dict]:
    selected = sorted(manifest["files"], key=lambda f: f["filename"])[:1]
    selected.append(manifest["manufacturer_specification"])
    if sum(f["size"] for f in selected) >= 2_000_000:
        raise ValueError("Pilot exceeds its declared two-file transfer budget")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for entry in selected:
        if Path(entry["filename"]).name != entry["filename"]:
            raise ValueError("Expected a plain source filename")
        path = output_dir / entry["filename"]
        if path.exists():
            content = path.read_bytes()
        else:
            request = urllib.request.Request(
                entry["content_details"]["download_url"],
                headers={"User-Agent": "PhysicalFPVResearch/0.1"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read(entry["size"] + 1)
        report = validate_workbook_bytes(content, entry)
        if not path.exists():
            temporary = path.with_suffix(".xlsx.tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
        reports.append(report)
    return reports


def inspect_records(rows: list[tuple]) -> tuple[dict, np.ndarray | None]:
    """Inspect every contiguous source step; keep the commanded-step clock intact."""
    if not rows:
        raise ValueError("No measurement records")
    for row in rows:
        if len(row) != len(HEADERS) or not isinstance(row[0], datetime):
            raise ValueError("Unsupported date type or measurement schema")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in row[1:]):
            raise ValueError("Nonfinite or missing numerical measurements")
        if int(row[3]) != row[3] or row[3] < 1:
            raise ValueError("Invalid source step index")
    if np.any(np.diff([row[1] for row in rows]) < 0):
        raise ValueError("Source test clock reverses across protocol steps")
    blocks = []
    for index, row in enumerate(rows, start=2):
        if not blocks or blocks[-1]["step"] != row[3]:
            blocks.append({"step": int(row[3]), "records": [], "first_excel_row": index})
        blocks[-1]["records"].append(row)
    summaries, discharge = [], None
    discharge_blocks = [b for b in blocks if b["step"] == 5]
    for block in blocks:
        records = block["records"]
        values = np.asarray([r[1:] for r in records], dtype=float)
        t, step_t, _, voltage, current, temperature = values.T
        dt = np.diff(t)
        if np.any(dt < 0):
            raise ValueError("Reversed source time within a contiguous step")
        duplicate_conflicts = sum(
            t[i] == t[i - 1] and records[i][1:] != records[i - 1][1:]
            for i in range(1, len(records))
        )
        observed_duration = float(t[-1] - t[0])
        current_integral = float(np.trapezoid(current, t))
        mean_current = current_integral / observed_duration if observed_duration > 0 else None
        origins = t - step_t
        summaries.append(
            {
                "step": block["step"],
                "name": STEP_NAMES.get(block["step"], "unmapped"),
                "measurement_rows": len(records),
                "excel_rows_inclusive": [
                    block["first_excel_row"],
                    block["first_excel_row"] + len(records) - 1,
                ],
                "measurement_dates_naive_local": [
                    records[0][0].isoformat(),
                    records[-1][0].isoformat(),
                ],
                "test_time_range_s": [float(t[0]), float(t[-1])],
                "commanded_step_time_range_s": [float(step_t[0]), float(step_t[-1])],
                "observed_duration_s": observed_duration,
                "inferred_commanded_step_start_test_time_s": float(np.median(origins)),
                "clock_relation_max_deviation_s": float(
                    np.max(np.abs(origins - np.median(origins)))
                ),
                "native_interval_s": {
                    "min": float(min(dt)),
                    "median": float(statistics.median(dt)),
                    "max": float(max(dt)),
                }
                if len(dt)
                else None,
                "exact_duplicate_times": int(np.sum(dt == 0)),
                "duplicate_time_conflicts": int(duplicate_conflicts),
                "current_a": {
                    "min": float(min(current)),
                    "max": float(max(current)),
                    "time_weighted_mean": mean_current,
                },
                "endpoint_voltage_v": [float(voltage[0]), float(voltage[-1])],
                "surface_temperature_c": {
                    "initial": float(temperature[0]),
                    "final": float(temperature[-1]),
                    "min": float(min(temperature)),
                    "max": float(max(temperature)),
                },
                "signed_observed_charge_ah": current_integral / 3600,
            }
        )
        if block["step"] == 5 and len(discharge_blocks) == 1:
            # Never reset the first observed time to zero: the initial interval is unobserved.
            discharge = np.column_stack((step_t, current, voltage, temperature + 273.15))
    canonical = [b["step"] for b in blocks] == [1, 2, 3, 4, 5, 6]
    extra = {}
    if len(discharge_blocks) == 1:
        d = next(s for s in summaries if s["step"] == 5)
        if d["observed_duration_s"] <= 0:
            raise ValueError("Discharge needs at least two distinct times")
        delay = d["commanded_step_time_range_s"][0]
        extra = {
            "unobserved_initial_interval_s": delay,
            "recorded_current_a": d["current_a"]["time_weighted_mean"],
            "observed_discharge_charge_ah": -d["signed_observed_charge_ah"],
            "protocol_inferred_initial_charge_if_constant_current_ah": -d["current_a"][
                "time_weighted_mean"
            ]
            * delay
            / 3600,
            "initial_charge_note": (
                "Conditional estimate, not a measured interval or rigorous bound; "
                "not used as a passing gate."
            ),
            "prior_high_rate_exposure": (
                "Unresolved: this workbook does not establish order relative to other experiments."
            ),
        }
    return {
        "measurement_rows": len(rows),
        "canonical_six_step_sequence": canonical,
        "contiguous_steps": summaries,
        "discharge": extra,
        "date_warning": (
            "Measurement timestamps are naive local values; workbook creation "
            "and repository upload dates are different metadata."
        ),
        "source_clock_policy": (
            "Preserve Step_Time(s); model comparison must start on "
            "the actually observed common interval."
        ),
        "model_runs": 0,
        "independent_validation_established": False,
    }, discharge


def inspect_pilot(raw_dir: Path, manifest: dict) -> tuple[dict, np.ndarray | None]:
    import openpyxl

    if not openpyxl.DEFUSEDXML:
        raise RuntimeError("Install pinned optional workbook dependencies, including defusedxml")
    entry = sorted(manifest["files"], key=lambda f: f["filename"])[0]
    path = Path(raw_dir) / entry["filename"]
    integrity = validate_workbook_bytes(path.read_bytes(), entry)
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError(
                "Pilot schema requires an explicitly identified single measurement sheet"
            )
        sheet = workbook.worksheets[0]
        stream = sheet.iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Source column names/units differ from the qualified schema")
        rows = list(stream)
        if any(all(v is None for v in row) for row in rows):
            raise ValueError("Unexpected blank measurement row; inspect before changing selection")
        report, discharge = inspect_records(rows)
        report.update(
            {
                "source": integrity,
                "sheet": sheet.title,
                "columns": list(HEADERS),
                "workbook_created": str(workbook.properties.created),
                "workbook_modified": str(workbook.properties.modified),
                "dataset_doi": manifest["dataset_doi"],
                "dataset_url": manifest["dataset_url"],
                "license_url": manifest["license_url"],
                "license": manifest["license"],
                "authors": manifest["authors"],
                "openpyxl_version": openpyxl.__version__,
            }
        )
        return report, discharge
    finally:
        workbook.close()
