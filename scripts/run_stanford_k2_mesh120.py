"""Prepare or execute one distinct frozen mesh120 spatial diagnostic.

No workflow trigger accompanies this implementation. Defaults never solve.
"""

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "docs/stanford-k2-mesh120-protocol.md"
BASELINE_PINS = json.loads((ROOT / "docs/benchmarks/stanford-k2-mesh120-baseline.json").read_text())
DEDUPLICATED_OLD_ARCHIVES = {
    "docs/benchmarks/stanford-k2-low-rate-model-evidence.zip.001",
    "docs/benchmarks/stanford-k2-low-rate-model-evidence.zip.002",
}
SOURCE_FILES = tuple(sorted(set(BASELINE_PINS["source_sha256"]) - DEDUPLICATED_OLD_ARCHIVES)) + (
    PROTOCOL,
    "docs/experiments/stanford-k2-mesh120.workflow.yml",
    "scripts/run_stanford_k2_mesh120.py",
    "scripts/compare_stanford_k2_mesh120.py",
    "scripts/verify_stanford_k2_tolerance_evidence.py",
    "docs/benchmarks/stanford-k2-mesh120-baseline.json",
    "docs/benchmarks/stanford-k2-tolerance-artifact.json",
)
WALL_LIMIT_S = 1200
MEMORY_LIMIT_BYTES = 4_000_000_000


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_versions():
    return {
        "python": platform.python_version(),
        **{
            name: importlib.metadata.version(name)
            for name in (
                "pybamm",
                "numpy",
                "casadi",
                "scipy",
                "pybammsolvers",
            )
        },
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_digests():
    names = set(SOURCE_FILES) | {
        str(path.relative_to(ROOT)) for path in (ROOT / "src/physical_fpv").glob("*.py")
    }
    for version in (1, 2):
        workflow = f".github/workflows/k2-low-rate-model-20261009-v{version}.yml"
        if (ROOT / workflow).exists():
            names.add(workflow)
    workflow = ".github/workflows/k2-mesh120-20261009-v1.yml"
    if (ROOT / workflow).exists():
        names.add(workflow)
    return {name: digest(ROOT / name) for name in sorted(names)}


def build_refined(data, mesh=120):
    """Reuse frozen equations; change only the two unused solver tolerances."""
    from physical_fpv.experimental_low_rate import build

    if mesh != 120:
        raise ValueError("Only one reviewed mesh120 diagnostic")
    sim, outputs, original = build(data, mesh)
    if hasattr(sim.built_model, "atol") or hasattr(sim.solver, "_setup"):
        raise ValueError("Unexpected model tolerance override or preconfigured solver")
    if sim.solver.rtol != 1e-7 or sim.solver.atol != 1e-7:
        raise ValueError("Baseline solver tolerances changed")
    if original["tolerance"] != 1e-7:
        raise ValueError("Baseline configuration changed")
    sim.solver.rtol = 1e-8
    sim.solver.atol = 1e-8
    metadata = {**original, "tolerance": 1e-8}
    if sim.solver.rtol != 1e-8 or sim.solver.atol != 1e-8:
        raise ValueError("Tightened tolerances not applied")
    return sim, outputs, metadata


def effective_tolerances(sim):
    import numpy as np

    actual = np.asarray(sim.solver._setup["atol"])
    if (
        hasattr(sim.built_model, "atol")
        or actual.shape != (sim.built_model.len_rhs_and_alg,)
        or not np.all(actual == 1e-8)
        or sim.solver.rtol != 1e-8
    ):
        raise ValueError("Effective solver tolerance differs from reviewed values")
    return {
        "rtol": 1e-8,
        "expanded_atol_min": float(actual.min()),
        "expanded_atol_max": float(actual.max()),
        "expanded_atol_count": len(actual),
        "model_level_atol_override": False,
        "scope": "Solver state error weights; not a global physical error bound",
    }


def assert_mesh_only_change(baseline, refined):
    ignored = {"mesh_points", "finite_witness_field_sizes"}
    if (
        baseline["mesh_points"] != 80
        or refined["mesh_points"] != 120
        or baseline["tolerance"] != 1e-8
        or refined["tolerance"] != 1e-8
        or {k: v for k, v in baseline.items() if k not in ignored}
        != {k: v for k, v in refined.items() if k not in ignored}
    ):
        raise ValueError("Physics or tolerances changed beyond reviewed mesh refinement")


def verify_baseline_members(directory):
    for name, expected in BASELINE_PINS["members"].items():
        path = directory / name
        if path.stat().st_size != expected["bytes"] or digest(path) != expected["sha256"]:
            raise ValueError("Pinned baseline member changed")
    return BASELINE_PINS["members"]


def extract_baseline(directory):
    import io
    import zipfile

    from verify_stanford_k2_tolerance_evidence import archive_bytes

    raw = archive_bytes(ROOT)
    if hashlib.sha256(raw).hexdigest() != BASELINE_PINS["archive_sha256"]:
        raise ValueError("Wrong complete baseline archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        original = json.loads(archive.read("inputs/manifest.json"))
        expected_fields = {
            "run_id": BASELINE_PINS["run_id"],
            "source_commit": BASELINE_PINS["source_commit"],
            "source_sha256": BASELINE_PINS["source_sha256"],
            "derived_input_sha256": BASELINE_PINS["derived_input_sha256"],
            "runtime_versions": BASELINE_PINS["runtime_versions"],
        }
        if any(original[k] != v for k, v in expected_fields.items()) or (
            original["planned_configurations"]["80"] != BASELINE_PINS["config"]
        ):
            raise ValueError("Complete baseline manifest differs from prospective pins")
        for name, expected in BASELINE_PINS["source_sha256"].items():
            if hashlib.sha256(archive.read("inputs/files/" + name)).hexdigest() != expected:
                raise ValueError("Archived baseline source identity changed")
        for name, expected in BASELINE_PINS["members"].items():
            content = archive.read(name)
            if (
                len(content) != expected["bytes"]
                or hashlib.sha256(content).hexdigest() != expected["sha256"]
            ):
                raise ValueError("Archived baseline member identity changed")
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    verify_baseline_members(directory)
    return {
        "archive_sha256": BASELINE_PINS["archive_sha256"],
        "archived_source_files_verified": len(BASELINE_PINS["source_sha256"]),
        "selected_members_persisted": len(BASELINE_PINS["members"]),
        "full_prior_archives_remain_in_repository": True,
        "recursive_archive_duplication": False,
    }


def prepare_inputs(out):
    import numpy as np
    import pybamm

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.experimental_low_rate import prepare

    if out.exists():
        raise ValueError("Prepared input directory already exists")
    data = prepare(ROOT)
    hashes = source_digests()
    out.mkdir(parents=True)
    for name in hashes:
        target = out / "files" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != hashes[name]:
            raise ValueError("Input copy identity mismatch")
    np.savetxt(
        out / "forcing.csv",
        np.column_stack([data.profile.time_s, data.profile.current_a]),
        delimiter=",",
        header="time_s,positive_discharge_current_a",
        comments="",
    )
    np.savetxt(
        out / "observed.csv",
        data.observed,
        delimiter=",",
        header="time_s,positive_current_a,voltage_v,skin_temperature_k",
        comments="",
    )
    np.save(out / "output-times.npy", data.output_time_s, allow_pickle=False)
    configurations = {}
    for mesh in (120,):
        sim, _, metadata = build_refined(data, mesh)
        parameters = {
            key: (
                {
                    "kind": "pinned_measured_interpolant",
                    "forcing_sha256": data.profile.fingerprint_sha256,
                }
                if key == "Current function [A]"
                else inspect.getsource(value)
                if callable(value)
                else value
            )
            for key, value in sim.parameter_values.items()
        }
        write_json(out / f"parameters-mesh{mesh}.json", parameters)
        configurations[str(mesh)] = metadata
        del sim
    write_evidence_attribution(out, ["stanford2021", "oregan2022_parameters"])
    manifest = {
        "status": "prepared_no_battery_solve",
        "prepared_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "source_sha256": hashes,
        "derived_input_sha256": {
            name: digest(out / name)
            for name in (
                "forcing.csv",
                "observed.csv",
                "output-times.npy",
                "parameters-mesh120.json",
            )
        },
        "source_metadata": data.metadata,
        "pybamm_version": pybamm.__version__,
        "numpy_version": np.__version__,
        "runtime_versions": runtime_versions(),
        "planned_meshes": [120],
        "planned_configurations": configurations,
        "baseline_configurations": {"80": BASELINE_PINS["config"]},
        "fixed_tolerances": {"rtol": 1e-8, "atol": 1e-8},
        "maximum_battery_dfns": 1,
        "shared_wall_limit_s": WALL_LIMIT_S,
        "worker_address_space_limit_bytes": MEMORY_LIMIT_BYTES,
        "no_new_source_downloads": True,
        "parameter_fitting": False,
    }
    extraction = extract_baseline(out / "baseline")
    for name, expected in BASELINE_PINS["source_sha256"].items():
        if name not in DEDUPLICATED_OLD_ARCHIVES and hashes.get(name) != expected:
            raise ValueError("Frozen baseline source identity changed")
    for name, actual in manifest["derived_input_sha256"].items():
        baseline_name = "parameters-mesh80.json" if name == "parameters-mesh120.json" else name
        if BASELINE_PINS["derived_input_sha256"].get(baseline_name) != actual:
            raise ValueError("Frozen derived input identity changed")
    assert_mesh_only_change(BASELINE_PINS["config"], configurations["120"])
    manifest["baseline_runtime_versions"] = BASELINE_PINS["runtime_versions"]
    manifest["baseline_source_commit"] = BASELINE_PINS["source_commit"]
    manifest["baseline_run_id"] = BASELINE_PINS["run_id"]
    manifest["baseline_selected_members"] = BASELINE_PINS["members"]
    manifest["baseline_preparation_receipt"] = extraction
    write_json(out / "manifest.json", manifest)
    return manifest


def verify_inputs(prepared_dir):
    manifest = json.loads((prepared_dir / "manifest.json").read_text())
    if manifest["source_sha256"] != source_digests():
        raise ValueError("Source changed after input preparation")
    for name, expected in manifest["source_sha256"].items():
        if digest(prepared_dir / "files" / name) != expected:
            raise ValueError("Persisted source copy changed")
    for name, expected in manifest["derived_input_sha256"].items():
        if digest(prepared_dir / name) != expected:
            raise ValueError("Persisted derived input changed")
    if (
        manifest["planned_meshes"] != [120]
        or manifest["maximum_battery_dfns"] != 1
        or manifest["fixed_tolerances"] != {"rtol": 1e-8, "atol": 1e-8}
        or manifest["shared_wall_limit_s"] != WALL_LIMIT_S
        or manifest["worker_address_space_limit_bytes"] != MEMORY_LIMIT_BYTES
        or manifest["baseline_configurations"]["80"] != BASELINE_PINS["config"]
        or manifest["baseline_selected_members"] != BASELINE_PINS["members"]
    ):
        raise ValueError("Reviewed execution bounds changed")
    assert_mesh_only_change(BASELINE_PINS["config"], manifest["planned_configurations"]["120"])
    verify_baseline_members(prepared_dir / "baseline")
    return manifest


def validate_managed_launch(prepared_dir, upload_receipt, environ):
    manifest = verify_inputs(prepared_dir)
    if manifest["runtime_versions"] != manifest["baseline_runtime_versions"]:
        raise ValueError("Execution runtime differs from the archived baseline")
    if manifest["runtime_versions"] != runtime_versions():
        raise ValueError("Execution runtime differs from persisted input runtime")
    if environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("Only the first reviewed managed attempt may execute")
    receipt = json.loads(upload_receipt.read_text())
    if (
        not str(receipt.get("artifact_id", "")).isdigit()
        or int(receipt["artifact_id"]) <= 0
        or receipt.get("verified_not_expired") is not True
    ):
        raise ValueError("Successful durable input upload required")
    for key, env_name in (("run_id", "GITHUB_RUN_ID"), ("source_commit", "GITHUB_SHA")):
        if (
            not environ.get(env_name)
            or str(receipt.get(key)) != environ[env_name]
            or str(manifest.get(key)) != environ[env_name]
        ):
            raise ValueError("Upload/launch identity mismatch")
    if receipt.get("manifest_sha256") != digest(prepared_dir / "manifest.json"):
        raise ValueError("Uploaded input manifest differs")
    return manifest


def worker(args):
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    import numpy as np

    from physical_fpv.experimental_low_rate import (
        collect_outputs,
        empirical_report,
        physical_audit,
        prepare,
    )

    manifest = validate_managed_launch(args.prepared, args.upload_receipt, os.environ)
    remaining = args.deadline_monotonic - time.monotonic()
    if not math.isfinite(remaining) or not 0 < remaining <= WALL_LIMIT_S:
        raise ValueError("Invalid or exhausted shared scientific deadline")
    # Enforce the same absolute deadline even if the supervising parent disappears.
    signal.setitimer(signal.ITIMER_REAL, remaining)
    if args.mesh != 120 or args.out.exists():
        raise ValueError("Unreviewed or duplicate worker stage")
    args.out.mkdir(parents=True)
    started = time.monotonic()
    write_json(args.out / "stage.json", {"status": "building", "mesh": args.mesh})
    data = prepare(ROOT)
    sim, outputs, metadata = build_refined(data, args.mesh)
    if metadata != manifest["planned_configurations"][str(args.mesh)]:
        raise ValueError("Built configuration differs from durable reviewed inputs")
    write_json(
        args.out / "model-input.json",
        {
            "config": metadata,
            "source_sha256": source_digests(),
            "source_commit": os.environ.get("GITHUB_SHA"),
            "source_metadata": data.metadata,
        },
    )
    write_json(
        args.out / "stage.json",
        {"status": "solving", "mesh": args.mesh, "maximum_battery_dfns_in_this_worker": 1},
    )
    # Setup never advances a battery trajectory; check the effective vector before solve.
    sim.solver.set_up(sim.built_model)
    effective = effective_tolerances(sim)
    write_json(args.out / "effective-tolerances.json", effective)
    # The only battery solve call in the worker. The parent owns the shared timer.
    solution = sim.solve([0.0, float(data.output_time_s[-1])], t_interp=data.output_time_s)
    if effective_tolerances(sim) != effective:
        raise ValueError("Effective tolerances changed during solve")
    np.save(args.out / "final-state.npy", np.asarray(solution.last_state.y), allow_pickle=False)
    try:
        arrays, output_receipt = collect_outputs(sim, solution, outputs, data)
    except Exception as error:
        # Preserve available solver evidence, explicitly unverified, without retrying.
        partial = {"time_s": np.asarray(solution.t, dtype=float)}
        failures = {}
        for column, name in outputs.items():
            try:
                partial[column] = np.asarray(solution[name](solution.t), dtype=float)
            except Exception as extraction_error:
                failures[column] = str(extraction_error)
        np.savez_compressed(args.out / "unverified-partial-arrays.npz", **partial)
        write_json(
            args.out / "failure.json",
            {
                "status": "UNVERIFIED",
                "error": str(error),
                "extraction_errors": failures,
                "battery_dfns_solved": 1,
                "partial_arrays_sha256": digest(args.out / "unverified-partial-arrays.npz"),
            },
        )
        raise
    np.savez_compressed(args.out / "scalar-arrays.npz", **arrays)
    audit = physical_audit(arrays, metadata, data)
    empirical = (
        empirical_report(data, arrays, str(solution.termination), audit)
        if not audit.get("nonfinite_scalar_columns")
        else None
    )
    report = {
        "mesh": args.mesh,
        "effective_tolerances": effective,
        "config": metadata,
        "output_receipt": output_receipt,
        "physical_audit": audit,
        "empirical": empirical,
        "source_sha256": source_digests(),
        "source_commit": os.environ.get("GITHUB_SHA"),
        "arrays_sha256": digest(args.out / "scalar-arrays.npz"),
        "final_state_sha256": digest(args.out / "final-state.npy"),
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "battery_dfns_solved": 1,
        "parameter_fitting": False,
        "runtime_versions": runtime_versions(),
    }
    write_json(args.out / "report.json", report)
    write_json(
        args.out / "stage.json",
        {
            "status": "complete",
            "mesh": args.mesh,
            "physical_audit_passed": audit["passed"],
            "empirical_pass_is_separate": True,
        },
    )
    return 0 if audit["passed"] else 2


def run_process_with_deadline(command, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"exit_code": 124, "status": "shared_budget_exhausted_before_stage"}
    process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    try:
        code = process.wait(timeout=remaining)
        return {"exit_code": code, "status": "exited"}
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        return {"exit_code": 124, "status": "shared_budget_exhausted_worker_terminated"}


def execute(args):
    validate_managed_launch(args.prepared, args.upload_receipt, os.environ)
    if args.out.exists():
        raise ValueError("Scientific output directory already exists; no duplicate launch")
    args.out.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + WALL_LIMIT_S
    ledger = {
        "run_id": os.environ["GITHUB_RUN_ID"],
        "source_commit": os.environ["GITHUB_SHA"],
        "started_at_utc": datetime.now(UTC).isoformat(),
        "shared_wall_limit_s": WALL_LIMIT_S,
        "worker_address_space_limit_bytes": MEMORY_LIMIT_BYTES,
        "maximum_battery_dfns": 1,
        "stages": [],
        "status": "running",
    }
    write_json(args.out / "launch.json", ledger)
    for mesh in (120,):
        stage_dir = args.out / f"mesh{mesh}"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--mesh",
            str(mesh),
            "--prepared",
            str(args.prepared.resolve()),
            "--upload-receipt",
            str(args.upload_receipt.resolve()),
            "--deadline-monotonic",
            str(deadline),
            "--out",
            str(stage_dir.resolve()),
        ]
        status = run_process_with_deadline(command, deadline)
        status["mesh"] = mesh
        ledger["stages"].append(status)
        write_json(args.out / "launch.json", ledger)
        if status["exit_code"] != 0:
            ledger["status"] = "UNVERIFIED_or_physical_failure_no_further_stage"
            ledger["elapsed_s"] = time.monotonic() - started
            write_json(args.out / "launch.json", ledger)
            return status["exit_code"] if status["exit_code"] > 0 else 1
        report = json.loads((stage_dir / "report.json").read_text())
        if not report["physical_audit"]["passed"]:
            raise ValueError("Worker incorrectly reported a successful physical audit")
    ledger["status"] = "single_mesh120_complete_spatial_comparison_pending"
    ledger["elapsed_s"] = time.monotonic() - started
    write_json(args.out / "launch.json", ledger)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--out", type=Path, required=True)
    for mode in ("execute", "worker"):
        command = sub.add_parser(mode)
        command.add_argument("--prepared", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        command.add_argument("--upload-receipt", type=Path, required=True)
        if mode == "worker":
            command.add_argument("--mesh", type=int, choices=(120,), required=True)
            command.add_argument("--deadline-monotonic", type=float, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare_inputs(args.out)
        return 0
    if args.mode == "worker":
        return worker(args)
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
