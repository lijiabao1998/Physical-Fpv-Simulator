"""Synthetic finite-time response identities, not empirical physics validation."""

import numpy as np
import pytest

from physical_fpv.onset_response import model_comparison, observed_response, rest_summary


def rest():
    return np.column_stack(
        (np.arange(0.0, 101.0), np.full(101, 4.2), np.zeros(101), np.full(101, 298.15))
    )


def load():
    return np.array(
        [
            [1.0, 4.0, -5.0, 298.15],
            [2.0, 3.9, -5.0, 298.16],
            [5.0, 3.8, -5.0, 298.17],
            [10.0, 3.7, -5.0, 298.18],
        ]
    )


def test_rest_tail_constant_and_linear_drift():
    values = rest()
    summary = rest_summary(values)
    assert summary["tails_s"]["60"]["mean_v"] == pytest.approx(4.2)
    assert summary["tails_s"]["10"]["endpoint_change_v"] == 0
    values[:, 1] = 4.2 - values[:, 0] * 1e-4
    summary = rest_summary(values)
    assert summary["tails_s"]["60"]["mean_v"] == pytest.approx(4.193)
    assert summary["tails_s"]["10"]["endpoint_change_per_second_v"] == pytest.approx(-1e-4)
    assert not summary["equilibrium_certified"]


def test_observed_response_units_and_interpolation():
    response = observed_response(rest(), load(), np.array([1.0, 1.5, 5.0, 10.0]))
    np.testing.assert_allclose(response["voltage_fall_v"], [0.2, 0.25, 0.4, 0.5], atol=1e-15)
    np.testing.assert_allclose(
        response["finite_time_apparent_response_ohm"], [0.04, 0.05, 0.08, 0.1], atol=1e-15
    )
    assert response["sampling_brackets"][0]["interval_width_s"] == 0
    assert response["sampling_brackets"][1]["interval_width_s"] == 1
    assert not response["pure_ohmic_identification"]


@pytest.mark.parametrize("delta", [0.0, 0.01])
def test_constant_offset_algebraic_compatibility_and_incompatibility(delta):
    response = observed_response(rest(), load(), np.array([1.0, 2.0, 5.0, 10.0]))
    model = np.array(
        [
            [0.0, 4.1, 4.1, 298.15],
            [1.0, 3.9 + delta, 4.09, 298.15],
            [2.0, 3.8 + delta, 4.08, 298.15],
            [5.0, 3.7 + delta, 4.07, 298.15],
            [10.0, 3.6 + delta, 4.06, 298.15],
        ]
    )
    result = model_comparison(response, model, np.array([[0.0, 5.0], [10.0, 5.0]]))
    assert result["initial_reference_offset_v"] == pytest.approx(-0.1)
    np.testing.assert_allclose(result["residual_minus_constant_offset_v"], delta, atol=1e-15)
    assert result["offset_only_arithmetic_compatible"] == [delta == 0] * 4
    assert result["arithmetic_closure_max_v"] < 1e-12
    assert not result["physical_initial_state_falsified"]


@pytest.mark.parametrize(
    "kind", ["current", "duplicate", "nan", "short_rest", "query_before", "query_after"]
)
def test_invalid_sources_and_unsupported_queries_rejected(kind):
    r, loaded, t = rest(), load(), np.array([1.0, 2.0, 5.0, 10.0])
    if kind == "current":
        loaded[1, 2] = 0
    if kind == "duplicate":
        loaded[1, 0] = loaded[0, 0]
    if kind == "nan":
        loaded[1, 1] = np.nan
    if kind == "short_rest":
        r = r[-20:]
    if kind == "query_before":
        t[0] = 0
    if kind == "query_after":
        t[-1] = 11
    with pytest.raises(ValueError):
        observed_response(r, loaded, t)


@pytest.mark.parametrize(
    "kind", ["duplicate_test", "duplicate_date", "origin", "rest_current", "sign"]
)
def test_original_phase_qualification_rejects_clock_or_current_defects(kind):
    from datetime import datetime, timedelta

    from physical_fpv.onset_response import qualify_phase

    base = datetime(2020, 1, 1)
    phase = 4 if kind == "rest_current" else 5
    rows = [
        (
            i + 2,
            (
                base + timedelta(seconds=i),
                100.0 + i,
                float(i),
                phase,
                4.0,
                0.0 if phase == 4 else -5.0,
                25.0,
            ),
        )
        for i in range(3)
    ]
    qualify_phase(rows, phase)
    index, value = rows[1]
    value = list(value)
    if kind == "duplicate_test":
        value[1] = 100.0
    if kind == "duplicate_date":
        value[0] = base
    if kind == "origin":
        value[2] = 1.1
    if kind == "rest_current":
        value[5] = 0.1
    if kind == "sign":
        value[5] = 1.0
    rows[1] = (index, tuple(value))
    with pytest.raises(ValueError):
        qualify_phase(rows, phase)


def test_saved_onset_reproduces_without_download_or_solve(tmp_path, monkeypatch):
    import importlib.util
    import json
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("No solve/download in cached onset analysis")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "onset_check", "scripts/check_stanford_k2_onset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = json.loads(
        (module.ROOT / "docs/benchmarks/stanford-k2-onset-comparison.json").read_text()
    )
    actual = module.run(module.ROOT / "docs/benchmarks", tmp_path)
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["timing"] == expected["timing"]
    assert actual["model"]["offset_only_arithmetic_compatible"] == [False] * 4
    assert not actual["model"]["physical_initial_state_falsified"]
    assert not actual["historical_1c_passed"]
    for key in (
        "terminal_residual_v",
        "residual_minus_constant_offset_v",
        "model_initial_reference_voltage_fall_v",
    ):
        np.testing.assert_allclose(
            actual["model"][key], expected["model"][key], rtol=1e-13, atol=1e-14
        )
    for label in ("low_rate", "high_rate"):
        assert actual[label]["sampling_brackets"] == expected[label]["sampling_brackets"]
        np.testing.assert_allclose(
            actual[label]["voltage_fall_v"],
            expected[label]["voltage_fall_v"],
            rtol=1e-13,
            atol=1e-14,
        )
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "stanford-k2-low-rate-onset-records.csv.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        module.read_source(bad, "stanford-k2-low-rate-onset-records.csv.gz")
