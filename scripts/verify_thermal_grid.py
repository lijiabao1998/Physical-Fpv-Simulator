"""Bound one representative ORegan80-grid run and persist progress and exact outcomes."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def worker_command(args):
    return [
        sys.executable,
        "-u",
        __file__,
        "--worker",
        "--mesh",
        str(args.mesh),
        "--timeout",
        str(args.timeout),
        "--out",
        str(args.out),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--mesh", type=int, choices=[80, 120], default=80)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", type=Path, default=Path("results/thermal-grid80-representative"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1200:
        parser.error("Representative diagnostic is bounded to 1–1200 seconds")
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
            mesh_points=args.mesh,
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
        if args.mesh == 120:
            import numpy as np

            reference_path = Path("docs/benchmarks/thermal-grid80-reference.csv")
            reference_manifest = json.loads(
                Path("docs/benchmarks/thermal-reference-manifest.json").read_text()
            )
            if pybamm.__version__ != reference_manifest["pybamm_version"]:
                raise ValueError("PyBaMM version differs from grid80 reference")
            metadata_bytes = Path("docs/benchmarks/thermal-representative-grid80.json").read_bytes()
            if hashlib.sha256(metadata_bytes).hexdigest() != reference_manifest["metadata_sha256"]:
                raise ValueError("Reference metadata checksum mismatch")
            raw = reference_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference_manifest["csv_sha256"]:
                raise ValueError("Reference grid80 checksum mismatch")
            if result.parameter_fingerprint != reference_manifest["parameter_fingerprint"]:
                raise ValueError("Physical parameters or initial/boundary state differ from grid80")
            reference = np.loadtxt(reference_path, delimiter=",", skiprows=1)
            stop = min(reference[-1, 0], result.time_s[-1])
            common = np.unique(
                np.r_[
                    reference[reference[:, 0] <= stop, 0],
                    result.time_s[result.time_s <= stop],
                    stop,
                ]
            )
            delta_v = np.interp(common, reference[:, 0], reference[:, 1]) - np.interp(
                common, result.time_s, result.voltage_v
            )
            delta_t = np.interp(common, reference[:, 0], reference[:, 3]) - np.interp(
                common, result.time_s, result.temperature_k
            )
            voltage = float(max(abs(delta_v)))
            temperature = float(max(abs(delta_t)))
            capacity = float(
                abs(reference[-1, 2] - result.capacity_ah[-1]) / result.capacity_ah[-1]
            )
            comparison = {
                "reference_mesh": 80,
                "candidate_mesh": 120,
                "reference_sha256": reference_manifest["csv_sha256"],
                "voltage_max_difference_v": voltage,
                "temperature_max_difference_k": temperature,
                "capacity_relative_difference": capacity,
                "voltage_peak_time_s": float(common[np.argmax(abs(delta_v))]),
                "temperature_peak_time_s": float(common[np.argmax(abs(delta_t))]),
                "common_interval_s": [float(common[0]), float(stop)],
                "reference_cutoff_time_s": float(reference[-1, 0]),
                "candidate_cutoff_time_s": float(result.time_s[-1]),
                "physical_audit_passed": result.physical_audit["passed"],
                "passed": voltage <= 0.005
                and temperature <= 0.1
                and capacity <= 0.01
                and result.physical_audit["passed"]
                and result.metadata()["voltage_cutoff_reached"],
                "scope": "single representative case; no whole-cohort validation",
            }
            (args.out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
            print(json.dumps(comparison), flush=True)
        print(json.dumps(metadata), flush=True)
        return 0
    start = time.monotonic()
    environment = dict(os.environ, PYBAMM_DISABLE_TELEMETRY="true", OMP_NUM_THREADS="1")
    with (args.out / "solver.log").open("w") as log:
        process = subprocess.Popen(
            worker_command(args),
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
                "scope": f"Single 5 A, 25 degC representative mesh {args.mesh} diagnostic",
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
            "scientific_convergence_passed": (
                json.loads((args.out / "comparison.json").read_text())["passed"]
                if status == "completed" and (args.out / "comparison.json").exists()
                else None
            ),
            "note": "A completed fine-grid solve still needs comparison to the coarse result",
        }
        (args.out / "status.json").write_text(json.dumps(result, indent=2) + "\n")
        (args.out / "progress.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
