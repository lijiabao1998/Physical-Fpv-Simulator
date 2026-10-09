"""Run one frozen-state diagnostic with bounded resources and saved progress."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL_SHA256 = "46fed0a3e6ce82d42486b2c88741dfa0a32b954c8ea31feeeb1e707a6238bf23"
REFERENCE_SHA256 = "61585bc925a0328513f7f6a905d55a926eed762530f5e9faae2e005d8a492846"
CALCULATION_FILES = (
    "src/physical_fpv/core.py",
    "src/physical_fpv/polarization.py",
    "src/physical_fpv/validation.py",
    "src/physical_fpv/attribution.py",
    "scripts/diagnose_polarization.py",
    "docs/polarization-protocol.md",
    "requirements-lock.txt",
    "pyproject.toml",
    "docs/benchmarks/cell790-grid120-diagnosis.json",
    "docs/benchmarks/thermal-grid120-reference.csv",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def worker_command(args):
    return [
        sys.executable,
        "-u",
        __file__,
        "--worker",
        "--timeout",
        str(args.timeout),
        "--out",
        str(args.out),
    ]


def run_worker(args):
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    import faulthandler
    import platform
    from dataclasses import asdict

    import numpy as np
    import pybamm

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.core import ModelConfig, _simulation_template, simulate
    from physical_fpv.polarization import export_polarization
    from physical_fpv.validation import write_timeseries

    faulthandler.dump_traceback_later(60, repeat=True)
    if digest("docs/polarization-protocol.md") != PROTOCOL_SHA256:
        raise ValueError("Frozen polarization protocol changed")
    if digest("docs/benchmarks/thermal-grid120-reference.csv") != REFERENCE_SHA256:
        raise ValueError("Previous grid120 reference changed")
    sources = {path: digest(path) for path in CALCULATION_FILES}
    previous = json.loads(Path("docs/benchmarks/cell790-grid120-diagnosis.json").read_text())
    config = ModelConfig(**previous["simulation"]["config"])
    if config.mesh_points != 120 or config.current_a != 5:
        raise ValueError("Diagnostic is restricted to the declared representative state")
    inputs = {
        "config": asdict(config),
        "source_sha256": sources,
        "source_commit_sha": os.environ.get("PHYSICAL_FPV_RESEARCH_COMMIT"),
        "protocol_sha256": PROTOCOL_SHA256,
        "pybamm_version": pybamm.__version__,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "memory_budget_bytes": 4_000_000_000,
        "wall_budget_s": args.timeout,
        "scope": "one unchanged model; new internal-state observables, no fit",
    }
    write_json(args.out / "input.json", inputs)
    result = simulate(config)
    if result.parameter_fingerprint != previous["simulation"]["parameter_fingerprint"]:
        raise ValueError("Frozen parameter or initial/boundary state fingerprint changed")
    write_timeseries(args.out / "timeseries.csv", result)
    write_json(args.out / "metadata.json", result.metadata())
    simulation = _simulation_template(
        config.model,
        config.thermal,
        config.parameter_set,
        config.mesh_points,
        config.tolerance,
        config.max_temperature_k,
        config.heat_transfer_coefficient_w_m2_k,
    )
    parameters = pybamm.ParameterValues(config.parameter_set)
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.initial_temperature_k,
            "Total heat transfer coefficient [W.m-2.K-1]": config.heat_transfer_coefficient_w_m2_k,
        }
    )
    summary = export_polarization(args.out, result, simulation.solution, parameters)
    reference = np.loadtxt(
        "docs/benchmarks/thermal-grid120-reference.csv", delimiter=",", skiprows=1
    )
    stop = min(reference[-1, 0], result.time_s[-1])
    common = np.unique(
        np.r_[reference[reference[:, 0] <= stop, 0], result.time_s[result.time_s <= stop], stop]
    )
    dv = np.interp(common, result.time_s, result.voltage_v) - np.interp(
        common, reference[:, 0], reference[:, 1]
    )
    dt = np.interp(common, result.time_s, result.temperature_k) - np.interp(
        common, reference[:, 0], reference[:, 3]
    )
    voltage = float(np.max(np.abs(dv)))
    temperature = float(np.max(np.abs(dt)))
    capacity = float(abs(result.capacity_ah[-1] - reference[-1, 2]) / reference[-1, 2])
    repeatability = {
        "comparison": "new observable export vs original grid120; no new mesh-convergence claim",
        "common_interval_s": [float(common[0]), float(stop)],
        "previous_cutoff_s": float(reference[-1, 0]),
        "new_cutoff_s": float(result.time_s[-1]),
        "voltage_max_difference_v": voltage,
        "temperature_max_difference_k": temperature,
        "capacity_relative_difference": capacity,
        "voltage_peak_difference_time_s": float(common[np.argmax(np.abs(dv))]),
        "temperature_peak_difference_time_s": float(common[np.argmax(np.abs(dt))]),
        "passed": voltage <= 0.001 and temperature <= 0.01 and capacity <= 0.001,
    }
    write_json(args.out / "repeatability.json", repeatability)
    if sources != {path: digest(path) for path in CALCULATION_FILES}:
        raise RuntimeError("Calculation files changed during the run")
    outcome = {
        "accounting_passed": summary["accounting_passed"],
        "repeatability_passed": repeatability["passed"],
        "physical_audit_passed": result.physical_audit["passed"],
        "voltage_cutoff_reached": result.metadata()["voltage_cutoff_reached"],
        "scope": "diagnostic consistency only; original empirical failures remain",
        "new_simulation_run": True,
    }
    outcome["diagnostic_checks_passed"] = all(
        outcome[k]
        for k in (
            "accounting_passed",
            "repeatability_passed",
            "physical_audit_passed",
            "voltage_cutoff_reached",
        )
    )
    write_evidence_attribution(args.out, ["tec_validation", "oregan2022_parameters"])
    write_json(args.out / "outcome.json", outcome)
    print(json.dumps(outcome), flush=True)
    return 0 if outcome["diagnostic_checks_passed"] else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--out", type=Path, default=Path("results/polarization-grid120"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1200:
        parser.error("Wall budget must be 1 to1200 seconds")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return run_worker(args)
    if (args.out / "status.json").exists():
        parser.error("Use a fresh output directory; existing evidence cannot be overwritten")
    start = time.monotonic()
    environment = dict(os.environ, PYBAMM_DISABLE_TELEMETRY="true", OMP_NUM_THREADS="1")
    with (args.out / "solver.log").open("w") as log:
        process = subprocess.Popen(
            worker_command(args), stdout=log, stderr=subprocess.STDOUT, env=environment
        )
        status = "running"
        while process.poll() is None:
            elapsed = time.monotonic() - start
            progress = {
                "status": status,
                "elapsed_s": elapsed,
                "budget_s": args.timeout,
                "pid": process.pid,
            }
            write_json(args.out / "progress.json", progress)
            print(json.dumps(progress), flush=True)
            if elapsed >= args.timeout:
                process.kill()
                process.wait()
                status = "budget_exhausted"
                break
            time.sleep(min(10, args.timeout - elapsed))
        if status == "running":
            status = {0: "completed", 3: "diagnostic_check_failure"}.get(
                process.returncode, "solver_or_resource_failure"
            )
        outcome = {
            "status": status,
            "return_code": process.returncode,
            "elapsed_s": time.monotonic() - start,
            "budget_s": args.timeout,
        }
        write_json(args.out / "status.json", outcome)
        write_json(args.out / "progress.json", outcome)
        print(json.dumps(outcome), flush=True)
        return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
