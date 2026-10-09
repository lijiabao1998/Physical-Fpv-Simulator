"""Immutable mesh-pair result reproduction, never another scientific execution."""

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import pybamm
import pytest


def load():
    sys.path.insert(0, str(Path("scripts").resolve()))
    name = "verify_stanford_k2_mesh120_evidence"
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_saved_mesh_pair_reproduces_without_solve_or_download(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved-data verification must not solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = load().verify()
    assert result["qualification"]["joint_mesh_pair_and_dataset_gates_passed"]
    assert result["original_mesh_comparison"]["full_numerical_qualification_passed"]
    assert not result["qualification"]["asymptotic_convergence_or_order_established"]
    assert not result["qualification"]["independent_validation_established"]
    assert not result["historical_high_rate_gate_passed"]
    assert len(result["ledger"]["stages"]) == 1
    assert result["ledger"]["stages"][0]["mesh"] == 120
    for mesh in ("mesh80", "mesh120"):
        assert result[mesh]["native_endpoint_observables_verified"] == 21
        assert result[mesh]["physical_audit"]["passed"]
        assert result[mesh]["charge_closure_diagnosis"]["failing_sample_count"] == 0


def test_mesh120_archive_rejects_substituted_part(tmp_path):
    module = load()
    data = json.loads(Path("docs/benchmarks/stanford-k2-mesh120-artifact.json").read_text())
    data["parts"][0]["path"] = "../replacement.zip"
    target = tmp_path / "docs/benchmarks/stanford-k2-mesh120-artifact.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="part path"):
        module.archive_bytes(tmp_path)
