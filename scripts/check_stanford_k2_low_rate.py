"""Reproduce a frozen conditional charge comparison from committed source arrays."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
from pathlib import Path

import numpy as np

from physical_fpv.low_rate_reference import compare

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASHES = {
    "stanford-k2-low-rate-discharge.csv.gz": (
        "5c5f0969e411d2be96bcdbb02cfcb397e2fd79d8ad92a26e5466f311d70ae5ef"
    ),
    "stanford-k2-rest-records.csv.gz": (
        "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ),
    "stanford-k2-state-scalars.csv.gz": (
        "188d1ba8e5889fc88e200b47524be4876548bdf43a57bc2e68e5fc776454e21e"
    ),
}


def read_verified(path, expected):
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Source hash changed")
    return gzip.decompress(content)


def load_inputs(source_dir):
    content = {
        name: read_verified(source_dir / name, expected) for name, expected in SOURCE_HASHES.items()
    }
    low_rows = list(
        csv.DictReader(io.StringIO(content["stanford-k2-low-rate-discharge.csv.gz"].decode()))
    )
    if len(low_rows) != 70370 or any(
        int(b["excel_row"]) != int(a["excel_row"]) + 1
        for a, b in zip(low_rows[:-1], low_rows[1:], strict=True)
    ):
        raise ValueError("Original source rows were dropped or reordered")
    low = np.array(
        [
            [float(r[k]) for k in ("step_time_s", "raw_current_a", "voltage_v", "skin_k")]
            for r in low_rows
        ]
    )
    high_rows = list(
        csv.DictReader(io.StringIO(content["stanford-k2-rest-records.csv.gz"].decode()))
    )
    high_rows = [r for r in high_rows if int(float(r["Step_Index"])) == 5]
    high = np.array(
        [
            [
                float(r["Step_Time(s)"]),
                float(r["Current(A)"]),
                float(r["Voltage(V)"]),
                float(r["Surface_Temp(degC)"]) + 273.15,
            ]
            for r in high_rows
        ]
    )
    state = np.genfromtxt(
        io.BytesIO(content["stanford-k2-state-scalars.csv.gz"]), delimiter=",", names=True
    )
    model = np.column_stack(
        [
            state[k]
            for k in (
                "time_s",
                "capacity_ah",
                "terminal_voltage_v",
                "bulk_ocv_v",
                "bulk_temperature_k",
            )
        ]
    )
    return low, high, model


def run(source_dir, out):
    started = time.monotonic()
    low, high, model = load_inputs(source_dir)
    out.mkdir(parents=True, exist_ok=True)
    scenarios = {}
    predictions = {}
    for name, mode in (("recorded_start", False), ("command_start_hold", True)):
        result, arrays = compare(low, high, model, mode)
        scenarios[name] = result
        path = out / f"stanford-k2-low-rate-{name}.csv.gz"
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "charge_ah",
                "low_rate_voltage_v",
                "high_rate_voltage_v",
                "model_terminal_v",
                "model_bulk_ocv_v",
                "static_reference_v",
                "measured_rate_difference_v",
                "model_bulk_to_terminal_v",
                "terminal_residual_v",
            ]
        )
        writer.writerows(arrays)
        path.write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
        predictions[name] = {
            "path": path.name,
            "committed": False,
            "availability": "Regenerate with this script; source arrays and summary are committed",
            "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(arrays),
        }
    report = {
        "protocol": "docs/stanford-k2-low-rate-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-k2-low-rate-protocol.md").read_bytes()
        ).hexdigest(),
        "source_gzip_sha256": SOURCE_HASHES,
        "analysis_source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "src/physical_fpv/low_rate_reference.py",
                "scripts/check_stanford_k2_low_rate.py",
            )
        },
        "source_doi": "10.17632/kxsbr4x3j2.2",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "license": "CC-BY-4.0",
        "new_dfns_solved": 0,
        "parameters_fitted": False,
        "physical_parameter_update": False,
        "blind_holdout": False,
        "independent_ocv_validation": False,
        "historical_1c_voltage_rmse_v": 0.05500305419157363,
        "historical_gate_v": 0.05,
        "historical_1c_passed": False,
        "unknown_history_gap_s": 163788.327,
        "source_rows": {"low_rate": len(low), "high_rate": len(high), "model": len(model)},
        "recorded_discharge_initials": {"low_rate": low[0].tolist(), "high_rate": high[0].tolist()},
        "scenarios": scenarios,
        "predictions": predictions,
        "elapsed_s": time.monotonic() - started,
    }
    if report["elapsed_s"] > 60:
        raise ValueError("Exceeded60s analysis budget")
    (out / "stanford-k2-low-rate-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    report = run(args.source_dir, args.out)
    print(
        json.dumps(
            {
                "elapsed_s": report["elapsed_s"],
                "scenarios": {
                    n: {
                        "common": s["common_charge_interval_ah"],
                        "violation_ah": s["upper_reference_violation_charge_ah"],
                        "full": s["windows"][0],
                    }
                    for n, s in report["scenarios"].items()
                },
            },
            indent=2,
        )
    )
