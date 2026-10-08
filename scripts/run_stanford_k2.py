"""One k2 conditional prediction; isolated meshes share a hard twenty-minute budget."""

import argparse
import hashlib
import json
import math
import os
import re
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

INPUT_PATH = "data/stanford-k2-pilot-input.json"
INPUT_SHA256 = "0e0d8360fa87870f4103110c48e95f93774696e46046bc335309c7822c037477"
CALCULATION_FILES = (
    "src/physical_fpv/core.py",
    "src/physical_fpv/current_profile.py",
    "src/physical_fpv/stanford_k2.py",
    "src/physical_fpv/stanford_benchmark.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/thermal_benchmark.py",
    "src/physical_fpv/validation.py",
    "scripts/run_stanford_k2.py",
    "docs/stanford-k2-prediction-protocol.md",
    INPUT_PATH,
    "data/stanford-manifest.json",
    "docs/benchmarks/stanford-k2-k6-history-partial.json",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
    "pyproject.toml",
)
ARRAY_NAMES = (
    "time_s",
    "voltage_v",
    "capacity_ah",
    "temperature_k",
    "lithium_mol",
    "heating_w",
    "cooling_w",
    "heat_capacity_j_k",
)


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_digests():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in CALCULATION_FILES}


def prepare_inputs(require_commit=True):
    import inspect
    import platform
    from dataclasses import asdict

    import numpy as np
    import pybamm

    from physical_fpv.core import parameter_fingerprint
    from physical_fpv.stanford_k2 import prepare_k2, verify_protocol

    sources = source_digests()
    if sources[INPUT_PATH] != INPUT_SHA256:
        raise ValueError("Frozen k2 input contract changed")
    fixed = json.loads(Path(INPUT_PATH).read_text())
    verify_protocol(Path.cwd())
    observed, profile, config, assumptions = prepare_k2(
        Path("data/stanford/raw"), json.loads(Path("data/stanford-manifest.json").read_text())
    )
    if profile.fingerprint_sha256 != fixed["current_profile_sha256"]:
        raise ValueError("Frozen current fingerprint changed")
    commit = os.environ.get("PHYSICAL_FPV_RESEARCH_COMMIT")
    if require_commit and (commit is None or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ValueError("Actual run needs its frozen PHYSICAL_FPV_RESEARCH_COMMIT")
    config.validate()
    p = pybamm.ParameterValues("ORegan2022")
    concentrations = {
        electrode: p[f"Initial concentration in {electrode} electrode [mol.m-3]"]
        for electrode in ("negative", "positive")
    }
    if concentrations != fixed["config"]["initial_concentrations_mol_m3"]:
        raise ValueError("Published initial concentrations changed")
    q = pybamm.LithiumIonParameters()
    xn = concentrations["negative"] / p["Maximum concentration in negative electrode [mol.m-3]"]
    xp = concentrations["positive"] / p["Maximum concentration in positive electrode [mol.m-3]"]
    temp = pybamm.Scalar(config.initial_temperature_k)
    un = float(p.process_symbol(q.n.prim.U(pybamm.Scalar(xn), temp)).evaluate())
    up = float(p.process_symbol(q.p.prim.U(pybamm.Scalar(xp), temp)).evaluate())
    static = {
        "negative_stoichiometry": xn,
        "positive_stoichiometry": xp,
        "negative_ocp_v": un,
        "positive_ocp_v": up,
        "equilibrium_ocv_v": up - un,
        "measured_pre_rest_endpoint_v": fixed["pre_rest_last_voltage_v"],
        "ocv_minus_measured_rest_v": up - un - fixed["pre_rest_last_voltage_v"],
        "ocv_method": "Installed ParticleLithiumIonParameters.U; entropic correction and asymptote",
        "initial_state_fitted_from_ocv": False,
        "heat_capacity_initial_below_measured_25c_by_k": max(
            0, 298.15 - config.initial_temperature_k
        ),
        "conductivity_stoichiometry_applicability": "Unestablished; measured near positive x=0.9",
        "independent_thermal_validation_established": False,
    }
    if not (0 < xn < 1 and 0 < xp < 1) or not np.isfinite([un, up]).all():
        raise ValueError("Static published initial state is outside physical stoichiometry bounds")
    p.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.initial_temperature_k,
            "Total heat transfer coefficient [W.m-2.K-1]": config.heat_transfer_coefficient_w_m2_k,
        }
    )
    fingerprint = hashlib.sha256(
        (
            parameter_fingerprint(p) + ":piecewise-linear-current:" + profile.fingerprint_sha256
        ).encode()
    ).hexdigest()
    parameter_source = Path(inspect.getfile(p["Negative electrode diffusivity [m2.s-1]"]))
    return (
        observed,
        profile,
        config,
        assumptions,
        {
            "source_commit_sha": commit,
            "source_sha256": sources,
            "config": asdict(config),
            "assumptions": assumptions,
            "static_initialization": static,
            "initial_concentrations_mol_m3": concentrations,
            "parameter_current_fingerprint": fingerprint,
            "installed_parameter_source_sha256": hashlib.sha256(
                parameter_source.read_bytes()
            ).hexdigest(),
            "python_version": platform.python_version(),
            "pybamm_version": pybamm.__version__,
            "numpy_version": np.__version__,
            "memory_budget_bytes": 4_000_000_000,
            "wall_budget_s": 1200,
            "profile_schedule": "adaptive",
            "new_simulated_meshes": [80, 120],
            "each_mesh_in_fresh_process": True,
            "k1_curve_reused": False,
            "fitting_performed": False,
        },
    )


