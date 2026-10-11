"""Bounded audit of the isolated FPV implementation, with separate scientific gates."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "results" / "fpv-candidate-audit"
    out.mkdir(parents=True, exist_ok=True)
    source = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "src/physical_fpv/fpv").rglob("*"))
        if p.is_file() and "__pycache__" not in str(p)
    }
    result = {
        "base_commit": "1990e23ce35b16d73d2d65b0d9a586064963dd6a",
        "candidate_source_sha256": source,
        "empirical_gate": "NOT ESTABLISHED",
        "preserved_failures": [
            "Chen 6/12 fail",
            "ORegan combined empirical 30/36 fail",
            "Stanford high-rate fail",
        ],
        "stages": {},
    }
    commands = {
        "focused_tests": [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *[str(p) for p in sorted((ROOT / "tests").glob("test_fpv_*.py"))],
        ],
        "lint": [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        "format": [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        "demo": [sys.executable, "-m", "physical_fpv.fpv", "demo", "--out", str(out / "demo.json")],
        "replay": [
            sys.executable,
            "-m",
            "physical_fpv.fpv",
            "replay",
            "--input",
            str(out / "demo.json"),
            "--out",
            str(out / "replay.json"),
        ],
    }
    for name, command in commands.items():
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=600)
        (out / f"{name}.log").write_text(completed.stdout + completed.stderr)
        result["stages"][name] = {
            "exit_code": completed.returncode,
            "passed": completed.returncode == 0,
        }
    result["software_checks_passed"] = all(x["passed"] for x in result["stages"].values())
    (out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["stages"], indent=2))
    return 0 if result["software_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
