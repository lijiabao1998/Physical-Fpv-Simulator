"""Saved-rate comparisons cannot hide support, sign or provenance changes."""

import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
module = importlib.import_module("compare_stanford_k2_qualified_rates")
combinations, run, sample = module.combinations, module.run, module.sample
require_reproduction = importlib.import_module("compare_stanford_k2_rates").require_reproduction


def synthetic():
    time = np.array([0.0, 18000.0])
    observed = np.column_stack((time, [1.0, 1.0], [4.0, 3.0], [298.0, 299.0]))
    curve = {
        "time_s": time,
        "voltage_v": np.array([4.02, 3.02]),
        "temperature_k": np.array([298.0, 299.0]),
        "capacity_ah": np.array([0.0, 5.0]),
    }
    return observed, curve


def test_two_rate_residual_identity_and_mesh_sensitivity():
    observed, curve = synthetic()
    low = {80: curve, 120: {**curve, "voltage_v": curve["voltage_v"] + 0.001}}
    high = {80: {**curve, "voltage_v": curve["voltage_v"] + 0.07}, 120: curve}
    points = combinations(observed, observed, low, high)
    assert len(points) == 9
    for point in points:
        assert point["observed_gap_v"] == 0
        assert point["pairs"]["low120_high120"]["gap_discrepancy_v"] == pytest.approx(0.001)
        assert point["saved_combination_min_v"] == pytest.approx(-0.07)
        assert point["saved_combination_max_v"] == pytest.approx(0.001)
        assert point["same_discrepancy_sign_all_combinations"] is False


@pytest.mark.parametrize("field", ["time_s", "voltage_v", "temperature_k", "capacity_ah"])
def test_nonfinite_model_values_rejected(field):
    observed, curve = synthetic()
    curve[field] = curve[field].copy()
    curve[field][0] = np.nan
    with pytest.raises(ValueError):
        sample(observed, curve, 1.0)


def test_no_extrapolation_or_repeated_time():
    observed, curve = synthetic()
    with pytest.raises(ValueError, match="outside"):
        sample(observed, {**curve, "time_s": np.array([0.0, 100.0])}, 1.0)
    with pytest.raises(ValueError, match="increasing"):
        sample(observed, {**curve, "time_s": np.array([0.0, 0.0])}, 1.0)


def test_missing_mesh_rejected():
    observed, curve = synthetic()
    with pytest.raises(ValueError, match="Exactly two"):
        combinations(observed, observed, {120: curve}, {80: curve, 120: curve})


def test_saved_result_reproduces_without_network_or_solver(monkeypatch):
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved-data audit must not download or solve")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = run()
    saved = json.loads(
        (ROOT / "docs/benchmarks/stanford-k2-qualified-rate-result.json").read_text()
    )
    require_reproduction(saved, result)
    assert result["historical_high_electrical_gates_passed"] is False
    assert result["unique_physical_cause_identified"] is False
    saved["points"][0]["pairs"]["low120_high120"]["gap_discrepancy_v"] += 0.001
    with pytest.raises(ValueError, match="does not reproduce"):
        require_reproduction(saved, result)
