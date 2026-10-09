"""Compare four immutable saved mesh combinations at nine predeclared Ah queries."""

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from compare_stanford_k2_rates import ARCHIVE_SHA, historical_inputs, rate_points
from verify_stanford_k2_mesh120_evidence import archive_bytes, verify

from physical_fpv.contrast_persistence import time_at_charge
from physical_fpv.experimental_low_rate import prepare, verified

ROOT = Path(__file__).resolve().parents[1]
QUERIES_AH = tuple(index / 2 for index in range(1, 10))


def sample(observed, curve, charge):
    """No extrapolation; measured charge excludes the unobserved initial interval."""
    t = time_at_charge(observed, charge)
    time = np.asarray(curve["time_s"], dtype=float)
    if time.ndim != 1 or len(time) < 2 or not np.isfinite(time).all():
        raise ValueError("Invalid model time support")
    if np.any(np.diff(time) <= 0) or not time[0] <= t <= time[-1]:
        raise ValueError("Query outside strictly increasing model support")
    result = {"time_s": t}
    for key in ("voltage_v", "temperature_k", "capacity_ah"):
        value = np.asarray(curve[key], dtype=float)
        if value.shape != time.shape or not np.isfinite(value).all():
            raise ValueError("Invalid saved model observable")
        result["model_" + key] = float(np.interp(t, time, value))
    result["measured_voltage_v"] = float(np.interp(t, observed[:, 0], observed[:, 2]))
    result["measured_skin_k"] = float(np.interp(t, observed[:, 0], observed[:, 3]))
    result["voltage_error_v"] = result["model_voltage_v"] - result["measured_voltage_v"]
    return result


def combinations(low_observed, high_observed, low_curves, high_curves):
    rows = []
    for charge in QUERIES_AH:
        low = {str(mesh): sample(low_observed, curve, charge) for mesh, curve in low_curves.items()}
        high = {
            str(mesh): sample(high_observed, curve, charge) for mesh, curve in high_curves.items()
        }
        if set(low) != {"80", "120"} or set(high) != {"80", "120"}:
            raise ValueError("Exactly two saved meshes per rate are required")
        observed_gap = low["120"]["measured_voltage_v"] - high["120"]["measured_voltage_v"]
        pairs = {}
        for lm, left in low.items():
            for hm, right in high.items():
                model_gap = left["model_voltage_v"] - right["model_voltage_v"]
                discrepancy = model_gap - observed_gap
                closure = discrepancy - (left["voltage_error_v"] - right["voltage_error_v"])
                if not np.isfinite(closure) or abs(closure) > 1e-12:
                    raise ValueError("Voltage gap arithmetic identity failed")
                pairs[f"low{lm}_high{hm}"] = {
                    "model_gap_v": model_gap,
                    "gap_discrepancy_v": discrepancy,
                    "identity_closure_v": closure,
                }
        primary = pairs["low120_high120"]["gap_discrepancy_v"]
        for pair in pairs.values():
            pair["difference_from_primary_v"] = pair["gap_discrepancy_v"] - primary
        values = [pair["gap_discrepancy_v"] for pair in pairs.values()]
        rows.append(
            {
                "conditional_charge_ah": charge,
                "low": low,
                "high": high,
                "observed_gap_v": observed_gap,
                "pairs": pairs,
                "saved_combination_min_v": min(values),
                "saved_combination_max_v": max(values),
                "same_discrepancy_sign_all_combinations": bool(
                    all(v > 0 for v in values) or all(v < 0 for v in values)
                ),
            }
        )
    return rows


