"""Offline comparison of one fixed-mesh tightened-tolerance diagnostic."""

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from compare_stanford_k2_rates import require_reproduction
from run_stanford_k2_tolerance import (
    ROOT,
    build_tightened,
    digest,
    verify_inputs,
    write_json,
)
from verify_stanford_k2_low_rate_evidence import (
    ARCHIVE_SHA,
    archive_bytes,
    closure_diagnostics,
    exact_piecewise_charge,
)
from verify_stanford_k2_low_rate_evidence import (
    verify as verify_baseline,
)

from physical_fpv.experimental_low_rate import (
    empirical_report,
    physical_audit,
    prepare,
    validate_output_grid,
    verify_endpoint,
)


def common_query_comparison(baseline, tightened, initial_charge):
    """Exact shared queries only; true endpoints are compared separately."""
    for arrays in (baseline, tightened):
        t = arrays["time_s"]
        if len(t) < 2 or not np.isfinite(t).all() or not np.all(np.diff(t) > 0):
            raise ValueError("Invalid comparison time grid")
        for name in ("voltage_v", "temperature_k", "capacity_ah"):
            if arrays[name].shape != t.shape or not np.isfinite(arrays[name]).all():
                raise ValueError("Invalid comparison scalar values")
    shared, left, right = np.intersect1d(
        baseline["time_s"], tightened["time_s"], assume_unique=True, return_indices=True
    )
    if len(shared) < 2 or shared[0] != 0:
        raise ValueError("Insufficient exact shared queries")
    dv = float(np.max(np.abs(baseline["voltage_v"][left] - tightened["voltage_v"][right])))
    dt = float(np.max(np.abs(baseline["temperature_k"][left] - tightened["temperature_k"][right])))
    q = [float(a["capacity_ah"][-1] - initial_charge) for a in (baseline, tightened)]
    if min(q) <= 0:
        raise ValueError("Invalid observed-start endpoint capacity")
    dq = abs(q[1] - q[0]) / q[1]
    cutoffs = [abs(float(a["voltage_v"][-1]) - 2.5) <= 1e-6 for a in (baseline, tightened)]
    flags = {
        "maximum_voltage_difference_le_5mv": dv <= 0.005,
        "maximum_temperature_difference_le_0_1k": dt <= 0.1,
        "endpoint_capacity_relative_difference_le_1percent": dq <= 0.01,
        "both_endpoint_voltages_at_cutoff": all(cutoffs),
    }
    return {
        "exact_shared_samples": len(shared),
        "exact_shared_interval_s": [float(shared[0]), float(shared[-1])],
        "maximum_voltage_difference_v": dv,
        "maximum_temperature_difference_k": dt,
        "earlier_actual_event_endpoint_s": float(
            min(baseline["time_s"][-1], tightened["time_s"][-1])
        ),
        "baseline_endpoint_s": float(baseline["time_s"][-1]),
        "tightened_endpoint_s": float(tightened["time_s"][-1]),
        "signed_cutoff_time_difference_s": float(tightened["time_s"][-1] - baseline["time_s"][-1]),
        "baseline_endpoint_observed_start_charge_ah": q[0],
        "tightened_endpoint_observed_start_charge_ah": q[1],
        "endpoint_capacity_relative_difference": dq,
        "descriptive_tolerance_stability_flags": flags,
        "descriptive_tolerance_stability_passed": all(flags.values()),
        "spatial_convergence_claimed": False,
    }


def verify_upload_receipt(directory, manifest):
    receipt = json.loads((directory.parent / "upload-receipt.json").read_text())
    artifact = receipt.get("artifact_id")
    if (
        type(artifact) is not int
        or artifact <= 0
        or receipt.get("verified_not_expired") is not True
        or str(receipt.get("run_id")) != str(manifest["run_id"])
        or receipt.get("source_commit") != manifest["source_commit"]
        or receipt.get("manifest_sha256") != digest(directory.parent / "inputs/manifest.json")
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", receipt.get("artifact_sha256", ""))
    ):
        raise ValueError("Durable pre-solve upload receipt identity changed")
    return receipt


