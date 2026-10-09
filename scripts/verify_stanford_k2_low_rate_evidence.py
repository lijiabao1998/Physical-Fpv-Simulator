"""Reproduce the pinned failed coarse experiment and diagnose charge closure.

This is offline saved-data verification. It builds equations but never solves.
"""

import argparse
import bisect
import hashlib
import io
import json
import tempfile
import zipfile
from fractions import Fraction
from pathlib import Path

import casadi
import numpy as np
from compare_stanford_k2_rates import rate_points, require_reproduction
from run_stanford_k2_low_rate_model import digest, runtime_versions, verify_inputs

from physical_fpv.experimental_low_rate import (
    build,
    empirical_report,
    physical_audit,
    prepare,
    validate_output_grid,
    verify_endpoint,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = "f841d0016f9787186f129c5c563226696fd340ab5c6212fcc8c2eb59ae5546cb"
SOURCE_COMMIT = "208d34882acb79b32b48e578575760580675c868"


def archive_bytes(root):
    manifest = json.loads(
        (root / "docs/benchmarks/stanford-k2-low-rate-model-artifact.json").read_text()
    )
    data = []
    if len(manifest["parts"]) != 2:
        raise ValueError("Evidence part count changed")
    for index, part in enumerate(manifest["parts"], 1):
        expected_path = f"docs/benchmarks/stanford-k2-low-rate-model-evidence.zip.{index:03d}"
        if part["path"] != expected_path:
            raise ValueError("Evidence part path changed")
        raw = (root / expected_path).read_bytes()
        if len(raw) != part["bytes"] or hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError("Evidence part hash/size mismatch")
        data.append(raw)
    raw = b"".join(data)
    if len(raw) != 13856564 or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Reassembled evidence archive identity changed")
    return raw


def exact_piecewise_charge(time_s, current_a, queries):
    """Exact rational integral of the supplied binary floating-point PWL law."""
    x = [Fraction(float(value)) for value in time_s]
    y = [Fraction(float(value)) for value in current_a]
    if len(x) != len(y) or len(x) < 2 or any(b <= a for a, b in zip(x, x[1:], strict=False)):
        raise ValueError("Invalid source knots")
    prefix = [Fraction(0)]
    for i in range(len(x) - 1):
        prefix.append(prefix[-1] + (y[i] + y[i + 1]) * (x[i + 1] - x[i]) / 2)
    values = []
    for value in queries:
        query = Fraction(float(value))
        if not x[0] <= query <= x[-1]:
            raise ValueError("Charge oracle query outside source support")
        index = min(bisect.bisect_right(x, query) - 1, len(x) - 2)
        elapsed = query - x[index]
        area = (
            prefix[index]
            + y[index] * elapsed
            + (y[index + 1] - y[index]) * elapsed**2 / (2 * (x[index + 1] - x[index]))
        )
        values.append(float(area / 3600))
    return np.asarray(values)


def closure_diagnostics(prepared, arrays, sim):
    time = arrays["time_s"]
    profile = prepared.profile
    exact = exact_piecewise_charge(profile.time_s, profile.current_a, time)
    analytic = profile.charge_integral_ah(time)
    current = profile.value_at(time)
    sampled_trapezoid = np.r_[0, np.cumsum((current[:-1] + current[1:]) * np.diff(time) / 7200)]
    error = arrays["capacity_ah"] - exact
    index = int(np.argmax(np.abs(error)))
    mask = np.abs(error) > 1e-6
    query = np.unique(np.r_[profile.time_s, prepared.output_time_s])
    symbol = casadi.MX.sym("time")
    expression = sim.built_model.get_processed_variable("Current [A]").to_casadi(t=symbol)
    compiled = casadi.Function("pinned_current", [symbol], [expression])
    actual = np.asarray(compiled(query.reshape(1, -1))).reshape(-1)
    capacity_rhs = next(
        rhs
        for variable, rhs in sim.built_model.rhs.items()
        if variable.name == "Discharge capacity [A.h]"
    )
    compiled_rhs = casadi.Function("capacity_rhs", [symbol], [capacity_rhs.to_casadi(t=symbol)])
    actual_rhs = np.asarray(compiled_rhs(query.reshape(1, -1))).reshape(-1)
    observed_start_error = (arrays["capacity_ah"] - prepared.initial_assumed_charge_ah) - (
        exact - prepared.initial_assumed_charge_ah
    )
    return {
        "oracle": "Exact rational PWL integral of the stored binary floats, rounded once to float",
        "source_integrator_vs_exact_max_ah": float(np.max(np.abs(analytic - exact))),
        "sampled_grid_trapezoid_vs_exact_max_ah": float(np.max(np.abs(sampled_trapezoid - exact))),
        "solver_capacity_vs_exact_max_ah": float(np.max(np.abs(error))),
        "solver_capacity_vs_exact_min_ah": float(error.min()),
        "maximum_error_time_s": float(time[index]),
        "minimum_error_time_s": float(time[np.argmin(error)]),
        "endpoint_error_ah": float(error[-1]),
        "relative_to_endpoint_charge": float(np.max(np.abs(error)) / exact[-1]),
        "failing_sample_count": int(mask.sum()),
        "first_failing_sample_time_s": float(time[mask][0]) if mask.any() else None,
        "last_failing_sample_time_s": float(time[mask][-1]) if mask.any() else None,
        "physical_charge_gate_ah": 1e-6,
        "initial_solver_capacity_ah": float(arrays["capacity_ah"][0]),
        "compiled_current_query_count": len(query),
        "compiled_current_vs_source_max_a": float(np.max(np.abs(actual - profile.value_at(query)))),
        "compiled_current_query_scope": "All source knots and all frozen output queries",
        "compiled_capacity_rhs_vs_current_over_3600_max_ah_per_s": float(
            np.max(np.abs(actual_rhs - profile.value_at(query) / 3600))
        ),
        "consistent_initial_interval_exclusion_max_error_ah": float(
            np.max(np.abs(observed_start_error[time >= prepared.observed[0, 0]]))
        ),
        "cutoff_endpoint_and_interior_both_checked": True,
        "threshold_changed": False,
        "unique_solver_mechanism_identified": False,
    }


def verify(root=ROOT):
    raw = archive_bytes(root)
    with tempfile.TemporaryDirectory(prefix="fpv-low-rate-verify-") as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if (
                len(names) != 62
                or len(set(names)) != 62
                or any(name.startswith("/") or ".." in Path(name).parts for name in names)
            ):
                raise ValueError("Unexpected evidence archive members")
            if any(name.startswith("evidence/mesh120/") for name in names):
                raise ValueError("Unexpected fine-mesh execution")
            archive.extractall(directory)
        manifest = verify_inputs(directory / "inputs")
        if manifest["source_commit"] != SOURCE_COMMIT or manifest["run_id"] != "37948404436":
            raise ValueError("Wrong scientific execution identity")
        upload = json.loads((directory / "upload-receipt.json").read_text())
        if upload["manifest_sha256"] != digest(directory / "inputs/manifest.json"):
            raise ValueError("Prepared input upload identity mismatch")
        ledger = json.loads((directory / "evidence/launch.json").read_text())
        if (
            ledger["stages"] != [{"exit_code": 2, "status": "exited", "mesh": 80}]
            or ledger["status"] != "UNVERIFIED_or_physical_failure_no_further_stage"
            or not 0 < ledger["elapsed_s"] <= 1200
            or ledger["source_commit"] != SOURCE_COMMIT
        ):
            raise ValueError("Unexpected execution ledger")
        stage = directory / "evidence/mesh80"
        report = json.loads((stage / "report.json").read_text())
        if (
            report["battery_dfns_solved"] != 1
            or report["source_sha256"] != manifest["source_sha256"]
            or digest(stage / "scalar-arrays.npz") != report["arrays_sha256"]
            or digest(stage / "final-state.npy") != report["final_state_sha256"]
        ):
            raise ValueError("Saved scientific output identity mismatch")
        with np.load(stage / "scalar-arrays.npz", allow_pickle=False) as packed:
            arrays = {key: packed[key] for key in packed.files}
        prepared = prepare(root)
        validate_output_grid(arrays["time_s"], prepared)
        sim, outputs, config = build(prepared, 80)
        if config != report["config"] or config != manifest["planned_configurations"]["80"]:
            raise ValueError("Rebuilt configuration differs")
        state = np.load(stage / "final-state.npy", allow_pickle=False)
        endpoint_checks = verify_endpoint(sim, arrays, state, outputs)
        require_reproduction(
            report["output_receipt"],
            {
                "requested_grid_preserved": True,
                "true_endpoint_preserved": True,
                "stored_full_history_values": 0,
                "last_state_shape": list(state.shape),
                "endpoint_scalar_checks": endpoint_checks,
            },
        )
        audit = physical_audit(arrays, config, prepared)
        empirical = empirical_report(prepared, arrays, report["empirical"]["termination"], audit)
        require_reproduction(report["physical_audit"], audit)
        require_reproduction(report["empirical"], empirical)
        diagnostics = closure_diagnostics(prepared, arrays, sim)
        return {
            "status": "FAIL_PHYSICAL_CHARGE_CLOSURE_FINE_MESH_NOT_RUN",
            "scientific_qualification_passed": False,
            "source_commit": SOURCE_COMMIT,
            "run_id": 37948404436,
            "archive_sha256": ARCHIVE_SHA,
            "independent_reproduction_passed": True,
            "source_files_verified": len(manifest["source_sha256"]),
            "derived_inputs_verified": len(manifest["derived_input_sha256"]),
            "output_samples": len(arrays["time_s"]),
            "final_state_observables_verified": len(endpoint_checks),
            "ledger": ledger,
            "worker_elapsed_s": report["elapsed_s"],
            "worker_peak_rss_kib": report["peak_rss_kib"],
            "physical_audit": audit,
            "coarse_empirical": empirical,
            "charge_closure_diagnosis": diagnostics,
            "exploratory_unqualified_mesh80_rate_comparison": rate_points(prepared, arrays),
            "mesh120_executed": False,
            "mesh_convergence_available": False,
            "execution_runtime_versions": report["runtime_versions"],
            "verification_runtime_versions": runtime_versions(),
            "new_solver_executions_in_verification": 0,
            "new_source_downloads": 0,
            "parameters_fitted": False,
            "historical_high_rate_rmse_v": 0.05500305419157363,
            "historical_high_rate_gate_passed": False,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = verify()
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")
