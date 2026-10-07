"""Reuse a verified numerical result only when its calculation inputs match exactly."""

import argparse
import ast
import hashlib
import json
from pathlib import Path

CALCULATION_FILES = (
    "src/physical_fpv/core.py",
    "scripts/verify_thermal_grid.py",
    "requirements-lock.txt",
    "pyproject.toml",
    "docs/benchmarks/thermal-grid80-reference.csv",
    "docs/benchmarks/thermal-reference-manifest.json",
    "docs/benchmarks/thermal-representative-grid80.json",
)


def calculation_contract(root):
    root = Path(root)
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in CALCULATION_FILES
    }
    # The numerical runner uses this serialization helper, not benchmark attribution code.
    source = (root / "src/physical_fpv/validation.py").read_text()
    function = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == "write_timeseries"
    )
    hashes["validation.py::write_timeseries"] = hashlib.sha256(
        ast.dump(function, include_attributes=False).encode()
    ).hexdigest()
    return hashes


def reusable_evidence(root, evidence):
    if calculation_contract(root) != evidence["calculation_contract"]:
        return False
    comparison = evidence["comparison"]
    return bool(
        comparison["reference_mesh"] == 80
        and comparison["candidate_mesh"] == 120
        and comparison["voltage_max_difference_v"] <= 0.005
        and comparison["temperature_max_difference_k"] <= 0.1
        and comparison["capacity_relative_difference"] <= 0.01
        and comparison["physical_audit_passed"]
        and comparison["passed"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("results/grid120"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    evidence = json.loads(Path("docs/benchmarks/grid120-verified-evidence.json").read_text())
    reuse = reusable_evidence(Path.cwd(), evidence)
    if reuse:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "comparison.json").write_text(
            json.dumps(evidence["comparison"], indent=2) + "\n"
        )
        (args.out / "reused-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        (args.out / "status.json").write_text(
            json.dumps(
                {
                    "status": "reused_verified_calculation",
                    "new_simulation_run": False,
                    "scientific_convergence_passed": True,
                    "source_ci_run_id": evidence["ci_run_id"],
                    "source_commit_sha": evidence["commit_sha"],
                    "note": "Exact calculation inputs are unchanged; only packaging changed. "
                    "This remains one representative case, not whole-cohort validation.",
                },
                indent=2,
            )
            + "\n"
        )
    if args.github_output:
        with args.github_output.open("a") as f:
            f.write(f"reuse={'true' if reuse else 'false'}\n")
    print(json.dumps({"reuse": reuse, "source_ci_run_id": evidence["ci_run_id"]}))


if __name__ == "__main__":
    main()
