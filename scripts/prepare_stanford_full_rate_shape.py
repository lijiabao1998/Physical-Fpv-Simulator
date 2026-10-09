"""Normalize all low-rate discharge rows from a checksum-pinned local workbook."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import openpyxl

from physical_fpv.stanford_data import inspect_workbook

ROOT = Path(__file__).resolve().parents[1]
FILENAME = "NMC_k1_0_05C_25degC.xlsx"


def validate_clocks(inspection):
    phase = next(p for p in inspection["contiguous_steps"] if p["step"] == 5)
    for key in (
        "exact_duplicate_times",
        "duplicate_time_conflicts",
        "backwards_step_clock_intervals",
        "negative_step_clock_records",
    ):
        if phase[key] != 0:
            raise ValueError("Discharge clocks are not strictly qualified")
    if not 0 <= phase["clock_relation_max_deviation_s"] <= 1e-6:
        raise ValueError("Discharge command origin is inconsistent")
    audit = inspection["measurement_clock_audit"]
    if (
        audit["backwards_date_intervals"] != 0
        or audit["date_test_clock_jumps_above_1s"] != 0
        or not 0 <= audit["max_relative_date_test_clock_discrepancy_s"] <= 1
    ):
        raise ValueError("Naive date/test clocks are not qualified")


def prepare(raw_dir, out):
    manifest = json.loads((ROOT / "data/stanford-chronology-manifest.json").read_text())
    entry = next(e for e in manifest["files"] if e["filename"] == FILENAME)
    inspection, discharge = inspect_workbook(raw_dir, entry, manifest)
    if not inspection["canonical_six_step_sequence"] or discharge is None:
        raise ValueError("Canonical discharge phase required")
    validate_clocks(inspection)
    # No invalid-row filtering: inspect_workbook has validated every original row.
    from physical_fpv.low_rate_reference import charge_axis

    charge_axis(discharge)
    workbook = openpyxl.load_workbook(raw_dir / FILENAME, read_only=True, data_only=True)
    stream = workbook.worksheets[0].iter_rows(values_only=True)
    next(stream)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["excel_row", "date_time_naive", "step_time_s", "raw_current_a", "voltage_v", "skin_k"]
    )
    count = 0
    prior_date = None
    for index, row in enumerate(stream, start=2):
        if row[3] == 5:
            if prior_date is not None and row[0] <= prior_date:
                raise ValueError("Discharge naive dates must strictly increase")
            prior_date = row[0]
            writer.writerow([index, row[0].isoformat(), row[2], row[5], row[4], row[6] + 273.15])
            count += 1
    workbook.close()
    assert count == len(discharge)
    content = buffer.getvalue().encode()
    compressed = gzip.compress(content, mtime=0)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-k1-low-rate-discharge.csv.gz").write_bytes(compressed)
    report = {
        "dataset_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "source_inspection": inspection,
        "discharge_rows": count,
        "normalized_csv_sha256": hashlib.sha256(content).hexdigest(),
        "normalized_gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        "normalized_gzip_bytes": len(compressed),
        "normalizer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "stanford-full-rate-shape-source.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    result = prepare(args.raw_dir, args.out)
    print(json.dumps({k: v for k, v in result.items() if k != "source_inspection"}, indent=2))
