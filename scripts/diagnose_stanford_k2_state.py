"""One bounded, unchanged k2 grid120 solve with observational state accounting."""

import argparse
import hashlib
import importlib.util
import json
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL_SHA256 = "911b1ce24f6a87626bbac67fbc37e9300ce7d8c60db0d05e712d278288f0c83b"
REFERENCE_ZIP_SHA256 = "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
EXTRA_FILES = (
    "src/physical_fpv/polarization.py",
    "scripts/diagnose_stanford_k2_state.py",
    "docs/stanford-k2-state-protocol.md",
    "docs/benchmarks/stanford-k2-recovery-evidence.zip",
    "docs/benchmarks/oregan-parameter-support.json",
    ".github/workflows/stanford-k2-state.yml",
    "tests/test_stanford_k2_state.py",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def capture_one_solve(simulate, config, profile):
    """Observe exactly one actual solve, restoring the method even on failure."""
    import pybamm

    original = pybamm.Simulation.solve
    captured = []

    def observe(simulation, *args, **kwargs):
        if captured:
            raise RuntimeError("More than one scientific solve was requested")
        captured.append([simulation, None])
        solution = original(simulation, *args, **kwargs)
        captured[0][1] = solution
        return solution

    pybamm.Simulation.solve = observe
    try:
        result = simulate(config, current_profile=profile, profile_schedule="adaptive")
    finally:
        pybamm.Simulation.solve = original
    if len(captured) != 1 or captured[0][0].solution is not captured[0][1]:
        raise RuntimeError("Could not authenticate the one captured solution")
    return result, *captured[0]


def summarize_states(path, endpoint):
    """Stream reduced native-profile CSV; never materialize full r-by-x states."""
    import csv

    envelopes = {"negative": (0.1585, 1.0), "positive": (0.2598, 0.8499)}
    crossings = {
        e: {
            "sampled_envelope": list(v),
            "first_observed_outside_s": None,
            "preceding_observation_s": None,
            "outside_saved_samples": 0,
            "maximum_excursion": 0.0,
        }
        for e, v in envelopes.items()
    }
    targets = {
        "initial": 0.0,
        "early": 0.1 * endpoint,
        "middle": 0.5 * endpoint,
        "late": 0.9 * endpoint,
        "end": endpoint,
        "residual_sign_change": 3152.943046406281,
    }
    selected, previous_time, count = {}, None, 0
    with path.open() as stream:
        for raw in csv.DictReader(stream):
            row = {k: float(v) for k, v in raw.items() if "_node_" not in k}
            t = row["time_s"]
            count += 1
            for electrode, (lower, upper) in envelopes.items():
                low = row[f"{electrode}_surface_min_stoichiometry"]
                high = row[f"{electrode}_surface_max_stoichiometry"]
                state = crossings[electrode]
                excursion = max(0.0, lower - low, high - upper)
                state["maximum_excursion"] = max(state["maximum_excursion"], excursion)
                if excursion > 0:
                    state["outside_saved_samples"] += 1
                    if state["first_observed_outside_s"] is None:
                        state["first_observed_outside_s"] = t
                        state["preceding_observation_s"] = previous_time
            for label, target in targets.items():
                if label not in selected or abs(t - target) < selected[label]["time_distance_s"]:
                    selected[label] = {
                        "target_time_s": target,
                        "time_distance_s": abs(t - target),
                        "observed_time_s": t,
                        "scalars": row,
                    }
            previous_time = t
    return {
        "support_crossings": crossings,
        "selected_states": selected,
        "saved_rows": count,
        "crossing_method": (
            "first saved output outside any native surface node; "
            "previous timestamp brackets observation"
        ),
        "continuous_crossing_or_outside_duration_inferred": False,
        "unique_empirical_cause_identified": False,
    }


def prepare(args):
    import shutil
    import zipfile

    from physical_fpv.stanford_data import validate_workbook_bytes

    if digest("docs/stanford-k2-state-protocol.md") != PROTOCOL_SHA256:
        raise ValueError("Frozen diagnostic protocol changed")
    archive = Path("docs/benchmarks/stanford-k2-recovery-evidence.zip")
    if digest(archive) != REFERENCE_ZIP_SHA256:
        raise ValueError("Previous recovery artifact changed")
    manifest = json.loads(Path("data/stanford-manifest.json").read_text())
    entry = next(e for e in manifest["files"] if e["filename"] == "NMC_k2_1C_25degC.xlsx")
    raw = Path("data/stanford/raw") / entry["filename"]
    source = args.source_inputs / "data/stanford/raw" / entry["filename"]
    validation = validate_workbook_bytes(source.read_bytes(), entry)
    if raw.exists() and digest(raw) != validation["sha256"]:
        raise ValueError("Existing workbook differs; never overwrite unknown source")
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        shutil.copyfile(source, raw)
    runner = module("scripts/run_stanford_k2.py")
    observed, profile, config, assumptions, inputs = runner.prepare_inputs()
    with zipfile.ZipFile(archive) as zipped:
        previous = json.loads(zipped.read("stanford-k2-recovery/input.json"))
    if inputs["source_sha256"] != previous["source_sha256"]:
        raise ValueError("Frozen scientific implementation changed")
    if inputs["parameter_current_fingerprint"] != previous["parameter_current_fingerprint"]:
        raise ValueError("Frozen physical/current identity changed")
    inputs.update(
        diagnostic_protocol_sha256=PROTOCOL_SHA256,
        diagnostic_source_sha256={p: digest(p) for p in EXTRA_FILES},
        original_attempt_status="unknown",
        reference_source_commit="50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84",
        reused_inputs_artifact_id=11590866548,
        reused_inputs_run_id=37871885149,
        original_source_reacquisitions=0,
        new_simulated_meshes=[120],
        prior_grid120_empirical_rmse_v=0.05500305419157363,
        scientific_threshold_rmse_v=0.05,
    )
    inputs["config"]["mesh_points"] = 120
    return runner, observed, profile, config, assumptions, inputs


def run_worker(args):
    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    signal.alarm(args.timeout)
    import faulthandler
    import io
    import zipfile
    from dataclasses import replace

    import numpy as np

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.core import simulate
    from physical_fpv.polarization import export_polarization
    from physical_fpv.stanford_k2 import evaluate_k2
    from physical_fpv.validation import write_timeseries

    faulthandler.dump_traceback_later(60, repeat=True)
    runner, observed, profile, config, assumptions, inputs = prepare(args)
    if json.loads((args.out / "input.json").read_text()) != inputs:
        raise ValueError("Prelaunch diagnostic inputs changed")
    write(args.out / "stage.json", {"stage": "solving", "mesh": 120})
    result, simulation, solution = capture_one_solve(
        simulate, replace(config, mesh_points=120), profile
    )
    runner.save_snapshot(args.out, 120, result)
    write_timeseries(args.out / "timeseries.csv", result)
    scientific = evaluate_k2(
        observed, profile, result, args.out / "residuals.csv", assumptions=assumptions
    )
    write(args.out / "empirical-report.json", scientific)
    write(args.out / "stage.json", {"stage": "exporting", "scientific_solve_calls": 1})
    actual = simulation.parameter_values.copy()
    interpolant = actual["Current function [A]"]
    if (
        type(interpolant).__name__ != "Interpolant"
        or not np.array_equal(np.asarray(interpolant.x[0]), profile.time_s)
        or not np.array_equal(np.asarray(interpolant.y).reshape(-1), profile.current_a)
        or interpolant.extrapolate is not False
        or interpolant.interpolator != "linear"
    ):
        raise ValueError("Actual solver interpolant differs from the frozen current profile")
    write(
        args.out / "captured-solve.json",
        {
            "scientific_solve_calls": 1,
            "same_simulation_solution_object": simulation.solution is solution,
            "actual_interpolant_type": type(interpolant).__name__,
            "actual_interpolator": interpolant.interpolator,
            "actual_extrapolate": interpolant.extrapolate,
            "actual_knots_and_values_equal_frozen_profile": True,
            "profile_sha256": profile.fingerprint_sha256,
            "actual_parameter_copy_fingerprinted": True,
            "only_scalar_current_normalized": True,
        },
    )
    # Normalize only current in a copy of ACTUAL parameters, using core's fingerprint convention.
    actual.update({"Current function [A]": config.current_a})
    summary = export_polarization(args.out, result, solution, actual, current_profile=profile)
    write(
        args.out / "state-findings.json",
        summarize_states(args.out / "polarization.csv", result.time_s[-1]),
    )
    with zipfile.ZipFile("docs/benchmarks/stanford-k2-recovery-evidence.zip") as zipped:
        with np.load(io.BytesIO(zipped.read("stanford-k2-recovery/mesh120-arrays.npz"))) as old:
            stop = min(old["time_s"][-1], result.time_s[-1])
            common = np.unique(
                np.r_[
                    old["time_s"][old["time_s"] <= stop], result.time_s[result.time_s <= stop], stop
                ]
            )
            dv = np.interp(common, result.time_s, result.voltage_v) - np.interp(
                common, old["time_s"], old["voltage_v"]
            )
            dt = np.interp(common, result.time_s, result.temperature_k) - np.interp(
                common, old["time_s"], old["temperature_k"]
            )
            capacity = float(
                abs(result.capacity_ah[-1] - old["capacity_ah"][-1]) / old["capacity_ah"][-1]
            )
            repeatability = {
                "reference_cutoff_s": float(old["time_s"][-1]),
                "diagnostic_cutoff_s": float(result.time_s[-1]),
                "voltage_max_difference_v": float(max(abs(dv))),
                "temperature_max_difference_k": float(max(abs(dt))),
                "capacity_relative_difference": capacity,
                "passed": bool(
                    max(abs(dv)) <= 0.001 and max(abs(dt)) <= 0.01 and capacity <= 0.001
                ),
            }
    write(args.out / "repeatability.json", repeatability)
    if inputs["diagnostic_source_sha256"] != {p: digest(p) for p in EXTRA_FILES}:
        raise ValueError("Diagnostic source changed during execution")
    if inputs["source_sha256"] != runner.source_digests():
        raise ValueError("Scientific source changed during execution")
    outcome = {
        "diagnostic_checks_passed": bool(
            summary["accounting_passed"]
            and repeatability["passed"]
            and result.physical_audit["passed"]
            and result.termination == "event: Minimum voltage [V]"
        ),
        "accounting_passed": summary["accounting_passed"],
        "repeatability_passed": repeatability["passed"],
        "scientific_voltage_rmse_v": scientific["voltage_rmse_v"],
        "scientific_empirical_pass": scientific["source_window_empirical_qualification_passed"],
        "scientific_solve_calls": 1,
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "unique_real_cell_cause_identified": False,
    }
    write_evidence_attribution(args.out, ["stanford2021", "oregan2022_parameters"])
    write(args.out / "outcome.json", outcome)
    print(json.dumps(outcome), flush=True)
    return 0 if outcome["diagnostic_checks_passed"] else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--source-inputs", type=Path, default=Path("source-inputs"))
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k2-state"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1200:
        parser.error("Diagnostic timeout must not exceed1200seconds")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.prepare_only:
        if (args.out / "input.json").exists():
            parser.error("Preserve existing diagnostic inputs")
        *_, inputs = prepare(args)
        write(args.out / "input.json", inputs)
        return 0
    if args.worker:
        return run_worker(args)
    if any((args.out / p).exists() for p in ("status.json", "progress.json", "outcome.json")):
        parser.error("Preserve existing run; choose a new output directory")
    if not (args.out / "input.json").exists():
        parser.error("Persist prepared input before launching")
    start = time.monotonic()
    command = [
        sys.executable,
        "-u",
        __file__,
        "--worker",
        "--timeout",
        str(args.timeout),
        "--source-inputs",
        str(args.source_inputs),
        "--out",
        str(args.out),
    ]
    with (args.out / "solver.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        status = "running"
        while process.poll() is None:
            elapsed = time.monotonic() - start
            progress = {"status": status, "elapsed_s": elapsed, "budget_s": args.timeout}
            write(args.out / "progress.json", progress)
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
    elapsed = time.monotonic() - start
    if status == "completed" and elapsed >= args.timeout:
        status = "budget_exhausted"
    write(
        args.out / "status.json",
        {
            "status": status,
            "return_code": process.returncode,
            "elapsed_s": elapsed,
            "budget_s": args.timeout,
        },
    )
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
