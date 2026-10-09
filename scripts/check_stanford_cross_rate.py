"""Frozen four-record finite-time scaling, with no fit or physical solve."""

import argparse
import hashlib
import importlib.util
import json
import time
from datetime import datetime
from pathlib import Path

from physical_fpv.cross_rate_response import compare_rates

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "stanford-cross-rate-acquisition.json": (
        "318a23c3e107df99f7f127b1617c5f9a0a6073df08d1e3d445e5e54a07873591"
    ),
    "stanford-k1-onset-records.csv.gz": (
        "0498bdbf4ef53271a43afceec5e1e084f3832e5319efda752c4f610a997905ef"
    ),
    "stanford-k2-rest-records.csv.gz": (
        "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ),
    "stanford-k1-low-rate-onset-records.csv.gz": (
        "378c2e17939e0721008f29d3053dc3cfd8a9c3524b83f1cf3c32787ed7121a10"
    ),
    "stanford-k2-low-rate-onset-records.csv.gz": (
        "8bc38714f31b007654960c22ed40ae3aea36c8f3e0b68fc5f147eed2b3023be4"
    ),
    "stanford-onset-transfer-source.json": (
        "ede4fa5c5524444ea7c4c59c8457cee3de79a20e3827d234ddc7273e61efdff6"
    ),
    "stanford-cross-rate-source.json": (
        "5c7bb5f8a9c724e9aee63f853ba05c5307dc709456885179de4528554087412a"
    ),
    "stanford-k2-onset-source.json": (
        "030f0615512df8de13de0389d3952e1cbbf838dc4f8faaa26adfe6cdf36f06ca"
    ),
}
FILES = {
    "k1_1c": "stanford-k1-onset-records.csv.gz",
    "k2_1c": "stanford-k2-rest-records.csv.gz",
    "k1_005c": "stanford-k1-low-rate-onset-records.csv.gz",
    "k2_005c": "stanford-k2-low-rate-onset-records.csv.gz",
}


def verified(source_dir, name):
    content = (source_dir / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != HASHES[name]:
        raise ValueError("Source hash changed")
    return content


def run(source_dir, out):
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location(
        "frozen_onset_parser", ROOT / "scripts/check_stanford_k2_onset.py"
    )
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    originals = {
        name: parser.record_rows(verified(source_dir, path)) for name, path in FILES.items()
    }
    parsed = {name: parser.inputs_and_timing(rows) for name, rows in originals.items()}
    result = compare_rates({name: (data[0], data[1]) for name, data in parsed.items()})
    for name, case in result["cases"].items():
        rows = parsed[name][3]
        case["timing"] = parsed[name][2]
        for bracket in case["sampling_brackets"]:
            neighbors = [rows[i] for i in bracket["neighbor_indices"]]
            bracket["excel_rows"] = [i for i, _ in neighbors]
            bracket["naive_dates"] = [r[0].isoformat() for _, r in neighbors]
            bracket["test_times_s"] = [r[1] for _, r in neighbors]
    inspections = {
        name: json.loads(verified(source_dir, path))["source_inspection"]
        for name, path in (
            ("k1_1c", "stanford-onset-transfer-source.json"),
            ("k1_005c", "stanford-cross-rate-source.json"),
            ("k2_005c", "stanford-k2-onset-source.json"),
        )
    }
    ranges = {
        name: [
            data["contiguous_steps"][0]["measurement_dates_naive_local"][0],
            data["contiguous_steps"][-1]["measurement_dates_naive_local"][-1],
        ]
        for name, data in inspections.items()
    }
    ranges["k2_1c"] = [
        originals["k2_1c"][0][1][0].isoformat(),
        originals["k2_1c"][-1][1][0].isoformat(),
    ]
    history = {}
    for cell in ("k1", "k2"):
        low, high = (
            [datetime.fromisoformat(t) for t in ranges[cell + "_005c"]],
            [datetime.fromisoformat(t) for t in ranges[cell + "_1c"]],
        )
        if low[1] <= high[0]:
            prior, later, gap = "005c", "1c", (high[0] - low[1]).total_seconds()
        elif high[1] <= low[0]:
            prior, later, gap = "1c", "005c", (low[0] - high[1]).total_seconds()
        else:
            prior, later, gap = None, None, None
        history[cell] = {
            "record_ranges_naive": {"005c": ranges[cell + "_005c"], "1c": ranges[cell + "_1c"]},
            "earlier_record": prior,
            "later_record": later,
            "unobserved_gap_s": gap,
            "record_ranges_overlap": gap is None,
            "history_replayed": False,
            "timezone": "unspecified",
        }
    acquisition = json.loads(verified(source_dir, "stanford-cross-rate-acquisition.json"))
    protocol_hash = hashlib.sha256(
        (ROOT / "docs/stanford-cross-rate-onset-protocol.md").read_bytes()
    ).hexdigest()
    if acquisition["state"] != "verified" or acquisition["protocol_sha256"] != protocol_hash:
        raise ValueError("Acquisition receipt does not match the frozen protocol")
    report = {
        "protocol": "docs/stanford-cross-rate-onset-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-cross-rate-onset-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": HASHES,
        "acquisition_receipt": "stanford-cross-rate-acquisition.json",
        "analysis_source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "src/physical_fpv/onset_response.py",
                "src/physical_fpv/cross_rate_response.py",
                "scripts/check_stanford_k2_onset.py",
                "scripts/check_stanford_cross_rate.py",
            )
        },
        "source_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "comparison": result,
        "same_cell_record_history": history,
        "new_dfns_solved": 0,
        "parameters_fitted": False,
        "physical_parameter_update": False,
        "blind_holdout": False,
        "historical_voltage_rmse_v": {"k1": 0.1914735217065252, "k2": 0.05500305419157363},
        "historical_gate_v": 0.05,
        "historical_passed": {"k1": False, "k2": False},
        "elapsed_s": time.monotonic() - started,
    }
    if report["elapsed_s"] > 60:
        raise ValueError("Exceeded60s analysis budget")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-cross-rate-onset.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = run(args.source_dir, args.out)
    c = r["comparison"]
    print(
        json.dumps(
            {
                "elapsed_s": r["elapsed_s"],
                "times": c["query_times_s"],
                "transfer": c["transfer"],
                "contrasts": c["cell_contrasts_k1_minus_k2"],
                "predicted_delta_v": c["predicted_low_rate_cell_fall_difference_v"],
                "observed_minus_predicted_delta_v": c[
                    "observed_minus_predicted_low_rate_cell_fall_difference_v"
                ],
                "history": r["same_cell_record_history"],
            },
            indent=2,
        )
    )