def run():
    root = ROOT
    low_verdict = verify(root)
    if low_verdict["qualification"]["joint_mesh_pair_and_dataset_gates_passed"] is not True:
        raise ValueError("Saved low-rate qualification did not reproduce")
    low_raw = archive_bytes(root)
    members = {
        80: "inputs/baseline/evidence/mesh80/scalar-arrays.npz",
        120: "evidence/mesh120/scalar-arrays.npz",
    }
    with zipfile.ZipFile(io.BytesIO(low_raw)) as archive:
        low_bytes = {mesh: archive.read(path) for mesh, path in members.items()}
    low_curves = {}
    for mesh, content in low_bytes.items():
        with np.load(io.BytesIO(content), allow_pickle=False) as arrays:
            low_curves[mesh] = {key: arrays[key] for key in arrays.files}
    high_raw = verified(root / "docs/benchmarks/stanford-k2-recovery-evidence.zip", ARCHIVE_SHA)
    observed, high120, _, high_input = historical_inputs()
    with zipfile.ZipFile(io.BytesIO(high_raw)) as archive:
        prefix = "stanford-k2-recovery/"
        high80 = np.genfromtxt(
            io.BytesIO(archive.read(prefix + "mesh80-timeseries.csv")), delimiter=",", names=True
        )
        high_report = json.loads(archive.read(prefix + "report.json"))
        reports = {
            mesh: json.loads(archive.read(prefix + f"mesh{mesh}-report.json")) for mesh in (80, 120)
        }
    if high_report["spatial_numerical_check"]["passed"] is not True:
        raise ValueError("Historical high-rate numerical qualification missing")
    for mesh, report in reports.items():
        if (
            report["model"]["config"]["mesh_points"] != mesh
            or report["model"]["physical_audit"]["passed"] is not True
            or report["model"]["voltage_cutoff_reached"] is not True
        ):
            raise ValueError("Historical curve mesh or physical provenance changed")
    prepared = prepare(root)
    rows = combinations(prepared.observed, observed, low_curves, {80: high80, 120: high120})
    # Independent existing helper must agree at identical queries for both low meshes.
    for mesh in (80, 120):
        previous_helper = rate_points(prepared, low_curves[mesh])["points"]
        for row, old in zip(rows, previous_helper, strict=True):
            difference = row["pairs"][f"low{mesh}_high120"]["gap_discrepancy_v"]
            if abs(difference - old["model_minus_observed_rate_gap_v"]) > 1e-12:
                raise ValueError("Established rate-point convention changed")
    return {
        "protocol": "docs/stanford-k2-qualified-rate-protocol.md",
        "protocol_sha256": hashlib.sha256(
            (root / "docs/stanford-k2-qualified-rate-protocol.md").read_bytes()
        ).hexdigest(),
        "low_archive_sha256": hashlib.sha256(low_raw).hexdigest(),
        "high_archive_sha256": ARCHIVE_SHA,
        "low_array_sha256": {
            str(mesh): hashlib.sha256(content).hexdigest() for mesh, content in low_bytes.items()
        },
        "low_sources": {
            "80": {
                "source_commit": low_verdict["reference_source_commit"],
                "run_id": low_verdict["reference_run_id"],
            },
            "120": {"source_commit": low_verdict["source_commit"], "run_id": low_verdict["run_id"]},
        },
        "initial_assumed_charge_excluded_ah": {
            "low": prepared.initial_assumed_charge_ah,
            "high": high_input["assumptions"]["assumed_initial_charge_ah"],
        },
        "profile_implementation_sha256": {
            "low_current": hashlib.sha256(
                (root / "src/physical_fpv/current_profile.py").read_bytes()
            ).hexdigest(),
            "high_historical": high_input["source_sha256"]["src/physical_fpv/current_profile.py"],
        },
        "saved_grid_point_counts": {
            "low": {str(mesh): len(curve["time_s"]) for mesh, curve in low_curves.items()},
            "high": {"80": len(high80), "120": len(high120)},
        },
        "grid_construction": {
            "low": "1-second samples plus predeclared Ah-query times and true endpoint",
            "high": "5-second samples plus current-profile knots and true endpoint",
        },
        "high_source_commit": high_input["source_commit_sha"],
        "low_runtime": low_verdict["execution_runtime_versions"],
        "high_recorded_runtime": {
            key: high_input[key + "_version"] for key in ("python", "pybamm", "numpy")
        },
        "low_qualification": low_verdict["qualification"],
        "historical_high_spatial_check": high_report["spatial_numerical_check"],
        "historical_high_rmse_v": reports[120]["voltage_rmse_v"],
        "historical_high_electrical_gates_passed": reports[120]["electrical_gates_passed"],
        "historical_high_config": reports[120]["model"]["config"],
        "points": rows,
        "new_battery_solves": 0,
        "new_source_downloads": 0,
        "parameters_fitted": False,
        "common_Ah_establishes_common_SOC": False,
        "mesh_combination_range_is_uncertainty_bound": False,
        "independent_validation_established": False,
        "unique_physical_cause_identified": False,
        "new_rate_acceptance_threshold_defined": False,
    }


def write_csv(result, path):
    fields = [
        "charge_ah",
        "observed_gap_v",
        "low80_high80_gap_discrepancy_v",
        "low80_high120_gap_discrepancy_v",
        "low120_high80_gap_discrepancy_v",
        "low120_high120_gap_discrepancy_v",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for point in result["points"]:
            writer.writerow(
                {
                    "charge_ah": point["conditional_charge_ah"],
                    "observed_gap_v": point["observed_gap_v"],
                    **{
                        key + "_gap_discrepancy_v": value["gap_discrepancy_v"]
                        for key, value in point["pairs"].items()
                    },
                }
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    write_csv(result, args.out.with_suffix(".csv"))
