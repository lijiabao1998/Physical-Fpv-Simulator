"""One prospectively frozen external measurement case, with a shared two-grid budget."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CALCULATION_FILES = (
    "src/physical_fpv/core.py",
    "src/physical_fpv/current_profile.py",
    "src/physical_fpv/stanford_benchmark.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/stanford_reference.py",
    "src/physical_fpv/thermal_benchmark.py",
    "src/physical_fpv/validation.py",
    "scripts/run_stanford_pilot.py",
    "docs/stanford-validation-protocol.md",
    "docs/stanford-scheduling-addendum.md",
    "docs/stanford-memory-addendum.md",
    "docs/benchmarks/stanford-k1-mesh80-reference.json",
    "docs/benchmarks/stanford-k1-mesh80-v2.csv.gz",
    "docs/benchmarks/stanford-k1-mesh80-v2.json",
    "data/stanford-manifest.json",
    "docs/benchmarks/stanford-k1-chronology.json",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
    "pyproject.toml",
)


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def complete_evidence_available(path):
    try:
        report = json.loads(path.read_text())
        return (
            set(report["cases"]) == {"80", "120"}
            and all(
                report["cases"][str(n)]["model"]["config"]["mesh_points"] == n for n in (80, 120)
            )
            and isinstance(report["spatial_numerical_check"]["passed"], bool)
            and bool(report["inputs"]["source_sha256"])
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def source_digests():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in CALCULATION_FILES}


def run_worker(args):
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    import faulthandler
    import gc
    import platform
    from dataclasses import asdict, replace

    import numpy as np
    import pybamm

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.core import parameter_fingerprint, simulate
    from physical_fpv.stanford_benchmark import (
        MEMORY_ADDENDUM_SHA256,
        SCHEDULING_ADDENDUM_SHA256,
        evaluate_pilot,
        prepare_pilot,
        verify_protocol,
    )
    from physical_fpv.stanford_reference import load_mesh80_reference
    from physical_fpv.thermal_benchmark import thermal_numerics
    from physical_fpv.validation import write_timeseries

    faulthandler.dump_traceback_later(60, repeat=True)
    verify_protocol(Path.cwd())
    sources = source_digests()
    manifest = json.loads(Path("data/stanford-manifest.json").read_text())
    observed, profile, config, assumptions = prepare_pilot(Path("data/stanford/raw"), manifest)
    parameters = pybamm.ParameterValues("ORegan2022")
    initial_concentrations = {
        electrode: parameters[f"Initial concentration in {electrode} electrode [mol.m-3]"]
        for electrode in ("negative", "positive")
    }
    if initial_concentrations != {"negative": 28866.0, "positive": 13975.0}:
        raise ValueError("Published initial concentrations differ from the frozen protocol")
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.initial_temperature_k,
            "Total heat transfer coefficient [W.m-2.K-1]": config.heat_transfer_coefficient_w_m2_k,
        }
    )
    fingerprint = hashlib.sha256(
        (
            parameter_fingerprint(parameters)
            + ":piecewise-linear-current:"
            + profile.fingerprint_sha256
        ).encode()
    ).hexdigest()
    reference = load_mesh80_reference(Path.cwd(), config, profile, fingerprint)
    inputs = {
        "config": asdict(config),
        "source_sha256": sources,
        "source_commit_sha": os.environ.get("PHYSICAL_FPV_RESEARCH_COMMIT"),
        "python_version": platform.python_version(),
        "pybamm_version": pybamm.__version__,
        "numpy_version": np.__version__,
        "memory_budget_bytes": 4_000_000_000,
        "wall_budget_s": args.timeout,
        "assumptions": assumptions,
        "fitting_performed": False,
        "initial_concentrations_mol_m3": initial_concentrations,
        "profile_schedule": "adaptive",
        "scheduling_addendum_sha256": SCHEDULING_ADDENDUM_SHA256,
        "memory_addendum_sha256": MEMORY_ADDENDUM_SHA256,
        "reused_mesh80": reference.metadata()["recorded_reference"],
        "new_simulated_meshes": [120],
    }
    write_json(args.out / "input.json", inputs)
    write_evidence_attribution(args.out, ["stanford2021", "oregan2022_parameters"])
    np.savetxt(
        args.out / "forcing.csv",
        np.column_stack((profile.time_s, profile.current_a)),
        delimiter=",",
        header="time_s,positive_discharge_current_a",
        comments="",
    )
    reports, results = {"80": reference.empirical_report}, {80: reference}
    write_json(args.out / "mesh80-report.json", reports["80"])
    write_timeseries(args.out / "mesh80-timeseries.csv", reference)
    ref_index = json.loads(Path("docs/benchmarks/stanford-k1-mesh80-reference.json").read_text())
    if (
        hashlib.sha256((args.out / "mesh80-timeseries.csv").read_bytes()).hexdigest()
        != ref_index["csv_sha256"]
    ):
        raise ValueError("Reused mesh80 serialization differs from the exact source curve")
    # Only regenerate the deterministic residual export from authenticated observations/curve.
    # Preserve the original report and its failed empirical gate without recalculating acceptance.
    start, stop = reports["80"]["common_observed_interval_s"]
    common = np.unique(
        np.r_[
            start,
            observed[(observed[:, 0] > start) & (observed[:, 0] < stop), 0],
            reference.time_s[(reference.time_s > start) & (reference.time_s < stop)],
            stop,
        ]
    )
    measured_v = np.interp(common, observed[:, 0], observed[:, 2])
    measured_t = np.interp(common, observed[:, 0], observed[:, 3])
    predicted_v = np.interp(common, reference.time_s, reference.voltage_v)
    predicted_t = np.interp(common, reference.time_s, reference.temperature_k)
    np.savetxt(
        args.out / "mesh80-residuals.csv",
        np.column_stack(
            (
                common,
                measured_v,
                predicted_v,
                predicted_v - measured_v,
                measured_t,
                predicted_t,
                predicted_t - measured_t,
            )
        ),
        delimiter=",",
        comments="",
        header="time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v,measured_skin_k,predicted_average_k,temperature_proxy_error_k",
    )
    if (
        hashlib.sha256((args.out / "mesh80-residuals.csv").read_bytes()).hexdigest()
        != ref_index["residual_sha256"]
    ):
        raise ValueError("Reused mesh80 residual export differs from original evidence")
    for mesh in (120,):
        gc.collect()
        started = time.monotonic()
        write_json(args.out / "stage.json", {"status": "running", "mesh": mesh})
        result = simulate(
            replace(config, mesh_points=mesh), current_profile=profile, profile_schedule="adaptive"
        )
        write_timeseries(args.out / f"mesh{mesh}-timeseries.csv", result)
        report = evaluate_pilot(observed, profile, result, args.out / f"mesh{mesh}-residuals.csv")
        report["elapsed_s"] = time.monotonic() - started
        report["peak_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        write_json(args.out / f"mesh{mesh}-report.json", report)
        reports[str(mesh)], results[mesh] = report, result
        print(
            json.dumps(
                {
                    "mesh": mesh,
                    "elapsed_s": report["elapsed_s"],
                    "voltage_rmse_v": report["voltage_rmse_v"],
                    "electrical_gates_passed": report["electrical_gates_passed"],
                }
            ),
            flush=True,
        )
    if source_digests() != sources:
        raise RuntimeError("Calculation files changed during the frozen pilot")
    if results[80].parameter_fingerprint != results[120].parameter_fingerprint:
        raise RuntimeError("Numerical grids used different forcing or physical parameters")
    numerical = thermal_numerics(results[80], results[120])
    common = np.unique(np.r_[results[80].time_s, results[120].time_s])
    common = common[common <= min(results[80].time_s[-1], results[120].time_s[-1])]
    dv = np.interp(common, results[80].time_s, results[80].voltage_v) - np.interp(
        common, results[120].time_s, results[120].voltage_v
    )
    dt = np.interp(common, results[80].time_s, results[80].temperature_k) - np.interp(
        common, results[120].time_s, results[120].temperature_k
    )
    numerical.update(
        {
            "voltage_peak_difference_time_s": float(common[np.argmax(abs(dv))]),
            "temperature_peak_difference_time_s": float(common[np.argmax(abs(dt))]),
            "coarse_cutoff_time_s": float(results[80].time_s[-1]),
            "fine_cutoff_time_s": float(results[120].time_s[-1]),
        }
    )
    write_json(
        args.out / "report.json",
        {
            "inputs": inputs,
            "cases": reports,
            "spatial_numerical_check": numerical,
            "electrical_pilot_gates_passed": reports["120"]["electrical_gates_passed"],
            "independent_thermal_validation_established": False,
            "whole_cohort_validation_established": False,
            "existing_oregan_empirical_failures": "30/36; unchanged",
            "fitting_performed": False,
        },
    )
    write_json(args.out / "stage.json", {"status": "completed", "meshes": [80, 120]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k1-pilot"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1200:
        parser.error("One pilot is bounded to at most1200seconds")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.worker:
        run_worker(args)
        return 0
    if any((args.out / name).exists() for name in ("input.json", "report.json", "status.json")):
        parser.error(
            "Output already contains evidence; choose a new directory rather than overwrite"
        )
    command = [
        sys.executable,
        "-u",
        __file__,
        "--worker",
        "--timeout",
        str(args.timeout),
        "--out",
        str(args.out),
    ]
    started = time.monotonic()
    with (args.out / "solver.log").open("w") as log:
        child = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, OMP_NUM_THREADS="1", PYBAMM_DISABLE_TELEMETRY="true"),
        )
        status = "running"
        while child.poll() is None:
            elapsed = time.monotonic() - started
            progress = {
                "status": status,
                "elapsed_s": elapsed,
                "budget_s": args.timeout,
                "scope": "one Stanford k1 mesh120 continuation; verified mesh80 reused",
            }
            write_json(args.out / "progress.json", progress)
            print(json.dumps(progress), flush=True)
            if elapsed >= args.timeout:
                child.kill()
                child.wait()
                status = "budget_exhausted"
                break
            time.sleep(min(10, args.timeout - elapsed))
        if status == "running":
            status = "completed" if child.returncode == 0 else "solver_or_resource_failure"
    result = {
        "status": status,
        "return_code": child.returncode,
        "elapsed_s": time.monotonic() - started,
        "budget_s": args.timeout,
        "missing_numerical_stage_is_unverified": not complete_evidence_available(
            args.out / "report.json"
        ),
        "empirical_disagreement_is_separate_from_execution_status": True,
    }
    write_json(args.out / "status.json", result)
    print(json.dumps(result), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
