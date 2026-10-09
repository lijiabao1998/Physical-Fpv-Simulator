"""Descriptive residual diagnostics cannot download, solve or change acceptance."""

import importlib.util
import json
import urllib.request
from pathlib import Path

import numpy as np
import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "k2_audit", "scripts/audit_stanford_k2_residuals.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_exact_linear_squared_integral_and_sign_crossing():
    m = module()
    t, e = np.array([0.0, 2.0]), np.array([1.0, -1.0])
    result = m.stats(t, e, 0, 2)
    assert result["integrated_squared_error_v2_s"] == pytest.approx(2 / 3)
    assert result["signed_mean_v"] == 0
    assert m.crossings(t, e) == [1.0]
    assert m.stats(t, e, 0, 1)["integrated_squared_error_v2_s"] == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "time,error,start,stop",
    [
        ([0, 0], [1, 1], 0, 1),
        ([0, 1], [1, float("nan")], 0, 1),
        ([0, 1], [1, 1], -1, 1),
        ([0, 1], [1, 1], 0, 2),
    ],
)
def test_invalid_samples_or_extrapolation_rejected(time, error, start, stop):
    with pytest.raises(ValueError):
        module().stats(time, error, start, stop)


def test_full_audit_is_reproducible_without_download_or_solve(monkeypatch):
    import physical_fpv.core

    def forbidden(*args, **kwargs):
        raise AssertionError("Residual audit must not download or simulate")

    monkeypatch.setattr(physical_fpv.core, "simulate", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result, _ = module().audit()
    saved = json.loads(Path("docs/benchmarks/stanford-k2-residual-audit.json").read_text())
    assert result == saved
    assert result["new_model_solves"] == result["new_source_downloads"] == 0
    assert result["scientific_empirical_pass"] is False
    fine = result["cases"]["120"]
    assert fine["full"]["rmse_v"] == pytest.approx(0.05500305419157363)
    assert sum(q["squared_error_fraction"] for q in fine["equal_observed_duration_quarters"]) == (
        pytest.approx(1)
    )
    assert fine["sign_regions"][0]["squared_error_fraction"] == pytest.approx(0.8610230278270689)
    assert result["saved_state_extrema"]["negative"]["support_crossing_time_s"] is None
    assert result["k1_comparison"]["max_absolute_prediction_difference_v"] == pytest.approx(
        0.002815200508976101
    )