def save_snapshot(out, mesh, result):
    import numpy as np

    from physical_fpv.stanford_k2 import SCOPE

    path = out / f"mesh{mesh}-arrays.npz"
    temporary = path.with_name(path.name + ".tmp")
    arrays = {name: getattr(result, name) for name in ARRAY_NAMES}
    if arrays["heat_capacity_j_k"] is None:
        raise ValueError("Lumped k2 result is missing its native thermal-capacity trace")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    temporary.replace(path)
    metadata = result.metadata()
    metadata["scope"] = SCOPE
    write_json(
        out / f"mesh{mesh}-snapshot.json",
        {
            "arrays_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "model": metadata,
        },
    )


def load_snapshot(out, mesh):
    import numpy as np

    from physical_fpv.core import ModelConfig, SimulationResult

    path = out / f"mesh{mesh}-arrays.npz"
    index = json.loads((out / f"mesh{mesh}-snapshot.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != index["arrays_sha256"]:
        raise ValueError("Saved mesh arrays failed integrity verification")
    metadata = index["model"]
    if metadata["config"]["mesh_points"] != mesh:
        raise ValueError("Saved mesh identity changed")
    with np.load(path, allow_pickle=False) as saved:
        if set(saved.files) != set(ARRAY_NAMES):
            raise ValueError("Saved native summary array names changed")
        arrays = {name: saved[name] for name in ARRAY_NAMES}
    if any(a.shape != arrays["time_s"].shape or not np.isfinite(a).all() for a in arrays.values()):
        raise ValueError("Saved observables have invalid shapes or values")
    return SimulationResult(
        ModelConfig(**metadata["config"]),
        **arrays,
        termination=metadata["termination"],
        physical_audit=metadata["physical_audit"],
        parameter_fingerprint=metadata["parameter_fingerprint"],
        solver_cache_info=metadata["compiled_template_cache"],
        current_protocol=metadata["current_protocol"],
    )


def run_stage(args):
    import faulthandler
    from dataclasses import replace

    import numpy as np

    from physical_fpv.attribution import write_evidence_attribution
    from physical_fpv.core import simulate
    from physical_fpv.stanford_k2 import evaluate_k2
    from physical_fpv.validation import write_timeseries

    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    # A child also has its own deadline if its supervisor disappears.
    signal.alarm(max(1, math.ceil(args.stage_budget)))
    faulthandler.dump_traceback_later(60, repeat=True)
    observed, profile, config, assumptions, inputs = prepare_inputs(not args.preflight_only)
    if args.preflight_only:
        write_json(args.out / "preflight.json", inputs)
        print(json.dumps(inputs["static_initialization"]), flush=True)
        return
    prior = args.out / "input.json"
    if prior.exists() and json.loads(prior.read_text()) != inputs:
        raise ValueError("Inputs changed between the two isolated meshes")
    if not prior.exists():
        write_json(prior, inputs)
        write_evidence_attribution(args.out, ["stanford2021", "oregan2022_parameters"])
        np.savetxt(
            args.out / "forcing.csv",
            np.column_stack((profile.time_s, profile.current_a)),
            delimiter=",",
            header="time_s,positive_discharge_current_a",
            comments="",
        )
    write_json(args.out / "stage.json", {"status": "running", "mesh": args.mesh})
    started = time.monotonic()
    result = simulate(
        replace(config, mesh_points=args.mesh), current_profile=profile, profile_schedule="adaptive"
    )
    if result.parameter_fingerprint != inputs["parameter_current_fingerprint"]:
        raise ValueError("Solved model differs from frozen parameter/forcing fingerprint")
    if source_digests() != inputs["source_sha256"]:
        raise ValueError("Calculation inputs changed during solve")
    write_timeseries(args.out / f"mesh{args.mesh}-timeseries.csv", result)
    report = evaluate_k2(
        observed,
        profile,
        result,
        args.out / f"mesh{args.mesh}-residuals.csv",
        assumptions=assumptions,
    )
    report["elapsed_s"] = time.monotonic() - started
    report["peak_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    save_snapshot(args.out, args.mesh, result)
    write_json(args.out / f"mesh{args.mesh}-report.json", report)
    write_json(args.out / "stage.json", {"status": "mesh_completed", "mesh": args.mesh})
    print(
        json.dumps(
            {
                "mesh": args.mesh,
                "elapsed_s": report["elapsed_s"],
                "voltage_rmse_v": report["voltage_rmse_v"],
                "empirical_qualified": report["source_window_empirical_qualification_passed"],
            }
        ),
        flush=True,
    )
    if not result.physical_audit["passed"]:
        raise RuntimeError("Physical audit failed; preserve result and stop before further mesh")


def summarize(out):
    import numpy as np

    from physical_fpv.thermal_benchmark import thermal_numerics

    inputs = json.loads((out / "input.json").read_text())
    if source_digests() != inputs["source_sha256"]:
        raise ValueError("Frozen calculation changed before numerical comparison")
    coarse, fine = (load_snapshot(out, mesh) for mesh in (80, 120))
    if coarse.parameter_fingerprint != fine.parameter_fingerprint:
        raise ValueError("Numerical meshes differ in physical parameter/forcing identity")
    if coarse.parameter_fingerprint != inputs["parameter_current_fingerprint"]:
        raise ValueError("Saved results differ from recorded calculation identity")
    numerical = thermal_numerics(coarse, fine)
    stop = min(coarse.time_s[-1], fine.time_s[-1])
    times = np.unique(
        np.r_[coarse.time_s[coarse.time_s <= stop], fine.time_s[fine.time_s <= stop], stop]
    )
    dv = np.interp(times, coarse.time_s, coarse.voltage_v) - np.interp(
        times, fine.time_s, fine.voltage_v
    )
    dt = np.interp(times, coarse.time_s, coarse.temperature_k) - np.interp(
        times, fine.time_s, fine.temperature_k
    )
    numerical.update(
        {
            "shared_time_interval_s": [float(times[0]), float(stop)],
            "voltage_peak_difference_time_s": float(times[np.argmax(abs(dv))]),
            "temperature_peak_difference_time_s": float(times[np.argmax(abs(dt))]),
            "coarse_cutoff_time_s": float(coarse.time_s[-1]),
            "fine_cutoff_time_s": float(fine.time_s[-1]),
        }
    )
    cases = {str(n): json.loads((out / f"mesh{n}-report.json").read_text()) for n in (80, 120)}
    return {
        "inputs": inputs,
        "cases": cases,
        "spatial_numerical_check": numerical,
        "electrical_mathematical_gates_passed": cases["120"]["electrical_gates_passed"],
        "source_window_empirical_qualification_passed": cases["120"][
            "source_window_empirical_qualification_passed"
        ],
        "numerically_qualified_conditional_prediction_passed": (
            numerical["passed"] and cases["120"]["source_window_empirical_qualification_passed"]
        ),
        "independent_thermal_validation_established": False,
        "whole_cohort_validation_established": False,
        "blinded": False,
        "fitting_performed": False,
        "existing_failures": {
            "stanford_k1_voltage_rmse_mv": 191.474,
            "chen": "6/12",
            "oregan": "30/36",
        },
        "k6_history_contrast": "unresolved; three stopped downloads unchanged",
    }


def write_budget_failure(out, report=None):
    if report is None and (out / "report.json").exists():
        report = json.loads((out / "report.json").read_text())
    if report is not None:
        report["execution_budget_passed"] = False
        report["numerically_qualified_conditional_prediction_passed"] = False
        report["qualification_status"] = "unverified_shared_budget_exhausted"
        write_json(out / "report.json", report)
    write_json(out / "stage.json", {"status": "budget_exhausted", "meshes": [80, 120]})


def finish_summary(out, started, budget, clock=None):
    """Bound postprocessing and never leave a PASS after its shared deadline."""
    clock = time.monotonic if clock is None else clock
    remaining = budget - (clock() - started)
    if remaining <= 0:
        write_budget_failure(out)
        return "budget_exhausted"

    def expired(signum, frame):
        raise TimeoutError("Shared k2 budget exhausted during numerical summary")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    report = None
    try:
        report = summarize(out)
        if clock() - started >= budget:
            raise TimeoutError("Shared k2 budget exhausted before report publication")
        report["execution_budget_passed"] = True
        write_json(out / "report.json", report)
        if clock() - started >= budget:
            raise TimeoutError("Shared k2 budget exhausted while saving report")
        write_json(out / "stage.json", {"status": "completed", "meshes": [80, 120]})
        if clock() - started >= budget:
            raise TimeoutError("Shared k2 budget exhausted while saving completion")
        return "completed"
    except TimeoutError:
        signal.setitimer(signal.ITIMER_REAL, 0)
        write_budget_failure(out, report)
        return "budget_exhausted"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def qualification_status(report_path, execution_status):
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    numeric = report.get("spatial_numerical_check", {}).get("passed")
    empirical = report.get("source_window_empirical_qualification_passed")
    completed = execution_status == "completed" and report.get("execution_budget_passed") is True
    return {
        "numerical_targets_passed": numeric,
        "source_window_empirical_targets_passed": empirical,
        "missing_or_failed_numerical_stage_is_unverified": not completed or numeric is not True,
        "conditional_prediction_qualified": completed and numeric is True and empirical is True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=int, choices=(80, 120))
    parser.add_argument("--stage-budget", type=float, default=1200)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k2-pilot"))
    args = parser.parse_args()
    if not 0 < args.stage_budget <= 1200:
        parser.error("This pilot permits at most1200 seconds")
    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mesh or args.preflight_only:
        try:
            run_stage(args)
        except Exception as exc:
            write_json(
                args.out / "stage-error.json",
                {"type": type(exc).__name__, "message": str(exc), "mesh": args.mesh},
            )
            raise
        return 0
    if any((args.out / n).exists() for n in ("input.json", "report.json", "status.json")):
        parser.error("Preserve previous evidence; choose a new output directory")
    started = time.monotonic()
    status, returncode = "running", None
    for mesh in (80, 120):
        remaining = args.stage_budget - (time.monotonic() - started)
        if remaining <= 0:
            status = "budget_exhausted"
            break
        command = [
            sys.executable,
            "-u",
            __file__,
            "--mesh",
            str(mesh),
            "--stage-budget",
            str(remaining),
            "--out",
            str(args.out),
        ]
        with (args.out / f"mesh{mesh}-solver.log").open("w") as log:
            child = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(
                    os.environ,
                    OMP_NUM_THREADS="1",
                    OPENBLAS_NUM_THREADS="1",
                    PYBAMM_DISABLE_TELEMETRY="true",
                ),
            )
            while child.poll() is None:
                elapsed = time.monotonic() - started
                progress = {
                    "status": "running",
                    "mesh": mesh,
                    "elapsed_s": elapsed,
                    "budget_s": args.stage_budget,
                }
                write_json(args.out / "progress.json", progress)
                print(json.dumps(progress), flush=True)
                if elapsed >= args.stage_budget:
                    child.kill()
                    child.wait()
                    status = "budget_exhausted"
                    break
                time.sleep(min(10, args.stage_budget - elapsed))
            returncode = child.returncode
        if status == "budget_exhausted" or returncode != 0:
            status = (
                "budget_exhausted" if status == "budget_exhausted" else "solver_or_physical_failure"
            )
            break
    if status == "running":
        try:
            status = finish_summary(args.out, started, args.stage_budget)
        except Exception as exc:
            status = "postprocessing_failure"
            write_json(
                args.out / "summary-error.json", {"type": type(exc).__name__, "message": str(exc)}
            )
    elapsed = time.monotonic() - started
    if status == "completed" and elapsed >= args.stage_budget:
        status = "budget_exhausted"
        write_budget_failure(args.out)
    result = {
        "status": status,
        "return_code": returncode,
        "elapsed_s": elapsed,
        "budget_s": args.stage_budget,
        "empirical_disagreement_is_separate_from_execution_status": True,
        **qualification_status(args.out / "report.json", status),
    }
    write_json(args.out / "status.json", result)
    print(json.dumps(result), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
