"""Compare one mesh120 result with an immutable, valid mesh80 reference."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_stanford_k2_rates import require_reproduction
from compare_stanford_k2_tolerance import common_query_comparison, verify_upload_receipt
from run_stanford_k2_mesh120 import (
    BASELINE_PINS,
    ROOT,
    assert_mesh_only_change,
    build_refined,
    digest,
    verify_baseline_members,
    verify_inputs,
    write_json,
)
from run_stanford_k2_tolerance import build_tightened
from verify_stanford_k2_low_rate_evidence import closure_diagnostics, exact_piecewise_charge

from physical_fpv.experimental_low_rate import (
    compare_meshes,
    empirical_report,
    physical_audit,
    prepare,
    validate_output_grid,
    verify_endpoint,
)


def verify_stage(stage, prepared, manifest, mesh):
    report = json.loads((stage / "report.json").read_text())
    if (
        report["mesh"] != mesh
        or report["battery_dfns_solved"] != 1
        or report["source_sha256"] != manifest["source_sha256"]
        or report["source_commit"] != manifest["source_commit"]
        or report["runtime_versions"] != manifest["runtime_versions"]
        or digest(stage / "scalar-arrays.npz") != report["arrays_sha256"]
        or digest(stage / "final-state.npy") != report["final_state_sha256"]
    ):
        raise ValueError("Saved stage identity changed")
    with np.load(stage / "scalar-arrays.npz", allow_pickle=False) as packed:
        arrays = {key: packed[key] for key in packed.files}
    validate_output_grid(arrays["time_s"], prepared)
    sim, outputs, config = build_tightened(prepared) if mesh == 80 else build_refined(prepared)
    if config != report["config"] or config != manifest["planned_configurations"][str(mesh)]:
        raise ValueError("Saved stage configuration changed")
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
        raise ValueError("Effective tolerance receipt changed")
    audit = physical_audit(arrays, config, prepared)
    empirical = empirical_report(prepared, arrays, report["empirical"]["termination"], audit)
    require_reproduction(report["physical_audit"], audit)
    require_reproduction(report["empirical"], empirical)
    diagnostics = closure_diagnostics(prepared, arrays, sim)
    signed = arrays["capacity_ah"] - exact_piecewise_charge(
        prepared.profile.time_s, prepared.profile.current_a, arrays["time_s"]
    )
    diagnostics["signed_maximum_ah"] = float(signed.max())
    diagnostics["signed_maximum_time_s"] = float(arrays["time_s"][np.argmax(signed)])
    return (
        arrays,
        report,
        {
            "physical_audit": audit,
            "empirical": empirical,
            "charge_closure_diagnosis": diagnostics,
            "native_endpoint_observables_verified": len(checks),
            "effective_tolerances": effective,
        },
    )


def qualify(mesh_comparison, coarse, fine):
    numerical = bool(mesh_comparison["full_numerical_qualification_passed"])
    empirical = bool(coarse["electrical_gates_passed"] and fine["electrical_gates_passed"])
    thermal_proxy = bool(all(fine["thermal_proxy_gates"].values()))
    return {
        "mesh_pair_numerical_gates_passed": numerical,
        "both_mesh_empirical_electrical_gates_passed": empirical,
        "fine_thermal_proxy_gates_passed": thermal_proxy,
        "joint_mesh_pair_and_dataset_gates_passed": numerical and empirical and thermal_proxy,
        "asymptotic_convergence_or_order_established": False,
        "independent_validation_established": False,
        "universal_model_validity_established": False,
        "scope": "Only this mesh80/120 pair, fixed tolerance and previously viewed record",
    }


def compare(directory):
    manifest = verify_inputs(directory.parent / "inputs")
    upload = verify_upload_receipt(directory, manifest)
    baseline = directory.parent / "inputs/baseline"
    verify_baseline_members(baseline)
    old_manifest = json.loads((baseline / "inputs/manifest.json").read_text())
    old_upload = verify_upload_receipt(baseline / "evidence", old_manifest)
    if (
        old_manifest["source_commit"] != BASELINE_PINS["source_commit"]
        or old_manifest["run_id"] != BASELINE_PINS["run_id"]
        or old_manifest["source_sha256"] != BASELINE_PINS["source_sha256"]
        or manifest["runtime_versions"] != old_manifest["runtime_versions"]
        or manifest["runtime_versions"] != BASELINE_PINS["runtime_versions"]
    ):
        raise ValueError("Reference or runtime identity changed")
    ledger = json.loads((directory / "launch.json").read_text())
    if (
        ledger["maximum_battery_dfns"] != 1
        or len(ledger["stages"]) != 1
        or ledger["stages"][0]["mesh"] != 120
        or ledger["stages"][0]["exit_code"] not in (0, 2)
        or ledger["shared_wall_limit_s"] != 1200
        or ledger["worker_address_space_limit_bytes"] != 4_000_000_000
        or not 0 < ledger["elapsed_s"] <= 1200
        or ledger["source_commit"] != manifest["source_commit"]
        or str(ledger["run_id"]) != str(manifest["run_id"])
        or (directory / "mesh80").exists()
    ):
        raise ValueError("Unexpected single-mesh120 execution ledger")
    old_ledger = json.loads((baseline / "evidence/launch.json").read_text())
    if old_ledger["stages"] != [{"exit_code": 0, "status": "exited", "mesh": 80}]:
        raise ValueError("Reference execution ledger changed")
    prepared = prepare(ROOT)
    coarse, old_report, old = verify_stage(baseline / "evidence/mesh80", prepared, old_manifest, 80)
    fine, report, new = verify_stage(directory / "mesh120", prepared, manifest, 120)
    assert_mesh_only_change(old_report["config"], report["config"])
    if (
        not old["physical_audit"]["passed"]
        or not old["empirical"]["cutoff_qualification_available"]
    ):
        raise ValueError("Previously valid reference is no longer verified")
    expected_code = 0 if new["physical_audit"]["passed"] else 2
    if ledger["stages"][0]["exit_code"] != expected_code:
        raise ValueError("Worker exit differs from physical verdict")
    mesh = compare_meshes(coarse, fine, old_report, report)
    exact = common_query_comparison(coarse, fine, prepared.initial_assumed_charge_ah)
    exact = {
        key.replace("baseline", "mesh80")
        .replace("tightened", "mesh120")
        .replace("descriptive_tolerance_stability", "exact_shared_query_stability"): value
        for key, value in exact.items()
    }
    return {
        "protocol": "stanford-k2-fixed-tolerance-mesh120-v1",
        "source_commit": manifest["source_commit"],
        "run_id": manifest["run_id"],
        "reference_run_id": BASELINE_PINS["run_id"],
        "reference_source_commit": BASELINE_PINS["source_commit"],
        "reference_archive_sha256": BASELINE_PINS["archive_sha256"],
        "reference_selected_members_verified": len(BASELINE_PINS["members"]),
        "input_upload_receipt": upload,
        "reference_upload_receipt": old_upload,
        "execution_runtime_versions": manifest["runtime_versions"],
        "mesh80": old,
        "mesh120": new,
        "original_mesh_comparison": mesh,
        "mesh_comparison_sampling": (
            "Union of saved common-support times including true endpoint; linear interpolation"
        ),
        "exact_shared_query_diagnostics": exact,
        "qualification": qualify(mesh, old["empirical"], new["empirical"]),
        "ledger": ledger,
        "worker_elapsed_s": report["elapsed_s"],
        "worker_peak_rss_kib": report["peak_rss_kib"],
        "new_battery_solves_in_comparison": 0,
        "new_source_downloads": 0,
        "parameters_fitted": False,
        "historical_high_rate_rmse_v": 0.05500305419157363,
        "historical_high_rate_gate_passed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = compare(args.directory)
    write_json(args.directory / "mesh-comparison.json", result)
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(
        0 if result["qualification"]["joint_mesh_pair_and_dataset_gates_passed"] else 2
    )
