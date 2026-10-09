"""Reproducible CPU-only command-line research tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.core import ModelConfig, simulate
from physical_fpv.data import download_data
from physical_fpv.materials import analytic_material_example
from physical_fpv.thermal_benchmark import run_thermal_benchmark
from physical_fpv.thermal_data import fetch_thermal_data, save_cohort_inspection
from physical_fpv.validation import run_benchmark, write_timeseries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Physical FPV battery research core")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser(
        "verify-replay", help="Verify saved replay ZIPs offline; never solve or download"
    )
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--inputs", type=Path, required=True)
    verify.add_argument("--outputs", type=Path, required=True)
    verify.add_argument("--out", type=Path, help="Optional JSON verification report")
    verify.add_argument("--require-numerical-pass", action="store_true")
    verify.add_argument("--require-empirical-pass", action="store_true")
    fetch = sub.add_parser("fetch-data", help="Download three checksum-pinned CC-BY-4.0 traces")
    fetch.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    sim = sub.add_parser("simulate", help="Run bounded single-cell constant-current simulation")
    sim.add_argument("--current", type=float, default=5.0, help="Discharge current [A]")
    sim.add_argument("--model", choices=["SPM", "SPMe", "DFN"], default="DFN")
    sim.add_argument("--thermal", choices=["isothermal", "lumped"], default="isothermal")
    sim.add_argument("--out", type=Path, default=Path("results/simulation"))
    benchmark = sub.add_parser("benchmark", help="Compare every cell/rate without fitting")
    benchmark.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    benchmark.add_argument("--model", choices=["SPM", "SPMe", "DFN"], default="DFN")
    benchmark.add_argument("--thermal", choices=["isothermal", "lumped"], default="isothermal")
    benchmark.add_argument("--out", type=Path, default=Path("results/benchmark"))
    benchmark.add_argument(
        "--skip-numerics", action="store_true", help="Exploration only; research gate cannot pass"
    )
    benchmark.add_argument(
        "--require-pass",
        action="store_true",
        help="Exit 2 if frozen research acceptance gates fail",
    )
    sub.add_parser("material-method-check", help="Analytical jump network, not a real material")
    thermal_fetch = sub.add_parser("thermal-fetch-data", help="Fetch checksum-pinned TEC archive")
    thermal_fetch.add_argument(
        "--archive", type=Path, default=Path("data/oregan/raw/validation.zip")
    )
    thermal_inspect = sub.add_parser(
        "thermal-inspect", help="Inspect raw quality, units and sensor flags"
    )
    thermal_inspect.add_argument(
        "--archive", type=Path, default=Path("data/oregan/raw/validation.zip")
    )
    thermal_inspect.add_argument(
        "--out", type=Path, default=Path("results/thermal-data-inspection.json")
    )
    thermal_bench = sub.add_parser(
        "thermal-benchmark", help="Run fixed ORegan2022 thermal reproduction"
    )
    thermal_bench.add_argument(
        "--archive", type=Path, default=Path("data/oregan/raw/validation.zip")
    )
    thermal_bench.add_argument("--out", type=Path, default=Path("results/thermal"))
    thermal_bench.add_argument("--skip-numerics", action="store_true")
    thermal_bench.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-replay":
            from physical_fpv.replay_verification import verify_replay

            if args.out and args.out.resolve() in {
                p.resolve() for p in (args.receipt, args.inputs, args.outputs)
            }:
                raise ValueError("Verification output must not overwrite input evidence")
            report = verify_replay(args.receipt, args.inputs, args.outputs)
            text = json.dumps(report, indent=2, allow_nan=False)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(text + "\n", encoding="utf-8")
            print(text)
            if args.require_numerical_pass and report["numerical"]["passed"] is not True:
                return 2
            if args.require_empirical_pass and report["empirical"]["passed"] is not True:
                return 2
        elif args.command == "fetch-data":
            print(json.dumps(download_data(args.data_dir), indent=2))
        elif args.command == "simulate":
            result = simulate(
                ModelConfig(model=args.model, thermal=args.thermal, current_a=args.current)
            )
            write_timeseries(args.out / "timeseries.csv", result)
            write_evidence_attribution(args.out, [])
            text = json.dumps(result.metadata(), indent=2, allow_nan=False)
            (args.out / "metadata.json").write_text(text + "\n", encoding="utf-8")
            print(text)
        elif args.command == "benchmark":
            report = run_benchmark(
                args.data_dir, args.out, args.model, args.thermal, numerical=not args.skip_numerics
            )
            print((args.out / "report.md").read_text(encoding="utf-8"))
            if args.require_pass and not report["research_gate_passed"]:
                return 2
        elif args.command == "thermal-fetch-data":
            print(json.dumps(fetch_thermal_data(args.archive), indent=2))
        elif args.command == "thermal-inspect":
            report = save_cohort_inspection(args.archive, args.out)
            print(
                json.dumps(
                    {
                        "files": report["files"],
                        "unique_cells": report["unique_cells"],
                        "duplicates": report["duplicate_records"],
                        "output": str(args.out),
                    }
                )
            )
        elif args.command == "thermal-benchmark":
            report = run_thermal_benchmark(args.archive, args.out, not args.skip_numerics)
            print((args.out / "report.md").read_text(encoding="utf-8"))
            if args.require_pass and not (
                report["all_empirical_targets_passed"] and report["all_numerical_targets_passed"]
            ):
                return 2
        else:
            print(json.dumps(analytic_material_example(), indent=2, allow_nan=False))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Research run stopped: {error}\n")
    return 0
