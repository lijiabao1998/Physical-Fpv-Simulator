"""Frozen response scaling with independent currents and conditional interpretation."""

import numpy as np
import pytest

from physical_fpv.cross_rate_response import compare_rates


def record(current, response):
    rest = np.column_stack((np.arange(61.0), np.full(61, 4.2), np.zeros(61), np.full(61, 298.15)))
    loaded = np.column_stack(
        (
            [1.0, 2.0, 5.0, 10.0],
            np.full(4, 4.2 - current * response),
            np.full(4, -current),
            np.full(4, 298.15),
        )
    )
    return rest, loaded


def records():
    return {
        "k1_1c": record(5.0, 0.06),
        "k2_1c": record(5.0, 0.03),
        "k1_005c": record(0.25, 0.06),
        "k2_005c": record(0.3, 0.03),
    }


def test_proportional_transfer_uses_both_actual_currents():
    result = compare_rates(records())
    for cell in ("k1", "k2"):
        np.testing.assert_allclose(
            result["transfer"][cell]["observed_minus_predicted_low_rate_fall_v"], 0, atol=1e-15
        )
    np.testing.assert_allclose(
        result["predicted_low_rate_cell_fall_difference_v"], 0.006, atol=1e-15
    )
    np.testing.assert_allclose(
        result["interaction_low_minus_high_response_contrast_ohm"], 0, atol=1e-14
    )
    assert not result["contact_resistance_identified"]
    assert not result["statistical_acceptance_established"]


def test_nontransferring_low_rate_response_is_reported_without_refitting():
    data = records()
    data["k1_005c"] = record(0.25, 0.04)
    result = compare_rates(data)
    np.testing.assert_allclose(
        result["transfer"]["k1"]["observed_minus_predicted_low_rate_fall_v"], -0.005, atol=1e-15
    )
    np.testing.assert_allclose(
        result["interaction_low_minus_high_response_contrast_ohm"], -0.02, atol=1e-14
    )
    np.testing.assert_allclose(
        result["observed_minus_predicted_low_rate_cell_fall_difference_v"], -0.005, atol=1e-15
    )
    assert not result["parameters_fitted"]


def test_zero_predicted_fall_has_no_undefined_relative_metric():
    data = records()
    data["k1_1c"] = record(5.0, 0.0)
    result = compare_rates(data)
    assert result["transfer"]["k1"]["relative_difference"] == [None] * 4


@pytest.mark.parametrize("kind", ["missing", "sign", "support", "first"])
def test_invalid_frozen_comparison_rejected(kind):
    data = records()
    if kind == "missing":
        del data["k1_005c"]
    if kind == "sign":
        data["k1_005c"][1][0, 2] = 0
    if kind == "support":
        data["k1_005c"][1][-1, 0] = 9.9
    if kind == "first":
        data["k1_005c"][1][:2, 0] = [2.0, 2.1]
    with pytest.raises(ValueError):
        compare_rates(data)


def test_saved_four_record_screen_reproduces_without_acquisition_or_solve(tmp_path, monkeypatch):
    import importlib.util
    import json
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("Frozen screen cannot download or solve")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "cross_rate_check", "scripts/check_stanford_cross_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.ROOT / "docs/benchmarks"
    expected = json.loads((source / "stanford-cross-rate-onset.json").read_text())
    actual = module.run(source, tmp_path)
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["same_cell_record_history"] == expected["same_cell_record_history"]
    assert actual["historical_passed"] == {"k1": False, "k2": False}
    result, target = actual["comparison"], expected["comparison"]
    assert result["query_times_s"] == target["query_times_s"]
    assert not result["contact_resistance_identified"]
    for cell in ("k1", "k2"):
        for key in (
            "predicted_low_rate_fall_v",
            "observed_minus_predicted_low_rate_fall_v",
            "low_minus_high_apparent_response_ohm",
        ):
            np.testing.assert_allclose(
                result["transfer"][cell][key], target["transfer"][cell][key], rtol=1e-13, atol=1e-14
            )
    np.testing.assert_allclose(
        result["observed_minus_predicted_low_rate_cell_fall_difference_v"],
        target["observed_minus_predicted_low_rate_cell_fall_difference_v"],
        rtol=1e-13,
        atol=1e-14,
    )
    for name in LABELS_FOR_TEST:
        assert result["cases"][name]["timing"] == target["cases"][name]["timing"]
        assert (
            result["cases"][name]["onset_current_support"]
            == target["cases"][name]["onset_current_support"]
        )
    (tmp_path / "stanford-k1-low-rate-onset-records.csv.gz").write_bytes(b"altered")
    with pytest.raises(ValueError, match="hash"):
        module.verified(tmp_path, "stanford-k1-low-rate-onset-records.csv.gz")


LABELS_FOR_TEST = ("k1_1c", "k1_005c", "k2_1c", "k2_005c")
