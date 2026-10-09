"""Independent synthetic checks for a retrospective thermal diagnostic."""

import numpy as np
import pytest

from physical_fpv.cooling_characterization import fit_decay, metrics, prediction, window


def test_recovers_synthetic_time_constant():
    t = np.linspace(0, 3601, 3602)
    y = 24 + 8 * np.exp(-(t - 60) / 320)
    result = fit_decay(t, y, 24)
    assert result["tau_s"] == pytest.approx(320, abs=0.001)
    assert result["calibration"]["rmse_k"] < 1e-5
    assert not result["boundary_optimum"]
    assert result["identified_heat_transfer_coefficient"] is None


def test_late_data_do_not_change_fit():
    t = np.arange(3602.0)
    y = 24 + 8 * np.exp(-(t - 60) / 320)
    original = fit_decay(t, y, 24)
    changed = y.copy()
    changed[t > 600] += 20 * np.sin(t[t > 600])
    assert fit_decay(t, changed, 24) == original


def test_constant_error_integral_and_maximum():
    m = metrics([60, 100, 300], [20, 20, 20], 60, 300, 20, 22, 0)
    assert m["rmse_k"] == pytest.approx(2)
    assert m["mean_signed_error_k"] == pytest.approx(2)
    assert m["maximum_absolute_error_k"] == pytest.approx(2)
    assert not m["independent_thermal_validation"]


def test_stationary_residual_inside_segment():
    # exp(-u) versus straight line joining its endpoints: interior minimum.
    m = metrics([60, 61], [1, np.exp(-1)], 60, 61, 0, 1, 1)
    u = -np.log(1 - np.exp(-1))
    expected = abs(np.exp(-u) - (1 + (np.exp(-1) - 1) * u))
    assert m["maximum_absolute_error_k"] == pytest.approx(expected)
    assert m["maximum_absolute_error_k"] > 0.07


def test_nominal_asymptote_cannot_cross():
    assert np.all(prediction([60, 600, 3600], 25, 31, 1 / 300) >= 25)


def test_interpolated_window_boundaries():
    t, y = window([0, 10, 20], [20, 30, 20], 5, 15)
    np.testing.assert_array_equal(t, [5, 10, 15])
    np.testing.assert_array_equal(y, [25, 30, 25])


@pytest.mark.parametrize(
    "t,y", [([0, 0], [1, 2]), ([1, 0], [1, 2]), ([0, 1], [1, np.nan]), ([0, 1], [1])]
)
def test_invalid_traces_rejected(t, y):
    with pytest.raises(ValueError):
        window(t, y, 0, 1)


def test_no_extrapolation_or_backward_prediction():
    with pytest.raises(ValueError):
        window([60, 600], [30, 25], 60, 601)
    with pytest.raises(ValueError):
        prediction([59], 25, 30, 0.001)
    with pytest.raises(ValueError):
        prediction([60], 25, 30, -1)


def test_boundary_fit_and_unexcited_case():
    t = np.arange(60.0, 601)
    result = fit_decay(t, np.ones_like(t) * 30, 25)
    assert result["boundary_optimum"]
    assert result["tau_s"] == pytest.approx(10000)
    with pytest.raises(ValueError):
        fit_decay(t, np.ones_like(t) * 25, 25)


def test_irregular_split_does_not_interpolate_a_check_sample_into_calibration():
    t = np.arange(0.0002, 3602)
    y = 24 + 8 * np.exp(-(t - 60) / 320)
    original = fit_decay(t, y, 24)
    changed = y.copy()
    changed[t > 600] += 100
    assert fit_decay(t, changed, 24) == original
    assert original["calibration"]["interval_s"][1] < 600
