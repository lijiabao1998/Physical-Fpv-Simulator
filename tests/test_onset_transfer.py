"""Independent anchor, loaded-fall and saved-terminal contrasts."""

import numpy as np
import pytest

from physical_fpv.onset_transfer import cross_cell_comparison


def example():
    rest = np.column_stack((np.arange(61.0), np.full(61, 4.2), np.zeros(61), np.full(61, 298.15)))
    loaded = np.array(
        [
            [1.0, 4.0, -5.0, 298.15],
            [2.0, 3.9, -5.0, 298.15],
            [5.0, 3.8, -5.0, 298.15],
            [10.0, 3.7, -5.0, 298.15],
        ]
    )
    model = np.column_stack((loaded[:, 0], loaded[:, 1] + 0.05, np.full(4, 298.16)))
    return rest, loaded, model


@pytest.mark.parametrize("contrast", ["anchor", "fall", "model"])
def test_delta_identity_distinguishes_observable_contrasts(contrast):
    r1, h1, m1 = example()
    r2, h2, m2 = example()
    if contrast == "anchor":
        r1[:, 1] += 0.1
        h1[:, 1] += 0.1
    if contrast == "fall":
        h1[:, 1] -= 0.05
    if contrast == "model":
        m1[:, 1] += 0.02
    result = cross_cell_comparison(r1, h1, m1, r2, h2, m2)
    expected = {"anchor": -0.1, "fall": 0.05, "model": 0.02}[contrast]
    np.testing.assert_allclose(result["delta_terminal_residual_v"], expected, atol=1e-15)
    assert result["arithmetic_closure_max_v"] < 1e-12
    assert not result["same_absolute_soc_established"]
    assert not result["unsaved_internal_states_inferred"]
    if contrast == "anchor":
        np.testing.assert_allclose(result["delta_observed_voltage_fall_v"], 0, atol=1e-15)


def test_common_first_time_requires_supported_observations():
    r1, h1, m1 = example()
    r2, h2, m2 = example()
    h1[0, 0] = 1.1
    m1[0, 0] = 1.05
    result = cross_cell_comparison(r1, h1, m1, r2, h2, m2)
    assert result["query_times_s"] == [1.1, 2.0, 5.0, 10.0]
    h1[0, 0] = 2.0
    h1[1, 0] = 2.1
    with pytest.raises(ValueError, match="precede"):
        cross_cell_comparison(r1, h1, m1, r2, h2, m2)


def test_missing_late_support_is_not_extrapolated():
    r1, h1, m1 = example()
    r2, h2, m2 = example()
    m1[-1, 0] = 9.9
    with pytest.raises(ValueError, match="outside"):
        cross_cell_comparison(r1, h1, m1, r2, h2, m2)


def test_saved_cross_cell_result_reproduces_without_download_or_solve(tmp_path, monkeypatch):
    import importlib.util
    import json
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("No solve/download in frozen transfer")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "onset_transfer_check", "scripts/check_stanford_onset_transfer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.ROOT / "docs/benchmarks"
    expected = json.loads((source / "stanford-onset-transfer.json").read_text())
    actual = module.run(source, tmp_path)
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["saved_model_context"] == expected["saved_model_context"]
    assert actual["historical_passed"] == {"k1": False, "k2": False}
    one, two = actual["comparison"], expected["comparison"]
    assert one["query_times_s"] == two["query_times_s"]
    assert not one["unsaved_internal_states_inferred"]
    assert one["arithmetic_closure_max_v"] < 1e-12
    for key in (
        "delta_model_terminal_v",
        "delta_observed_voltage_fall_v",
        "delta_terminal_residual_v",
    ):
        np.testing.assert_allclose(one[key], two[key], rtol=1e-13, atol=1e-14)
    for name in ("k1", "k2"):
        assert one["cases"][name]["timing"] == two["cases"][name]["timing"]
        np.testing.assert_allclose(
            one["cases"][name]["terminal_residual_v"],
            two["cases"][name]["terminal_residual_v"],
            rtol=1e-13,
            atol=1e-14,
        )
    (tmp_path / "stanford-k1-onset-records.csv.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        module.verified(tmp_path, "stanford-k1-onset-records.csv.gz")
