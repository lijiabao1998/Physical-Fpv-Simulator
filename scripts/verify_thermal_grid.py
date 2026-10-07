"""Bound one representative ORegan80-grid run and persist progress and exact outcomes."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", type=Path, default=Path("results/thermal-grid80-representative"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 600:
        parser.error("Representative diagnostic is bounded to1–600 seconds")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.worker:
        import faulthandler
        import functools
        import resource
        from dataclasses import asdict

        from physical_fpv.core import ModelConfig, _simulation_template, pybamm, simulate
        from physical_fpv.validation import write_timeseries

        resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
        faulthandler.dump_traceback_later(60, repeat=True)
        config = ModelConfig(
            parameter_set="ORegan2022",
            thermal="lumped",
            current_a=5,
            mesh_points=80,
            initial_temperature_k=297.75,
            heat_transfer_coefficient_w_m2_k=15,
        )
        (args.out / "input.json").write_text(json.dumps(asdict(config), indent=2) + "\n")
        simulation = _simulation_template(
            config.model,
            config.thermal,
            config.parameter_set,
            config.mesh_points,
            config.tolerance,
            config.max_temperature_k,
            config.heat_transfer_coefficient_w_m2_k,
        )
        solver = pybamm.IDAKLUSolver(
            rtol=config.tolerance,
            atol=config.tolerance,
            options={"num_threads": 1, "print_stats": True},
        )
        simulation.solve = functools.partial(simulation.solve, solver=solver)
        start = time.monotonic()
        result = simulate(config)
        write_timeseries(args.out / "timeseries.csv", result)
        metadata = result.metadata()
        metadata["elapsed_seconds"] = time.monotonic() - start
        metadata["diagnostic_method"] = "default IDAKLU VM; solver statistics enabled"
        (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata), flush=True)
        return 0
    start = time.monotonic()
    environment = dict(os.environ, PYBAMM_DISABLE_TELEMETRY="true", OMP_NUM_THREADS="1")
    with (args.out / "solver.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", __file__, "--worker", "--out", str(args.out)],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        status = "running"
        while process.poll() is None:
            elapsed = time.monotonic() - start
            progress = {
                "status": status,
                "elapsed_seconds": elapsed,
                "budget_seconds": args.timeout,
                "pid": process.pid,
                "scope": "single5A25degC representative mesh80 diagnostic",
            }
            (args.out / "progress.json").write_text(json.dumps(progress, indent=2) + "\n")
            print(json.dumps(progress), flush=True)
            if elapsed >= args.timeout:
                process.kill()
                process.wait()
                status = "budget_exhausted"
                break
            time.sleep(min(10, args.timeout - elapsed))
        if status == "running":
            status = "completed" if process.returncode == 0 else "solver_or_resource_failure"
        result = {
            "status": status,
            "return_code": process.returncode,
            "elapsed_seconds": time.monotonic() - start,
            "budget_seconds": args.timeout,
            "scientific_convergence_passed": False,
            "note": "A completed fine-grid solve still needs comparison to the coarse result",
        }
        (args.out / "status.json").write_text(json.dumps(result, indent=2) + "\n")
        (args.out / "progress.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
