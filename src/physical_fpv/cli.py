"""Reproducible CPU-only command-line research tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from physical_fpv.core import ModelConfig, simulate
from physical_fpv.data import download_data
from physical_fpv.materials import analytic_material_example
from physical_fpv.validation import run_benchmark, write_timeseries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Physical FPV battery research core")
    sub = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch-data":
            print(json.dumps(download_data(args.data_dir), indent=2))
        elif args.command == "simulate":
            result = simulate(
                ModelConfig(model=args.model, thermal=args.thermal, current_a=args.current)
            )
            write_timeseries(args.out / "timeseries.csv", result)
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
        else:
            print(json.dumps(analytic_material_example(), indent=2, allow_nan=False))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Research run stopped: {error}\n")
    return 0
