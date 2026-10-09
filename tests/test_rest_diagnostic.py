import json
import subprocess
import sys
from pathlib import Path

import pybamm
import pytest


def test_published_initial_state_and_active_capacity_definitions():
    audit = json.loads(Path("docs/benchmarks/oregan-definition-audit.json").read_text())
    parameters = pybamm.ParameterValues("ORegan2022")
    for name, expected in audit["checked_values"].items():
        assert parameters[name] == expected


@pytest.mark.data
def test_no_solve_rest_diagnostic_is_reproducible_and_keeps_failures(tmp_path):
    if not Path("data/oregan/raw/validation.zip").exists():
        pytest.skip("Run physical-fpv thermal-fetch-data")
    subprocess.run(
        [sys.executable, "scripts/diagnose_rest_state.py", "--out", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads((tmp_path / "review.json").read_text())
    assert all(report["consistency_checks"].values())
    rest = report["protocol_audit"]["first_postdischarge_rest"]
    assert rest["maximum_absolute_recorded_current_a"] == 0
    assert not rest["equilibrium_established"]
    assert rest["last_windows"][-1]["voltage_change_v"] > 0
    assert not report["residual_diagnostics"]["scientific_gates_unchanged"]["voltage_rmse"]
    assert report["residual_diagnostics"]["full_measured_time_coverage"] < 1
    assert (tmp_path / "source-attribution.json").exists()
    assert (tmp_path / "licenses/TEC-BSD-3-Clause.txt").exists()
