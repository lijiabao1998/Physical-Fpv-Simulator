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


def test_recorded_order_is_not_continuous_state_history():
    m = module()
    history = json.loads(Path("docs/benchmarks/stanford-k2-k6-history-partial.json").read_text())
    k2 = history["saved_report_analysis"]["histories"]["k2"]
    assert k2["complete"] and k2["history_qualified"]
    previous, following = k2["ordered_intervals"][:2]
    boundary = m.history_boundary(previous, following)
    assert boundary["previous_end_naive_local"] == "2019-08-31T21:41:12.806000"
    assert boundary["following_start_naive_local"] == "2019-09-02T19:11:01.133000"
    assert boundary["unobserved_gap_s"] == pytest.approx(163788.327, rel=0, abs=1e-6)
    assert boundary["continuous_state_replay_allowed"] is False
    assert boundary["following_workbook_sha256"] == m.SOURCE_SHA256
    with pytest.raises(ValueError, match="continuous state replay is not supported"):
        m.require_continuous_state_replay(previous, following)


@pytest.mark.parametrize("date", ["2019-08-31T21:41:12.806000", "2019-08-30T00:00:00"])
def test_nonpositive_file_gap_does_not_establish_continuity(date):
    with pytest.raises(ValueError, match="does not establish continuous"):
        module().history_boundary(
            {"end_naive_local": "2019-08-31T21:41:12.806000"},
            {"start_naive_local": date},
        )


def test_utc_conversion_cannot_silently_replace_source_naive_dates():
    with pytest.raises(ValueError, match="original naive-local timestamps"):
        module().history_boundary(
            {"end_naive_local": "2019-08-31T21:41:12.806000+00:00"},
            {"start_naive_local": "2019-09-02T19:11:01.133000+00:00"},
        )
