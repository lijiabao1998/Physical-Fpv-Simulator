"""Recorded state algebra must preserve failure and never run a new simulation."""

import importlib.util
import json
import shutil
import urllib.request
from pathlib import Path

import pybamm
import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "state_analysis", "scripts/analyze_stanford_k2_states.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def copied(root):
    (root / "docs/benchmarks").mkdir(parents=True)
    for name in ("stanford-k2-state-summary.json", "stanford-k2-state-scalars.csv.gz"):
        shutil.copyfile(Path("docs/benchmarks") / name, root / "docs/benchmarks" / name)


def test_state_analysis_is_exactly_reproducible_without_solve_or_download(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("State analysis must not solve or acquire source data")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = module().analyze()
    saved = json.loads(Path("docs/benchmarks/stanford-k2-state-analysis.json").read_text())
    assert result == saved
    assert result["scientific_empirical_pass"] is False
    assert result["ocp_algebra_reconstruction_error_v"] < 1e-6
    assert (
        result["direct_temperature_ocp_diagnostic"]["indirect_temperature_effects_isolated"]
        is False
    )


def test_modified_scalar_data_rejected(tmp_path):
    copied(tmp_path)
    path = tmp_path / "docs/benchmarks/stanford-k2-state-scalars.csv.gz"
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="scalar archive"):
        module().analyze(tmp_path)


def test_scientific_failure_cannot_be_promoted(tmp_path):
    copied(tmp_path)
    path = tmp_path / "docs/benchmarks/stanford-k2-state-summary.json"
    data = json.loads(path.read_text())
    data["records"]["empirical-report.json"]["source_window_empirical_qualification_passed"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="scientific failure"):
        module().analyze(tmp_path)


def test_interval_mean_uses_saved_linear_trace():
    import numpy as np

    assert module().mean_on(np.array([0.0, 2.0]), np.array([1.0, 3.0]), 0.5, 1.5) == 2.0
