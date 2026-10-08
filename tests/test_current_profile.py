import warnings
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from physical_fpv.current_profile import CurrentProfile


def test_constant_current_keeps_the_supplied_clock_and_units():
    profile = CurrentProfile([0, 1.0006, 1800, 3600], [5.000325] * 4)
    query = np.array([0, 1.0006, 900, 1800, 3600])
    np.testing.assert_allclose(profile.value_at(query), 5.000325)
    np.testing.assert_allclose(profile.charge_integral_ah(query), 5.000325 * query / 3600)
    assert profile.end_time_s == 3600
    assert profile.min_current_a == profile.max_current_a == 5.000325
    assert profile.value_at(0) == 5.000325
    assert profile.charge_integral_ah(0) == 0
    assert isinstance(profile.value_at(12), float)
    assert isinstance(profile.charge_integral_ah(12), float)


def test_ramp_charge_is_quadratic_inside_a_segment():
    profile = CurrentProfile([0, 3600], [2, 6])
    query = [0, 900, 1800, 2700, 3600]
    np.testing.assert_allclose(profile.value_at(query), [2, 3, 4, 5, 6])
    np.testing.assert_allclose(profile.charge_integral_ah(query), [0, 0.625, 1.5, 2.625, 4])
    assert profile.min_current_a == 2
    assert profile.max_current_a == 6


def test_nonuniform_rising_and_falling_segments_include_partial_charge():
    profile = CurrentProfile([0, 2, 5, 9], [1, 5, 2, 6])
    query = np.array([[9, 1, 3.5], [0, 5, 7]])
    np.testing.assert_allclose(profile.value_at(query), [[6, 3, 3.5], [1, 2, 4]])
    np.testing.assert_allclose(
        profile.charge_integral_ah(query),
        np.array([[32.5, 2, 12.375], [0, 16.5, 22.5]]) / 3600,
    )
    assert profile.min_current_a == 1
    assert profile.max_current_a == 6


def test_extra_knots_on_the_same_line_preserve_the_function_and_integral():
    sparse = CurrentProfile([0, 3600], [2, 6])
    refined = CurrentProfile([0, 450, 1800, 2700, 3600], [2, 2.5, 4, 5, 6])
    query = np.linspace(0, 3600, 101)
    np.testing.assert_allclose(sparse.value_at(query), refined.value_at(query))
    np.testing.assert_allclose(sparse.charge_integral_ah(query), refined.charge_integral_ah(query))
    # The function matches, but the exact supplied content/provenance differs.
    assert sparse.fingerprint_sha256 != refined.fingerprint_sha256


@pytest.mark.parametrize(
    ("times", "currents"),
    [
        ([], []),
        ([0], [1]),
        ([0, 1], [1]),
        ([[0, 1]], [[1, 2]]),
        ([0, 1], [[1, 2]]),
        ([1.0006, 2], [5, 5]),
        ([-1, 0, 1], [1, 1, 1]),
        ([0, 1, 1], [1, 1, 1]),
        ([0, 2, 1], [1, 1, 1]),
        ([0, -1], [1, 1]),
        ([0, np.nan], [1, 1]),
        ([0, np.inf], [1, 1]),
        ([0, 1], [0, 1]),
        ([0, 1], [1, -1]),
        ([0, 1], [1, np.nan]),
        ([0, 1], [1, np.inf]),
        ([0, 1 + 1j], [1, 1]),
        ([0, 1], [1, 1 + 1j]),
        ([False, True], [1, 1]),
        ([0, 1], [False, True]),
        (["0", "1"], [1, 1]),
    ],
)
def test_invalid_knots_are_rejected_without_repair(times, currents):
    with pytest.raises(ValueError):
        CurrentProfile(times, currents)


@pytest.mark.parametrize("query", [-1e-12, 2.00000000001, np.nan, np.inf, -np.inf, [0, 3]])
@pytest.mark.parametrize("operation", ["value_at", "charge_integral_ah", "require_coverage"])
def test_queries_cannot_extrapolate_or_use_nonfinite_times(operation, query):
    profile = CurrentProfile([0, 2], [1, 3])
    with pytest.raises(ValueError):
        getattr(profile, operation)(query)


def test_coverage_is_explicit_and_closed_at_both_ends():
    profile = CurrentProfile([0, 2], [1, 3])
    for end in (0, 1, 2):
        profile.require_coverage(end)
    with pytest.raises(ValueError, match="scalar"):
        profile.require_coverage([1, 2])
    with pytest.raises(ValueError, match="coverage"):
        profile.require_coverage(np.nextafter(2.0, np.inf))
    assert profile.value_at(2) == 3
    assert profile.charge_integral_ah(2) == pytest.approx(4 / 3600)


def test_inputs_and_exposed_arrays_cannot_mutate_profile_or_fingerprint():
    times = np.array([0.0, 1.0, 2.0])
    currents = np.array([1.0, 2.0, 3.0])
    profile = CurrentProfile(times, currents)
    fingerprint = profile.fingerprint_sha256
    times[:] = 42
    currents[:] = 42
    for exposed in (profile.time_s, profile.current_a):
        with pytest.raises(ValueError):
            exposed[0] = 42
        with pytest.raises(ValueError):
            exposed.setflags(write=True)
        with pytest.raises(TypeError):
            memoryview(exposed)[0] = 42
        with warnings.catch_warnings(action="ignore", category=DeprecationWarning):
            exposed.shape = (1, 3)
    with pytest.raises(FrozenInstanceError):
        profile.end_time_s = 42
    with pytest.raises(FrozenInstanceError):
        profile.fingerprint_sha256 = "changed"
    np.testing.assert_array_equal(profile.time_s, [0, 1, 2])
    np.testing.assert_array_equal(profile.current_a, [1, 2, 3])
    assert profile.value_at(1.5) == 2.5
    assert profile.charge_integral_ah(2) == pytest.approx(4 / 3600)
    assert profile.fingerprint_sha256 == fingerprint


def test_fingerprint_is_independent_of_input_endianness_and_numeric_container():
    ordinary = CurrentProfile([0, 1, 2], [1, 2, 3])
    big_endian = CurrentProfile(
        np.array([-0.0, 1, 2], dtype=">f8"), np.array([1, 2, 3], dtype=">f8")
    )
    assert ordinary.fingerprint_sha256 == big_endian.fingerprint_sha256
    assert len(ordinary.fingerprint_sha256) == 64
    int(ordinary.fingerprint_sha256, 16)
    assert ordinary.fingerprint_sha256 != CurrentProfile([0, 1, 3], [1, 2, 3]).fingerprint_sha256
    assert ordinary.fingerprint_sha256 != CurrentProfile([0, 1, 2], [1, 2, 4]).fingerprint_sha256


def test_tiny_segments_do_not_require_an_overflowing_current_slope():
    profile = CurrentProfile([0, 1e-300], [1, 1e100])
    assert profile.value_at(0.5e-300) == pytest.approx(0.5e100)
    assert profile.charge_integral_ah(1e-300) == pytest.approx(0.5e-200 / 3600, rel=1e-12, abs=0)


def test_unrepresentable_total_charge_is_rejected():
    with pytest.raises(ValueError, match="finite float64"):
        CurrentProfile([0, 1e300], [1e300, 1e300])
