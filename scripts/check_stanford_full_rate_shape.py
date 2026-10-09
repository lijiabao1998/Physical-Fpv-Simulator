"""Compare four complete archived measured discharges without fitting or solving."""

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from physical_fpv.full_rate_shape import evaluate

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "stanford-cross-rate-onset.json": (
        "92bdf117f74347824d3bcfda6553f0b0b66afc914c3152ba7317924836f83382"
    ),
    "stanford-full-rate-shape-source.json": (
        "82f52dcb8e9808eebc1e31d31dbd4063cabe4f35403c6ae67d2993ffd79b42cd"
    ),
    "stanford-k2-low-rate-source.json": (
        "984b83c1f105493f14d5894441c7bcebee2474e2c3904313213e71633ac89eda"
    ),
    "stanford-k1-low-rate-discharge.csv.gz": (
        "ac0587df4bd755f7aeb834f848585228e566a89dd94a5e68512ed810e19e3eff"
    ),
    "stanford-k2-low-rate-discharge.csv.gz": (
        "5c5f0969e411d2be96bcdbb02cfcb397e2fd79d8ad92a26e5466f311d70ae5ef"
    ),
    "stanford-k1-discharge-records.csv.gz": (
        "9d5c84c83a116b2ed032ee638a57664c690866837c925a6fbf62c2e2acfb893c"
    ),
    "stanford-k2-rest-records.csv.gz": (
        "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ),
}


def verified(source_dir, name):
    data = (source_dir / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != HASHES[name]:
        raise ValueError("Source hash changed: " + name)
    return data


def low_rows(content):
    reader = csv.DictReader(io.StringIO(gzip.decompress(content).decode()))
    expected = [
        "excel_row",
        "date_time_naive",
        "step_time_s",
        "raw_current_a",
        "voltage_v",
        "skin_k",
    ]
    if reader.fieldnames != expected:
        raise ValueError("Normalized low-rate schema changed")
    rows = list(reader)
    indices = [int(r["excel_row"]) for r in rows]
    dates = [datetime.fromisoformat(r["date_time_naive"]) for r in rows]
    if len(rows) < 2 or any(b != a + 1 for a, b in zip(indices[:-1], indices[1:], strict=True)):
        raise ValueError("Full discharge rows missing or reordered")
    if any(b <= a for a, b in zip(dates[:-1], dates[1:], strict=True)):
        raise ValueError("Naive dates not strictly increasing")
    x = np.array(
        [
            [
                float(r["step_time_s"]),
                -float(r["raw_current_a"]),
                float(r["voltage_v"]),
                float(r["skin_k"]),
            ]
            for r in rows
        ]
    )
    if (
        max(
            abs((date - dates[0]).total_seconds() - (t - x[0, 0]))
            for date, t in zip(dates, x[:, 0], strict=True)
        )
        > 1
    ):
        raise ValueError("Date/step clock mismatch")
    return x, {
        "first_excel_row": indices[0],
        "last_excel_row": indices[-1],
        "first_date_naive": dates[0].isoformat(),
        "last_date_naive": dates[-1].isoformat(),
        "per_row_test_time_present": False,
        "test_clock_qualification": (
            "Original clock audit in pinned source receipt; no reconstructed test times"
        ),
    }


def run(source_dir, out):
    started = time.monotonic()
    frozen = json.loads(verified(source_dir, "stanford-cross-rate-onset.json"))
    descriptors = {
        name: frozen["comparison"]["cases"][name + "_005c"]["finite_time_apparent_response_ohm"][0]
        for name in ("k1", "k2")
    }
    if frozen["comparison"]["query_times_s"][0] != 1.001:
        raise ValueError("Frozen descriptor query changed")
    spec = importlib.util.spec_from_file_location(
        "frozen_onset_parser", ROOT / "scripts/check_stanford_k2_onset.py"
    )
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    cases, provenance = {}, {}
    receipts = {
        "k1": json.loads(verified(source_dir, "stanford-full-rate-shape-source.json")),
        "k2": json.loads(verified(source_dir, "stanford-k2-low-rate-source.json")),
    }
    for name in ("k1", "k2"):
        low, provenance[name + "_005c"] = low_rows(
            verified(source_dir, "stanford-" + name + "-low-rate-discharge.csv.gz")
        )
        if len(low) != receipts[name]["discharge_rows"]:
            raise ValueError("Complete discharge count changed")
        cases[name + "_005c"] = low
        filename = (
            "stanford-k1-discharge-records.csv.gz"
            if name == "k1"
            else "stanford-k2-rest-records.csv.gz"
        )
        rows = parser.record_rows(verified(source_dir, filename))
        rest, load, timing, selected = parser.inputs_and_timing(rows)
        cases[name + "_1c"] = np.column_stack([load[:, 0], -load[:, 2], load[:, 1], load[:, 3]])
        if float(rest[-1, 1]) != frozen["comparison"]["cases"][name + "_1c"]["rest"]["endpoint_v"]:
            raise ValueError("Source anchor mismatch")
        provenance[name + "_1c"] = {
            "timing": timing,
            "first_excel_row": selected[0][0],
            "last_excel_row": selected[-1][0],
            "first_date_naive": selected[0][1][0].isoformat(),
            "last_date_naive": selected[-1][1][0].isoformat(),
            "per_row_test_time_present": True,
        }
    report = {
        "protocol": "docs/stanford-full-rate-shape-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-full-rate-shape-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": HASHES,
        "analysis_source_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "src/physical_fpv/full_rate_shape.py",
                "src/physical_fpv/contrast_persistence.py",
                "src/physical_fpv/onset_response.py",
                "scripts/check_stanford_full_rate_shape.py",
                "scripts/check_stanford_k2_onset.py",
            )
        },
        "comparison": evaluate(cases, descriptors),
        "record_provenance": provenance,
        "low_rate_source_receipts": receipts,
        "same_cell_low_high_history": frozen["same_cell_record_history"],
        "rest_anchors_v": {
            label: case["rest"]["endpoint_v"]
            for label, case in frozen["comparison"]["cases"].items()
        },
        "dataset_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "new_downloads": 0,
        "new_dfns_solved": 0,
        "parameters_fitted": False,
        "physical_parameter_update": False,
        "blind_holdout": False,
        "physical_or_statistical_acceptance_established": False,
        "historical_voltage_rmse_v": frozen["historical_voltage_rmse_v"],
        "historical_gate_v": 0.05,
        "historical_passed": {"k1": False, "k2": False},
        "numerical_voltage_tolerance_v": 1e-12,
        "numerical_charge_tolerance_ah": 1e-12,
        "elapsed_s": time.monotonic() - started,
    }
    if report["elapsed_s"] > 60:
        raise ValueError("Analysis exceeded60s budget")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-full-rate-shape.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = run(args.source_dir, args.out)
    print(json.dumps({"elapsed_s": r["elapsed_s"], "comparison": r["comparison"]}, indent=2))