def compare(directory):
    manifest = verify_inputs(directory.parent / "inputs")
    upload = verify_upload_receipt(directory, manifest)
    baseline_result = verify_baseline()
    with zipfile.ZipFile(io.BytesIO(archive_bytes(ROOT))) as archive:
        with np.load(
            io.BytesIO(archive.read("evidence/mesh80/scalar-arrays.npz")), allow_pickle=False
        ) as packed:
            baseline = {key: packed[key] for key in packed.files}
    ledger = json.loads((directory / "launch.json").read_text())
    if (
        ledger["maximum_battery_dfns"] != 1
        or len(ledger["stages"]) != 1
        or ledger["stages"][0]["mesh"] != 80
        or ledger["stages"][0]["exit_code"] not in (0, 2)
        or ledger["shared_wall_limit_s"] != 1200
        or ledger["worker_address_space_limit_bytes"] != 4_000_000_000
        or not 0 < ledger["elapsed_s"] <= 1200
        or ledger["source_commit"] != manifest["source_commit"]
        or str(ledger["run_id"]) != str(manifest["run_id"])
        or (directory / "mesh120").exists()
    ):
        raise ValueError("Unexpected single-solve execution ledger")
    stage = directory / "mesh80"
    report = json.loads((stage / "report.json").read_text())
    if (
        report["battery_dfns_solved"] != 1
        or report["source_sha256"] != manifest["source_sha256"]
        or report["source_commit"] != manifest["source_commit"]
        or report["runtime_versions"] != manifest["runtime_versions"]
        or digest(stage / "scalar-arrays.npz") != report["arrays_sha256"]
        or digest(stage / "final-state.npy") != report["final_state_sha256"]
    ):
        raise ValueError("Saved scientific output identity mismatch")
    with np.load(stage / "scalar-arrays.npz", allow_pickle=False) as packed:
        arrays = {key: packed[key] for key in packed.files}
    prepared = prepare(ROOT)
    validate_output_grid(arrays["time_s"], prepared)
    sim, outputs, config = build_tightened(prepared)
    if config != report["config"] or config != manifest["planned_configurations"]["80"]:
        raise ValueError("Tightened configuration differs")
    state = np.load(stage / "final-state.npy", allow_pickle=False)
    checks = verify_endpoint(sim, arrays, state, outputs)
    require_reproduction(
        report["output_receipt"],
        {
            "requested_grid_preserved": True,
            "true_endpoint_preserved": True,
            "stored_full_history_values": 0,
            "last_state_shape": list(state.shape),
            "endpoint_scalar_checks": checks,
        },
    )
    effective = report["effective_tolerances"]
    if effective != json.loads((stage / "effective-tolerances.json").read_text()) or (
        effective["rtol"] != 1e-8
        or effective["expanded_atol_min"] != 1e-8
        or effective["expanded_atol_max"] != 1e-8
        or effective["expanded_atol_count"] != sim.built_model.len_rhs_and_alg
        or effective["model_level_atol_override"] is not False
    ):
        raise ValueError("Effective tolerance evidence changed")
    if manifest["runtime_versions"] != manifest["baseline_runtime_versions"]:
        raise ValueError("Baseline and diagnostic runtimes differ")
    audit = physical_audit(arrays, config, prepared)
    empirical = empirical_report(prepared, arrays, report["empirical"]["termination"], audit)
    require_reproduction(report["physical_audit"], audit)
    require_reproduction(report["empirical"], empirical)
    expected_code = 0 if audit["passed"] else 2
    if ledger["stages"][0]["exit_code"] != expected_code:
        raise ValueError("Worker exit differs from physical verdict")
    diagnostics = closure_diagnostics(prepared, arrays, sim)
    signed = arrays["capacity_ah"] - exact_piecewise_charge(
        prepared.profile.time_s, prepared.profile.current_a, arrays["time_s"]
    )
    diagnostics["solver_capacity_vs_exact_signed_max_ah"] = float(signed.max())
    diagnostics["signed_maximum_error_time_s"] = float(arrays["time_s"][np.argmax(signed)])
    diagnostics["maximum_scope"] = (
        "All prescribed saved samples and true endpoint; not continuous extrema"
    )
    comparison = common_query_comparison(baseline, arrays, prepared.initial_assumed_charge_ah)
    comparison["both_voltage_cutoff_events_reached"] = bool(
        baseline_result["coarse_empirical"]["cutoff_qualification_available"]
        and empirical["cutoff_qualification_available"]
    )
    comparison["descriptive_tolerance_stability_passed"] = bool(
        comparison["descriptive_tolerance_stability_passed"]
        and comparison["both_voltage_cutoff_events_reached"]
    )
    old = baseline_result["physical_audit"]["charge_integral_error_ah"]
    new = audit["charge_integral_error_ah"]
    improved = new < old
    closure_passed = new <= 1e-6
    valid_physical_cutoff = bool(audit["passed"] and empirical["cutoff_qualification_available"])
    narrow_support = improved and closure_passed and valid_physical_cutoff
    return {
        "protocol": "stanford-k2-fixed-mesh-tolerance-v1",
        "source_commit": manifest["source_commit"],
        "run_id": manifest["run_id"],
        "baseline_archive_sha256": ARCHIVE_SHA,
        "effective_tolerances": effective,
        "execution_runtime_versions": manifest["runtime_versions"],
        "baseline_verdict_preserved": baseline_result["status"],
        "baseline_charge_closure_max_abs_error_ah": old,
        "tightened_charge_closure_max_abs_error_ah": new,
        "closure_error_decreased": improved,
        "unchanged_charge_closure_gate_passed": closure_passed,
        "narrow_charge_hypothesis_supported": narrow_support,
        "diagnostic_evidence_valid_physical_cutoff": valid_physical_cutoff,
        "joint_charge_and_tolerance_stability_supported": bool(
            narrow_support and comparison["descriptive_tolerance_stability_passed"]
        ),
        "diagnostic_status": "complete_fixed_mesh_diagnostic"
        if valid_physical_cutoff
        else "FAILED_or_UNVERIFIED_physical_or_cutoff_evidence",
        "input_upload_receipt": upload,
        "full_physical_audit": audit,
        "coarse_empirical": empirical,
        "charge_closure_diagnosis": diagnostics,
        "same_mesh_tolerance_comparison": comparison,
        "spatial_convergence_available": False,
        "overall_model_qualification_passed": False,
        "qualification_limit": "No mesh120 at tightened tolerance; no spatial convergence claim",
        "historical_high_rate_rmse_v": 0.05500305419157363,
        "historical_high_rate_gate_passed": False,
        "new_source_downloads": 0,
        "new_solver_executions_in_comparison": 0,
        "final_state_observables_verified": len(checks),
        "ledger": ledger,
        "worker_elapsed_s": report["elapsed_s"],
        "worker_peak_rss_kib": report["peak_rss_kib"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = compare(args.directory)
    write_json(args.directory / "tolerance-comparison.json", result)
    print(json.dumps(result, indent=2, allow_nan=False))
