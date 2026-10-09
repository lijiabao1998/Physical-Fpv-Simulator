"""Bounded paired prefix solves isolate integration scheduling from measured forcing."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from run_stanford_pilot import write_json

PROTOCOL_SHA256 = "03691f9d38a2b45c898ede4669141f4d612599743200cfc6a38a2298f1ac35d9"
HORIZON_S = 60.0


def worker(args):
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
    import faulthandler
    from dataclasses import asdict

    import numpy as np
    import pybamm

    from physical_fpv.core import parameter_fingerprint
    from physical_fpv.stanford_benchmark import prepare_pilot

    faulthandler.dump_traceback_later(30, repeat=True)
    manifest = json.loads(Path("data/stanford-manifest.json").read_text())
    _, profile, config, assumptions = prepare_pilot(Path("data/stanford/raw"), manifest)
    previous = json.loads(Path("docs/benchmarks/stanford-k1-verified-evidence.json").read_text())
    previous = previous["inputs"]
    if (
        asdict(config) != previous["config"]
        or profile.fingerprint_sha256 != previous["assumptions"]["current_profile_sha256"]
    ):
        raise ValueError("Diagnostic differs from the frozen full-pilot input")
    parameters = pybamm.ParameterValues(config.parameter_set)
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
    parameters.update(
        {
            "Current function [A]": pybamm.Interpolant(
                profile.time_s,
                profile.current_a,
                pybamm.t,
                interpolator="linear",
                extrapolate=False,
            )
        }
    )
    model = pybamm.lithium_ion.DFN(options={"thermal": "lumped"})
    model.events.append(
        pybamm.Event(
            "Research temperature envelope",
            config.max_temperature_k - model.variables["Volume-averaged cell temperature [K]"],
        )
    )
    native = profile.time_s[(profile.time_s >= 0) & (profile.time_s <= HORIZON_S)]
    output = np.unique(np.r_[native, np.arange(0, HORIZON_S + 5, 5), HORIZON_S])
    stops = (
        np.unique(np.r_[native, HORIZON_S])
        if args.mode == "all_knots"
        else np.array([0, HORIZON_S])
    )
    options = {"num_threads": 1, "print_stats": True}
    if args.mode == "adaptive_dt1":
        options["dt_max"] = 1.0
    solver = pybamm.IDAKLUSolver(rtol=config.tolerance, atol=config.tolerance, options=options)
    timings = {}
    for method in ("set_up", "_integrate"):
        original = getattr(solver, method)

        def timed(*pos, _name=method, _original=original, **kw):
            write_json(args.out / "stage.json", {"stage": _name, "mode": args.mode})
            started = time.monotonic()
            result = _original(*pos, **kw)
            timings[_name] = timings.get(_name, 0) + time.monotonic() - started
            return result

        setattr(solver, method, timed)
    simulation = pybamm.Simulation(
        model,
        parameter_values=parameters,
        solver=solver,
        var_pts={"x_n": 80, "x_s": 40, "x_p": 80, "r_n": 80, "r_p": 80},
    )
    started = time.monotonic()
    solution = simulation.solve(stops, t_interp=output)
    if abs(solution.t[-1] - HORIZON_S) > 1e-9:
        raise RuntimeError("Prefix did not reach its declared horizon")

    def get(name):
        return np.asarray(solution[name](output), dtype=float).reshape(-1)

    voltage, temperature = get("Terminal voltage [V]"), get("Volume-averaged cell temperature [K]")
    charge, lithium = get("Discharge capacity [A.h]"), get("Total lithium [mol]")
    heating, cooling = get("Total heating [W]"), get("Surface total cooling [W]")
    heat_capacity = (
        get("Volume-averaged effective heat capacity [J.K-1.m-3]") * parameters["Cell volume [m3]"]
    )
    bounds = {}
    for electrode in ("Negative", "Positive"):
        c = np.asarray(solution[f"{electrode} particle concentration [mol.m-3]"].entries)
        surface = np.asarray(
            solution[f"{electrode} particle surface concentration [mol.m-3]"].entries
        )
        maximum = parameters[f"Maximum concentration in {electrode.lower()} electrode [mol.m-3]"]
        bounds[electrode.lower()] = {
            "minimum": min(float(c.min()), float(surface.min())),
            "maximum": max(float(c.max()), float(surface.max())),
            "limit": maximum,
            "passed": bool(
                np.isfinite(c).all()
                and np.isfinite(surface).all()
                and min(c.min(), surface.min()) >= -1e-6
                and max(c.max(), surface.max()) <= maximum + 1e-6
            ),
        }
    electrolyte = np.asarray(solution["Electrolyte concentration [mol.m-3]"].entries)
    charge_error = float(np.max(abs(charge - profile.charge_integral_ah(output))))
    lithium_drift = float(np.max(abs(lithium - lithium[0])) / lithium[0])
    heat_error = float(
        abs(np.trapezoid(heat_capacity, temperature) - np.trapezoid(heating + cooling, output))
        / max(abs(np.trapezoid(abs(heating), output)), 1.0)
    )
    physical = bool(
        charge_error <= 1e-6
        and lithium_drift <= 1e-6
        and heat_error <= 0.01
        and all(b["passed"] for b in bounds.values())
        and np.isfinite(electrolyte).all()
        and electrolyte.min() > 0
        and all(np.isfinite(v).all() for v in (voltage, temperature, charge, lithium))
    )
    report = {
        "mode": args.mode,
        "protocol_sha256": PROTOCOL_SHA256,
        "config": asdict(config),
        "current_profile_sha256": profile.fingerprint_sha256,
        "parameter_fingerprint": fingerprint,
        "horizon_s": HORIZON_S,
        "integration_stop_count": len(stops),
        "common_output_count": len(output),
        "setup_and_integration_timings_s": timings,
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "charge_integral_error_ah": charge_error,
        "lithium_inventory_relative_drift": lithium_drift,
        "thermal_energy_relative_residual": heat_error,
        "concentration_bounds": bounds,
        "electrolyte_min_mol_m3": float(electrolyte.min()),
        "physical_audit_passed": physical,
        "solver_options": options,
        "termination": str(solution.termination),
        "source": assumptions["source"],
        "empirical_validation_performed": False,
        "pybamm_version": pybamm.__version__,
    }
    np.savetxt(
        args.out / "timeseries.csv",
        np.column_stack((output, voltage, temperature, charge, lithium)),
        delimiter=",",
        header="time_s,voltage_v,temperature_k,charge_ah,lithium_mol",
        comments="",
    )
    write_json(args.out / "report.json", report)
    print(json.dumps(report), flush=True)


def compare(root, first, second):
    import numpy as np

    left, right = [root / n for n in (first, second)]
    if not all((p / "report.json").exists() for p in (left, right)):
        return {"first": first, "second": second, "status": "incomplete", "passed": False}
    a, b = [np.loadtxt(p / "timeseries.csv", delimiter=",", skiprows=1) for p in (left, right)]
    ra, rb = [json.loads((p / "report.json").read_text()) for p in (left, right)]
    if (
        not np.array_equal(a[:, 0], b[:, 0])
        or ra["parameter_fingerprint"] != rb["parameter_fingerprint"]
    ):
        raise ValueError("Scheduling comparison changed output grid or physics")
    dv, dt, dq = [float(np.max(abs(a[:, i] - b[:, i]))) for i in (1, 2, 3)]
    return {
        "first": first,
        "second": second,
        "status": "completed",
        "voltage_max_difference_v": dv,
        "temperature_max_difference_k": dt,
        "charge_max_difference_ah": dq,
        "passed": bool(
            dv <= 1e-4
            and dt <= 1e-3
            and dq <= 1e-6
            and ra["physical_audit_passed"]
            and rb["physical_audit_passed"]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["all_knots", "adaptive", "adaptive_dt1"])
    parser.add_argument("--out", type=Path, default=Path("results/stanford-scheduling-v1"))
    args = parser.parse_args()
    if (
        hashlib.sha256(Path("docs/stanford-scheduling-diagnostic.md").read_bytes()).hexdigest()
        != PROTOCOL_SHA256
    ):
        raise ValueError("Frozen scheduling diagnostic protocol changed")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mode:
        worker(args)
        return
    if (args.out / "summary.json").exists():
        raise ValueError("Preserve prior diagnostic evidence; select a new output directory")
    summaries = {}
    for mode in ("all_knots", "adaptive", "adaptive_dt1"):
        if mode == "adaptive_dt1" and compare(args.out, "all_knots", "adaptive")["passed"]:
            break
        folder = args.out / mode
        folder.mkdir(exist_ok=True)
        if (folder / "report.json").exists():
            raise ValueError("Do not overwrite an existing arm")
        started = time.monotonic()
        with (folder / "solver.log").open("w") as log:
            child = subprocess.Popen(
                [sys.executable, "-u", __file__, "--mode", mode, "--out", str(folder)],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, OMP_NUM_THREADS="1", PYBAMM_DISABLE_TELEMETRY="true"),
            )
            try:
                code = child.wait(timeout=120)
                status = "completed" if code == 0 else "solver_or_resource_failure"
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                code = child.returncode
                status = "budget_exhausted"
        summaries[mode] = {
            "status": status,
            "return_code": code,
            "elapsed_s": time.monotonic() - started,
        }
        write_json(folder / "status.json", summaries[mode])
        print(json.dumps({mode: summaries[mode]}), flush=True)
    comparisons = [compare(args.out, "all_knots", "adaptive")]
    if "adaptive_dt1" in summaries:
        comparisons += [
            compare(args.out, "all_knots", "adaptive_dt1"),
            compare(args.out, "adaptive", "adaptive_dt1"),
        ]
    write_json(
        args.out / "summary.json",
        {
            "protocol_sha256": PROTOCOL_SHA256,
            "arms": summaries,
            "comparisons": comparisons,
            "scope": "prefix scheduling diagnosis only; no full-pilot empirical result",
        },
    )
    print(json.dumps(comparisons), flush=True)


if __name__ == "__main__":
    main()
