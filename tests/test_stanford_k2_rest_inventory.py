"""No-fit, no-solve compatibility audit and explicit missing-interval conventions."""

import importlib.util
import json
import urllib.request
from pathlib import Path

import numpy as np
import pybamm
import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "rest_audit", "scripts/audit_stanford_k2_rest_inventory.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_saved_source_audit_reproduces_without_solve_download_or_fit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rest audit must not solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = module().audit()
    assert result == json.loads(Path("docs/benchmarks/stanford-k2-rest-inventory.json").read_text())
    assert result["fitting_performed"] is False
    assert result["equilibrium_established"] is False
    assert result["measurement_uncertainty_supplied"] is False
    assert result["new_dynamic_solve_recommended_now"] is False


def test_actual_sample_and_exact_window_are_distinct_estimators():
    result = module().last_window(
        np.array([0, 5, 10]), np.array([0, 10, 20]), np.array([20, 20, 20]), 6
    )
    assert result["endpoint_minus_first_actual_sample_v"] == 10
    assert result["endpoint_minus_interpolated_exact_window_v"] == 12
    assert result["first_actual_sample_duration_s"] == 5


def test_gap_conventions_are_explicit_not_fitted():
    groups = {
        1: np.array([[0, 0, 1, 3, 0, 25], [1, 1, 1, 3, 0, 25]], float),
        2: np.array([[4, 1, 2, 3, 2, 25], [5, 2, 2, 3, 2, 25]], float),
    }
    m = module()
    assert m.charge_between(groups, 1, 2, "observed_only")[0] == pytest.approx(2 / 3600)
    assert m.charge_between(groups, 1, 2, "linear_bridge")[0] == pytest.approx(5 / 3600)
    assert m.charge_between(groups, 1, 2, "command_hold")[0] == pytest.approx(4 / 3600)


def test_unphysical_inventory_is_not_evaluated():
    with pytest.raises(ValueError, match="physical stoichiometry"):
        module().uniform_ocv(None, {"negative": -0.1, "positive": 0.5}, 298.15)


def test_initial_inventory_cannot_be_refitted_in_saved_metadata(monkeypatch):
    m = module()
    original = m.json.loads

    def changed(text, *args, **kwargs):
        value = original(text, *args, **kwargs)
        if isinstance(value, dict) and "records" in value:
            value["records"]["polarization.json"]["accounting"]["declared_initial_stoichiometry"][
                "negative"
            ] = 0.5
        return value

    monkeypatch.setattr(m.json, "loads", changed)
    with pytest.raises(ValueError, match="Initial mean was changed"):
        m.audit()


@pytest.mark.data
def test_archived_source_records_match_original_workbook():
    path = Path("data/stanford/raw/NMC_k2_1C_25degC.xlsx")
    if not path.exists():
        pytest.skip("Original k2 workbook not present; do not acquire it for this test")
    assert module().verify_original_workbook(path)
