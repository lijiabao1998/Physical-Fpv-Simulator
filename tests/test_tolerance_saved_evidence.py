"""Reproduce the immutable tolerance experiment without another solve/download."""

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import pybamm
import pytest


def load():
    sys.path.insert(0, str(Path("scripts").resolve()))
    name = "verify_stanford_k2_tolerance_evidence"
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_complete_tolerance_evidence_reproduces_without_solve_or_download(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved evidence reproduction cannot solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = load().verify()
    assert result["joint_charge_and_tolerance_stability_supported"]
    assert result["tightened_charge_closure_max_abs_error_ah"] < 1e-6
    assert result["full_physical_audit"]["passed"]
    assert result["coarse_empirical"]["electrical_gates_passed"]
    assert result["final_state_observables_verified"] == 21
    assert len(result["ledger"]["stages"]) == 1
    assert not result["spatial_convergence_available"]
    assert not result["overall_model_qualification_passed"]
    assert not result["historical_high_rate_gate_passed"]


def test_tolerance_archive_rejects_substituted_part_path(tmp_path):
    module = load()
    original = json.loads(Path("docs/benchmarks/stanford-k2-tolerance-artifact.json").read_text())
    original["parts"][0]["path"] = "../other.zip"
    target = tmp_path / "docs/benchmarks/stanford-k2-tolerance-artifact.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="part path"):
        module.archive_bytes(tmp_path)
