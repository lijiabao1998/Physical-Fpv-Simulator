"""A low voltage error must never conceal failed charge closure or missing mesh120."""

import importlib.util
import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pybamm
import pytest


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path("scripts").resolve()))
    spec = importlib.util.spec_from_file_location(
        "verify_low_rate_evidence", "scripts/verify_stanford_k2_low_rate_evidence.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_exact_oracle_has_independent_signed_ramp_and_units(monkeypatch):
    from physical_fpv.current_profile import CurrentProfile

    m = module(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("Independent oracle must not call production integration")

    monkeypatch.setattr(CurrentProfile, "charge_integral_ah", forbidden)
    got = m.exact_piecewise_charge([0, 0.5, 2], [0.25, 0.75, -0.25], [0, 0.25, 0.5, 1, 2])
    expected = [
        float(v / 3600)
        for v in (Fraction(0), Fraction(3, 32), Fraction(1, 4), Fraction(13, 24), Fraction(5, 8))
    ]
    np.testing.assert_array_equal(got, expected)
    with pytest.raises(ValueError, match="outside"):
        m.exact_piecewise_charge([0, 1], [1, 1], [1.01])
    with pytest.raises(ValueError, match="knots"):
        m.exact_piecewise_charge([0, 0], [1, 1], [0])


def test_saved_failed_experiment_reproduces_without_solver_or_network(monkeypatch):
    import urllib.request

    m = module(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved evidence verification must not solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = m.verify()
    saved = json.loads(Path("docs/benchmarks/stanford-k2-low-rate-model-result.json").read_text())
    assert set(result.pop("verification_runtime_versions")) == {
        "python",
        "pybamm",
        "numpy",
        "casadi",
        "scipy",
        "pybammsolvers",
    }
    saved.pop("verification_runtime_versions")
    m.require_reproduction(saved, result)
    assert not result["scientific_qualification_passed"]
    assert not result["mesh120_executed"] and not result["mesh_convergence_available"]
    assert result["coarse_empirical"]["voltage_rmse_v"] < 0.05
    assert not result["coarse_empirical"]["electrical_gates_passed"]
    diagnosis = result["charge_closure_diagnosis"]
    assert diagnosis["solver_capacity_vs_exact_max_ah"] > 1e-6
    assert diagnosis["endpoint_error_ah"] < 1e-6
    assert diagnosis["source_integrator_vs_exact_max_ah"] < 1e-12
    assert diagnosis["compiled_current_vs_source_max_a"] < 1e-15
    assert diagnosis["maximum_error_time_s"] == 61597


def test_changed_archive_part_path_or_bytes_are_rejected(monkeypatch, tmp_path):
    m = module(monkeypatch)
    path = tmp_path / "docs/benchmarks/stanford-k2-low-rate-model-artifact.json"
    path.parent.mkdir(parents=True)
    manifest = json.loads(
        Path("docs/benchmarks/stanford-k2-low-rate-model-artifact.json").read_text()
    )
    manifest["parts"][0]["path"] = "../outside"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="path changed"):
        m.archive_bytes(tmp_path)
    manifest["parts"][0]["path"] = "docs/benchmarks/stanford-k2-low-rate-model-evidence.zip.001"
    (tmp_path / manifest["parts"][0]["path"]).write_bytes(b"wrong bytes")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash/size"):
        m.archive_bytes(tmp_path)
