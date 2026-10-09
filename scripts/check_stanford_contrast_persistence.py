"""Reproduce a frozen descriptive continuation using only archived measurements."""

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import time
from pathlib import Path

import numpy as np

from physical_fpv.contrast_persistence import evaluate

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "stanford-cross-rate-onset.json": (
        "92bdf117f74347824d3bcfda6553f0b0b66afc914c3152ba7317924836f83382"
    ),
    "stanford-k1-discharge-records.csv.gz": (
        "9d5c84c83a116b2ed032ee638a57664c690866837c925a6fbf62c2e2acfb893c"
    ),
    "stanford-contrast-persistence-source.json": (
        "80b684ee2257f8134ba95f3a7643c562c160a1fb9534657f6f9ef22d5cd63df3"
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
    "stanford-k2-state-summary.json": (
        "a0edecf428708727ec27bb50549c0ca189609f8bd47d4207cd73265b44fc0b34"
    ),
}


def verified(source_dir, name):
    data = (source_dir / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != HASHES[name]:
        raise ValueError("Source hash changed: " + name)
    return data


def run(source_dir, out):
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location(
        "frozen_onset_parser", ROOT / "scripts/check_stanford_k2_onset.py"
    )
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    frozen = json.loads(verified(source_dir, "stanford-cross-rate-onset.json"))
    if frozen["comparison"]["query_times_s"][0] != 1.001:
        raise ValueError("Frozen query changed")
    cases, timing, descriptors, anchors = {}, {}, {}, {}
    model_names = {"k1": "stanford-k1-mesh120-v3.csv.gz", "k2": "stanford-k2-state-scalars.csv.gz"}
    for name, filename in (
        ("k1", "stanford-k1-discharge-records.csv.gz"),
        ("k2", "stanford-k2-rest-records.csv.gz"),
    ):
        rest, load, timing[name], _ = parser.inputs_and_timing(
            parser.record_rows(verified(source_dir, filename))
        )
        measured = np.column_stack([load[:, 0], -load[:, 2], load[:, 1], load[:, 3]])
        anchors[name] = float(rest[-1, 1])
        frozen_case = frozen["comparison"]["cases"][name + "_005c"]
        descriptors[name] = frozen_case["finite_time_apparent_response_ohm"][0]
        if anchors[name] != frozen["comparison"]["cases"][name + "_1c"]["rest"]["endpoint_v"]:
            raise ValueError("Rest anchor differs from frozen evidence")
        data = np.genfromtxt(
            io.BytesIO(gzip.decompress(verified(source_dir, model_names[name]))),
            delimiter=",",
            names=True,
        )
        columns = (
            ("time_s", "voltage_v", "temperature_k")
            if name == "k1"
            else ("time_s", "terminal_voltage_v", "bulk_temperature_k")
        )
        model = np.column_stack([data[k] for k in columns])
        cases[name] = measured, model
        timing[name]["conditional_charge_origin"] = {
            "step_time_s": float(measured[0, 0]),
            "naive_timestamp": timing[name]["first_discharge"]["date_naive"],
            "omitted_initial_command_interval_s": [0.0, float(measured[0, 0])],
            "missing_interval_charge_imputed": False,
        }
    comparison = evaluate(cases, descriptors, anchors)
    source = json.loads(verified(source_dir, "stanford-contrast-persistence-source.json"))
    k2 = json.loads(verified(source_dir, "stanford-k2-state-summary.json"))
    model_context = {"k1": source["model_input_receipt"], "k2": k2["records"]["input.json"]}
    report = {
        "protocol": "docs/stanford-contrast-persistence-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/stanford-contrast-persistence-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": HASHES,
        "analysis_source_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "src/physical_fpv/contrast_persistence.py",
                "scripts/check_stanford_contrast_persistence.py",
                "scripts/check_stanford_k2_onset.py",
                "src/physical_fpv/onset_response.py",
            )
        },
        "comparison": comparison,
        "timing": timing,
        "same_cell_low_high_history": frozen["same_cell_record_history"],
        "archived_model_context": model_context,
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
        raise ValueError("Exceeded analysis time budget")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-contrast-persistence.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "docs/benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    result = run(args.source_dir, args.out)
    print(
        json.dumps({"elapsed_s": result["elapsed_s"], "comparison": result["comparison"]}, indent=2)
    )
