"""Reuse the exact recorded pilot outcome, including failures, without another solve."""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


def runner(root):
    spec = importlib.util.spec_from_file_location(
        "recorded_stanford_runner", root / "scripts/run_stanford_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calculation_contract(root):
    return {
        p: hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in runner(root).CALCULATION_FILES
    }


def reusable_attempt(root, evidence):
    try:
        run_id = evidence["ci_run_id"]
        status = evidence["supervisor_status"]
        if (
            not isinstance(run_id, int)
            or run_id <= 0
            or re.fullmatch(r"[0-9a-f]{40}", evidence["commit_sha"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", evidence["artifact_zip_sha256"]) is None
            or evidence["source_sha256"] != calculation_contract(root)
        ):
            return False
        if status["status"] not in {"completed", "budget_exhausted", "solver_or_resource_failure"}:
            return False
        report = evidence.get("report")
        if status["status"] == "completed":
            return (
                isinstance(report, dict)
                and set(report["cases"]) == {"80", "120"}
                and all(
                    report["cases"][str(n)]["model"]["config"]["mesh_points"] == n
                    for n in (80, 120)
                )
                and isinstance(report["spatial_numerical_check"]["passed"], bool)
                and report["inputs"]["source_sha256"] == evidence["source_sha256"]
                and report["inputs"]["source_commit_sha"] == evidence["commit_sha"]
                and status["missing_numerical_stage_is_unverified"] is False
            )
        return report is None and status["missing_numerical_stage_is_unverified"] is True
    except (KeyError, TypeError, ValueError, OSError):
        return False


def export_reused(root, evidence, output):
    from physical_fpv.attribution import write_evidence_attribution

    if not reusable_attempt(root, evidence):
        raise ValueError("Recorded attempt does not match the current calculation")
    module = runner(root)
    output.mkdir(parents=True, exist_ok=True)
    status = dict(evidence["supervisor_status"])
    status.update(
        {
            "new_simulation_run": False,
            "execution_origin": "reused_recorded_attempt",
            "source_ci_run_id": evidence["ci_run_id"],
            "source_commit_sha": evidence["commit_sha"],
        }
    )
    module.write_json(output / "status.json", status)
    module.write_json(output / "reused-evidence.json", evidence)
    write_evidence_attribution(output, ["stanford2021", "oregan2022_parameters"])
    if evidence.get("report") is not None:
        module.write_json(output / "report.json", evidence["report"])
    for mesh, report in evidence.get("partial_case_reports", {}).items():
        if mesh not in {"80", "120"}:
            raise ValueError("Unexpected cached mesh")
        module.write_json(output / f"mesh{mesh}-report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k1-pilot"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    path = Path("docs/benchmarks/stanford-k1-v3-verified-evidence.json")
    evidence = json.loads(path.read_text()) if path.exists() else None
    reuse = evidence is not None and reusable_attempt(Path.cwd(), evidence)
    if reuse:
        export_reused(Path.cwd(), evidence, args.out)
    if args.github_output:
        with args.github_output.open("a") as handle:
            handle.write(f"reuse={'true' if reuse else 'false'}\n")
    print(
        json.dumps(
            {
                "reuse": reuse,
                "source_ci_run_id": evidence["ci_run_id"] if reuse else None,
                "new_simulation_run": False,
            }
        )
    )


if __name__ == "__main__":
    main()
