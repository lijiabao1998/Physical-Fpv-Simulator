"""Prepare an isolated experiment, or execute its reviewed single managed job.

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
PROTOCOL = "docs/stanford-k2-low-rate-model-protocol.md"
SOURCE_FILES = (
    PROTOCOL,
    "docs/experiments/stanford-k2-low-rate-model.workflow.yml",
    "src/physical_fpv/experimental_low_rate.py",
    "src/physical_fpv/core.py",
    "src/physical_fpv/current_profile.py",
    "src/physical_fpv/contrast_persistence.py",
    "src/physical_fpv/stanford_benchmark.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/thermal_benchmark.py",
    "src/physical_fpv/thermal_data.py",
    "src/physical_fpv/validation.py",
    "scripts/run_stanford_k2_low_rate_model.py",
    "scripts/compare_stanford_k2_rates.py",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
    "pyproject.toml",
    "docs/benchmarks/stanford-k2-low-rate-discharge.csv.gz",
    "docs/benchmarks/stanford-k2-low-rate-source.json",
    "docs/benchmarks/stanford-cross-rate-onset.json",
    "docs/benchmarks/stanford-k2-recovery-evidence.zip",
    "docs/benchmarks/stanford-k2-rest-records.csv.gz",
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
    workflow = ".github/workflows/k2-low-rate-model-20261009-v1.yml"
    if (ROOT / workflow).exists():
        names.add(workflow)
    return {name: digest(ROOT / name) for name in sorted(names)}


def prepare_inputs(out):
    import numpy as np
    import pybamm

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.experimental_low_rate import build, prepare

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
    for mesh in (80, 120):
        sim, _, metadata = build(data, mesh)
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
                "parameters-mesh80.json",
                "parameters-mesh120.json",
            )
        },
        "source_metadata": data.metadata,
        "pybamm_version": pybamm.__version__,
        "numpy_version": np.__version__,
        "runtime_versions": runtime_versions(),
        "planned_meshes": [80, 120],
        "planned_configurations": configurations,
        "maximum_battery_dfns": 2,
        "shared_wall_limit_s": WALL_LIMIT_S,
        "worker_address_space_limit_bytes": MEMORY_LIMIT_BYTES,
        "no_new_source_downloads": True,
        "parameter_fitting": False,
    }
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
        manifest["planned_meshes"] != [80, 120]
        or manifest["shared_wall_limit_s"] != WALL_LIMIT_S
        or manifest["worker_address_space_limit_bytes"] != MEMORY_LIMIT_BYTES
    ):
        raise ValueError("Reviewed execution bounds changed")
    return manifest


def validate_managed_launch(prepared_dir, upload_receipt, environ):
    manifest = verify_inputs(prepared_dir)
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
        build,
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
    if args.mesh not in (80, 120) or args.out.exists():
        raise ValueError("Unreviewed or duplicate worker stage")
    args.out.mkdir(parents=True)
    started = time.monotonic()
    write_json(args.out / "stage.json", {"status": "building", "mesh": args.mesh})
    data = prepare(ROOT)
    sim, outputs, metadata = build(data, args.mesh)
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
    # The only battery solve call in the worker. The parent owns the shared timer.
    solution = sim.solve([0.0, float(data.output_time_s[-1])], t_interp=data.output_time_s)
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
        "maximum_battery_dfns": 2,
        "stages": [],
        "status": "running",
    }
    write_json(args.out / "launch.json", ledger)
    for mesh in (80, 120):
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
    ledger["status"] = "two_stages_complete_scientific_verdict_pending"
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
            command.add_argument("--mesh", type=int, choices=(80, 120), required=True)
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
