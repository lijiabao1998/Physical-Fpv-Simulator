"""Analytic fixed-trajectory shared-term screen on immutable archived inputs."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from physical_fpv.series_loss_compatibility import coefficients, feasible_set, intersect_sets

ROOT = Path(__file__).resolve().parents[1]
INPUT_GZIP_SHA256 = "5ea98848b8759550fb92f21cac74a1edf8ddbc8b284285c3a42cfcd862cd4d8c"
INPUT_JSON_SHA256 = "dc673cd345c38ae67248d18eb5a81f2c10ede6e2c435cd0d7908d7062e758653"
GATE_V = 0.05


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_inputs(path):
    compressed = path.read_bytes()
    if sha(compressed) != INPUT_GZIP_SHA256:
        raise ValueError("Archived normalized input identity changed")
    data = gzip.decompress(compressed)
    if sha(data) != INPUT_JSON_SHA256:
        raise ValueError("Uncompressed input identity changed")
    return json.loads(data)


def check_interval(coef):
    result = feasible_set(coef, GATE_V)
    if result["status"] == "nonempty":
        lo, hi = result["interval_ohm"]
        a, b, c = (coef[k] for k in ("A_a2", "B_v_a", "C_v2"))
        for r in [lo, (lo + hi) / 2, hi]:
            value = a * r**2 - 2 * b * r + c
            if value > GATE_V**2 + 1e-12 or value < -1e-12:
                raise ValueError("Analytic feasible interval failed numerical consistency")
        if abs(a * hi**2 - 2 * b * hi + c - GATE_V**2) > 1e-12:
            raise ValueError("Upper root inconsistent with unchanged gate")
    return result


def run(source, out):
    started = time.monotonic()
    artifact = load_inputs(source)
    results = {}
    for name, cell in artifact["cells"].items():
        t, e, i = (
            np.asarray(cell[k])
            for k in ["time_s", "model_minus_observed_v", "positive_observed_discharge_current_a"]
        )
        if np.any(i <= 0):
            raise ValueError("This discharge screen requires positive observed current")
        full = coefficients(t, e, i)
        if full["interval_s"] != cell["common_interval_s"]:
            raise ValueError("Original common interval changed")
        if abs(full["baseline_rmse_v"] - cell["published_baseline_rmse_v"]) > 1e-12:
            raise ValueError("Original baseline RMSE no longer reproduces")
        quarters = []
        boundaries = np.linspace(*cell["observed_interval_s"], 5)
        for index, (left, right) in enumerate(zip(boundaries[:-1], boundaries[1:], strict=True), 1):
            right = min(right, t[-1])
            if right <= left:
                continue
            part = coefficients(t, e, i, left, right)
            quarters.append(
                {
                    "observed_duration_quarter": index,
                    "coefficients": part,
                    "descriptive_feasible_set": check_interval(part),
                    "additional_acceptance_gate": False,
                }
            )
        results[name] = {
            "coefficients": full,
            "fixed_trajectory_feasible_set": check_interval(full),
            "descriptive_quarters": quarters,
            "original_coverage": {
                k: cell[k]
                for k in [
                    "observed_interval_s",
                    "common_interval_s",
                    "original_model_event_s",
                    "observed_tail_beyond_model_s",
                    "common_observed_duration_fraction",
                ]
            },
            "source_provenance": cell["provenance"],
            "source_inspection": cell["source_inspection"],
            "conditioning": cell["conditioning"],
        }
    shared = intersect_sets([r["fixed_trajectory_feasible_set"] for r in results.values()])
    if all(c["fixed_trajectory_feasible_set"]["status"] == "nonempty" for c in results.values()):
        intervals = [c["fixed_trajectory_feasible_set"]["interval_ohm"] for c in results.values()]
        shared["max_lower_minus_min_upper_ohm"] = max(x[0] for x in intervals) - min(
            x[1] for x in intervals
        )
    result = {
        "protocol": "docs/stanford-series-loss-protocol.md",
        "hashes": {
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for p in [
                source,
                Path(__file__),
                ROOT / "docs/stanford-series-loss-protocol.md",
                ROOT / "src/physical_fpv/series_loss_compatibility.py",
            ]
        },
        "input_json_sha256": INPUT_JSON_SHA256,
        "normalizer_sha256": artifact["normalizer_sha256"],
        "source_attribution": artifact["source_attribution"],
        "gate_rmse_v": GATE_V,
        "primary_decision": "fixed-trajectory shared-term " + shared["status"],
        "shared_feasible_set": shared,
        "cases": results,
        "selected_resistance_ohm": None,
        "identified_physical_resistance": False,
        "new_electrochemical_solves": 0,
        "new_downloads": 0,
        "physical_parameter_update": False,
        "corrected_electrical_validation_pass": False,
        "blind_validation": False,
        "scope": "Post-hoc compatibility on frozen trajectories, not a circuit/DFN resimulation",
        "elapsed_s": time.monotonic() - started,
    }
    if result["elapsed_s"] > 60:
        raise ValueError("60-second analysis budget exceeded")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-series-loss-compatibility.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "docs/benchmarks/stanford-series-loss-inputs.json.gz"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    result = run(args.source, args.out)
    print(
        json.dumps(
            {
                "elapsed_s": result["elapsed_s"],
                "shared": result["shared_feasible_set"],
                "individual": {
                    k: v["fixed_trajectory_feasible_set"] for k, v in result["cases"].items()
                },
            },
            indent=2,
        )
    )
