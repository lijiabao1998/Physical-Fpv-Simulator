"""Evaluate fixed nominal-clock onset queries using only verified saved records."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np

from physical_fpv.onset_response import model_comparison, observed_response, qualify_phase
from physical_fpv.stanford_data import HEADERS

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "stanford-k2-low-rate-onset-records.csv.gz": (
        "8bc38714f31b007654960c22ed40ae3aea36c8f3e0b68fc5f147eed2b3023be4"
    ),
    "stanford-k2-rest-records.csv.gz": (
        "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ),
    "stanford-k2-state-scalars.csv.gz": (
        "188d1ba8e5889fc88e200b47524be4876548bdf43a57bc2e68e5fc776454e21e"
    ),
    "stanford-k2-recovery-evidence.zip": (
        "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
    ),
}


def read_source(source_dir, name):
    content = (source_dir / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != HASHES[name]:
        raise ValueError("Source hash changed")
    return content


def record_rows(content):
    result = []
    for row in csv.DictReader(io.StringIO(gzip.decompress(content).decode())):
        result.append(
            (
                int(row["excel_row"]),
                tuple(
                    [datetime.fromisoformat(row["Date_Time"])]
                    + [float(row[k]) for k in HEADERS[1:]]
                ),
            )
        )
    return result


def inputs_and_timing(rows):
    rest, load = qualify_phase(rows, 4), qualify_phase(rows, 5)

    def to_array(selected):
        return np.array([[r[2], r[4], r[5], r[6] + 273.15] for _, r in selected])

    for selected in (rest, load):
        if any(b[0] != a[0] + 1 for a, b in zip(selected[:-1], selected[1:], strict=True)):
            raise ValueError("Original phase rows dropped or reordered")
    a, b = rest[-1], load[0]
    origin = b[1][1] - b[1][2]
    audits = {}
    for name, selected in (("rest", rest), ("discharge", load)):
        initial = selected[0][1]
        origins = [r[1] - r[2] for _, r in selected]
        audits[name] = {
            "rows_checked": len(selected),
            "max_relative_date_test_discrepancy_s": max(
                abs((r[0] - initial[0]).total_seconds() - (r[1] - initial[1])) for _, r in selected
            ),
            "max_command_origin_deviation_s": max(abs(v - origins[0]) for v in origins),
            "strictly_increasing_dates_test_and_step_clocks": True,
        }
    timing = {
        "phase_clock_audits": audits,
        "last_rest": {
            "excel_row": a[0],
            "date_naive": a[1][0].isoformat(),
            "test_time_s": a[1][1],
            "step_time_s": a[1][2],
        },
        "first_discharge": {
            "excel_row": b[0],
            "date_naive": b[1][0].isoformat(),
            "test_time_s": b[1][1],
            "step_time_s": b[1][2],
        },
        "inferred_discharge_command_origin_test_s": origin,
        "recorded_sample_bracket_test_s": [a[1][1], b[1][1]],
        "recorded_sample_bracket_width_s": b[1][1] - a[1][1],
        "command_origin_after_last_rest_s": origin - a[1][1],
        "physical_switching_time_verified": False,
        "instrument_latency_known": False,
    }
    return to_array(rest), to_array(load), timing, load


def run(source_dir, out):
    started = time.monotonic()
    low_rest, low_load, low_timing, low_rows = inputs_and_timing(
        record_rows(read_source(source_dir, "stanford-k2-low-rate-onset-records.csv.gz"))
    )
    high_rest, high_load, high_timing, high_rows = inputs_and_timing(
        record_rows(read_source(source_dir, "stanford-k2-rest-records.csv.gz"))
    )
    state = np.genfromtxt(
        io.BytesIO(gzip.decompress(read_source(source_dir, "stanford-k2-state-scalars.csv.gz"))),
        delimiter=",",
        names=True,
    )
    model = np.column_stack(
        [state[k] for k in ("time_s", "terminal_voltage_v", "bulk_ocv_v", "bulk_temperature_k")]
    )
    with zipfile.ZipFile(
        io.BytesIO(read_source(source_dir, "stanford-k2-recovery-evidence.zip"))
    ) as archive:
        name = next(n for n in archive.namelist() if n.endswith("/forcing.csv"))
        forcing = np.genfromtxt(io.BytesIO(archive.read(name)), delimiter=",", skip_header=1)
    first = max(low_load[0, 0], high_load[0, 0], model[0, 0])
    if first >= 2:
        raise ValueError("Common initial query must precede2s")
    queries = np.array([first, 2.0, 5.0, 10.0])
    low = observed_response(low_rest, low_load, queries)
    high = observed_response(high_rest, high_load, queries)
    saved = model_comparison(high, model, forcing)
    for response, rows in ((low, low_rows), (high, high_rows)):
        for bracket in response["sampling_brackets"]:
            neighbors = [rows[i] for i in bracket["neighbor_indices"]]
            bracket["excel_rows"] = [i for i, _ in neighbors]
            bracket["naive_dates"] = [r[0].isoformat() for _, r in neighbors]
            bracket["test_times_s"] = [r[1] for _, r in neighbors]
    report = {
        "protocol": "docs/stanford-k2-onset-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-k2-onset-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": HASHES,
        "source_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "analysis_source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("src/physical_fpv/onset_response.py", "scripts/check_stanford_k2_onset.py")
        },
        "low_rate": low,
        "high_rate": high,
        "model": saved,
        "timing": {"low_rate": low_timing, "high_rate": high_timing},
        "temperature_differences_k": {
            "high_skin_minus_low_skin": (np.array(high["skin_k"]) - low["skin_k"]).tolist(),
            "model_bulk_minus_high_skin": (
                np.array(saved["bulk_temperature_k"]) - high["skin_k"]
            ).tolist(),
        },
        "low_minus_high_rest_endpoint_v": low["rest"]["endpoint_v"] - high["rest"]["endpoint_v"],
        "new_downloads": 0,
        "new_dfns_solved": 0,
        "parameters_fitted": False,
        "physical_parameter_update": False,
        "independent_validation": False,
        "historical_1c_voltage_rmse_v": 0.05500305419157363,
        "historical_gate_v": 0.05,
        "historical_1c_passed": False,
        "elapsed_s": time.monotonic() - started,
    }
    if report["elapsed_s"] > 60:
        raise ValueError("Exceeded60s analysis budget")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-k2-onset-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = run(args.source_dir, args.out)
    print(
        json.dumps(
            {
                "times": r["high_rate"]["query_times_s"],
                "rest_difference_v": r["low_minus_high_rest_endpoint_v"],
                "model": r["model"],
                "temperature": r["temperature_differences_k"],
            },
            indent=2,
        )
    )
