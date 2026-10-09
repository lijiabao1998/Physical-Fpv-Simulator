"""Reproduce a same-query cross-cell contrast from pinned cached records."""

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import time
from pathlib import Path

import numpy as np

from physical_fpv.onset_transfer import cross_cell_comparison

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "stanford-k1-onset-records.csv.gz": (
        "0498bdbf4ef53271a43afceec5e1e084f3832e5319efda752c4f610a997905ef"
    ),
    "stanford-k2-rest-records.csv.gz": (
        "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ),
    "stanford-k1-mesh120-v3.csv.gz": (
        "b88bee993c17315197598f50f19ed72d6023d158b0bb8b1ea8c6e86761a611ba"
    ),
    "stanford-k2-state-scalars.csv.gz": (
        "188d1ba8e5889fc88e200b47524be4876548bdf43a57bc2e68e5fc776454e21e"
    ),
    "stanford-onset-transfer-source.json": (
        "ede4fa5c5524444ea7c4c59c8457cee3de79a20e3827d234ddc7273e61efdff6"
    ),
    "stanford-k2-state-summary.json": (
        "a0edecf428708727ec27bb50549c0ca189609f8bd47d4207cd73265b44fc0b34"
    ),
}


def verified(source_dir, name):
    content = (source_dir / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != HASHES[name]:
        raise ValueError("Source hash changed")
    return content


def parser_module():
    # Reuse the previously reviewed clock/row parser without changing its identity.
    spec = importlib.util.spec_from_file_location(
        "frozen_onset_parser", ROOT / "scripts/check_stanford_k2_onset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(source_dir, out):
    started = time.monotonic()
    parser = parser_module()
    cases = {}
    for name, filename in (
        ("k1", "stanford-k1-onset-records.csv.gz"),
        ("k2", "stanford-k2-rest-records.csv.gz"),
    ):
        cases[name] = parser.inputs_and_timing(parser.record_rows(verified(source_dir, filename)))
    k1data = np.genfromtxt(
        io.BytesIO(gzip.decompress(verified(source_dir, "stanford-k1-mesh120-v3.csv.gz"))),
        delimiter=",",
        names=True,
    )
    k2data = np.genfromtxt(
        io.BytesIO(gzip.decompress(verified(source_dir, "stanford-k2-state-scalars.csv.gz"))),
        delimiter=",",
        names=True,
    )
    models = {
        "k1": np.column_stack([k1data[k] for k in ("time_s", "voltage_v", "temperature_k")]),
        "k2": np.column_stack(
            [k2data[k] for k in ("time_s", "terminal_voltage_v", "bulk_temperature_k")]
        ),
    }
    result = cross_cell_comparison(
        cases["k1"][0], cases["k1"][1], models["k1"], cases["k2"][0], cases["k2"][1], models["k2"]
    )
    for name, case in result["cases"].items():
        rows = cases[name][3]
        case["timing"] = cases[name][2]
        for bracket in case["observed"]["sampling_brackets"]:
            records = [rows[i] for i in bracket["neighbor_indices"]]
            bracket["excel_rows"] = [i for i, _ in records]
            bracket["naive_dates"] = [r[0].isoformat() for _, r in records]
            bracket["test_times_s"] = [r[1] for _, r in records]
    k1source = json.loads(verified(source_dir, "stanford-onset-transfer-source.json"))
    k2summary = json.loads(verified(source_dir, "stanford-k2-state-summary.json"))
    originals = {"k1": k1source["model_input_receipt"], "k2": k2summary["records"]["input.json"]}
    contexts = {}
    for name, data in originals.items():
        contexts[name] = {
            "archived_input_config": data["config"],
            "source_commit": data["source_commit_sha"],
            "actual_compared_curve_mesh_points": 120,
            "input_config_mesh_note": (
                "k1 input starts at80; retained fine curve is independently verified120"
                if name == "k1"
                else "k2 input and compared curve both use120"
            ),
            "current_profile_sha256": data["assumptions"]["current_profile_sha256"],
            "initial_interval_current_assumption_a": data["assumptions"][
                "initial_interval_current_assumption_a"
            ],
            "current_profile_implementation_sha256": data["source_sha256"][
                "src/physical_fpv/current_profile.py"
            ],
            "temperature_observable": data["assumptions"]["temperature_observable"],
        }
    report = {
        "protocol": "docs/stanford-onset-transfer-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-onset-transfer-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": HASHES,
        "analysis_source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "src/physical_fpv/onset_response.py",
                "src/physical_fpv/onset_transfer.py",
                "scripts/check_stanford_k2_onset.py",
                "scripts/check_stanford_onset_transfer.py",
            )
        },
        "source_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "comparison": result,
        "saved_model_context": contexts,
        "previously_viewed_records": True,
        "blind_holdout": False,
        "new_downloads": 0,
        "new_dfns_solved": 0,
        "parameters_fitted": False,
        "physical_parameter_update": False,
        "historical_voltage_rmse_v": {"k1": 0.1914735217065252, "k2": 0.05500305419157363},
        "historical_gate_v": 0.05,
        "historical_passed": {"k1": False, "k2": False},
        "elapsed_s": time.monotonic() - started,
    }
    if report["elapsed_s"] > 60:
        raise ValueError("Exceeded60s analysis budget")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-onset-transfer.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = run(args.source_dir, args.out)
    print(json.dumps({"elapsed_s": r["elapsed_s"], "comparison": r["comparison"]}, indent=2))
