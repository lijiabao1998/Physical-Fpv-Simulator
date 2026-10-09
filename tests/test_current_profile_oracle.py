"""Independent exact-rational arithmetic checks, not electrochemical validation."""

import random
from fractions import Fraction

import numpy as np
import pytest

from physical_fpv.current_profile import CurrentProfile


def exact_current_and_charge(times, currents, query):
    """Integrate the affine polynomial with rational arithmetic, segment by segment.

    Fractions represent the actual binary64 inputs exactly. This intentionally
    does not call interpolation, searchsorted, trapezoid, or production helpers.
    """
    t = [Fraction(float(x)) for x in times]
    current = [Fraction(float(x)) for x in currents]
    q = Fraction(float(query))
    if not t[0] <= q <= t[-1]:
        raise ValueError("Oracle query outside supplied interval")
    charge = Fraction(0)
    for left, right, start, end in zip(t[:-1], t[1:], current[:-1], current[1:], strict=True):
        width = right - left
        elapsed = min(q, right) - left
        if elapsed < 0:
            break
        slope = (end - start) / width
        charge += start * elapsed + slope * elapsed * elapsed / 2
        if q <= right:
            return float(start + slope * elapsed), float(charge / 3600)
    raise AssertionError("Covered query must have an oracle segment")


def deterministic_profile(seed):
    rng = random.Random(seed)
    # Dyadic, irregular times avoid decimal parsing ambiguity; currents span
    # many scales but remain positive and safely inside normal float64 range.
    times = [0.0]
    for _ in range(rng.randint(2, 31)):
        times.append(times[-1] + rng.randint(1, 1024) / 128)
    currents = [rng.randint(1, 128) * 2.0 ** rng.randint(-20, 20) for _ in times]
    return np.array(times), np.array(currents)


@pytest.mark.parametrize("seed", range(16))
def test_nonuniform_profiles_against_exact_polynomial_oracle(seed):
    times, currents = deterministic_profile(seed)
    profile = CurrentProfile(times, currents)
    queries = set(times)
    queries.update((times[:-1] + times[1:]) / 2)
    for knot in times[1:-1]:
        queries.update([np.nextafter(knot, -np.inf), np.nextafter(knot, np.inf)])
    queries.update(np.linspace(0, times[-1], 37))
    for query in sorted(queries):
        current, charge = exact_current_and_charge(times, currents, query)
        # At most 31 positive segment areas: 256 eps allows conservative
        # accumulation/rounding error, not a physical acceptance tolerance.
        tolerance = 256 * np.finfo(float).eps
        assert profile.value_at(query) == pytest.approx(current, rel=tolerance, abs=0)
        assert profile.charge_integral_ah(query) == pytest.approx(charge, rel=tolerance, abs=0)
    assert profile.charge_integral_ah(0) == 0
    for outside in [np.nextafter(0.0, -np.inf), np.nextafter(times[-1], np.inf)]:
        for operation in [profile.value_at, profile.charge_integral_ah, profile.require_coverage]:
            with pytest.raises(ValueError, match="coverage"):
                operation(outside)


@pytest.mark.parametrize(
    "time_scale,current_scale", [(2.0**-100, 2.0**100), (2.0**100, 2.0**-100), (8, 32)]
)
def test_dimensionally_consistent_time_current_scaling(time_scale, current_scale):
    times, currents = deterministic_profile(20261009)
    original = CurrentProfile(times, currents)
    scaled = CurrentProfile(times * time_scale, currents * current_scale)
    for query in np.linspace(0, times[-1], 79):
        exact_current, exact_charge = exact_current_and_charge(
            times * time_scale, currents * current_scale, query * time_scale
        )
        tolerance = 256 * np.finfo(float).eps
        assert scaled.value_at(query * time_scale) == pytest.approx(
            exact_current, rel=tolerance, abs=0
        )
        assert scaled.charge_integral_ah(query * time_scale) == pytest.approx(
            exact_charge, rel=tolerance, abs=0
        )
        assert scaled.value_at(query * time_scale) == pytest.approx(
            original.value_at(query) * current_scale, rel=tolerance, abs=0
        )
        assert scaled.charge_integral_ah(query * time_scale) == pytest.approx(
            original.charge_integral_ah(query) * time_scale * current_scale, rel=tolerance, abs=0
        )
    assert original.fingerprint_sha256 != scaled.fingerprint_sha256


def test_oracle_has_independent_closed_form_ramp_sanity_check():
    # I(t)=2+4t/3600 A, Q(900s)=0.625 Ah.
    assert exact_current_and_charge([0, 3600], [2, 6], 900) == (3, 0.625)


def test_steep_fall_just_before_knot_keeps_small_endpoint_weight():
    times, currents = [0, 3], [2**50, 1]
    query = np.nextafter(3.0, 0.0)
    profile = CurrentProfile(times, currents)
    expected, _ = exact_current_and_charge(times, currents, query)
    assert expected == 1.1666666666666665
    assert profile.value_at(query) == expected


def test_near_max_finite_constant_current_does_not_overflow_in_interpolation():
    times = [0, 0.03286517098350328, 1.2866201085102371]
    current = np.finfo(float).max
    profile = CurrentProfile(times, [current] * 3)
    query = 0.09456806934239166
    with np.errstate(over="raise", invalid="raise"):
        assert profile.value_at(query) == current
    assert np.isfinite(profile.charge_integral_ah(query))


def test_saved_k2_query_audit_is_reproducible_without_solver_or_download(monkeypatch):
    import importlib.util
    import json
    import urllib.request
    from pathlib import Path

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("Arithmetic audit must not solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "profile_audit", "scripts/audit_current_profile_arithmetic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.audit()
    assert result == json.loads(Path("docs/benchmarks/current-profile-arithmetic.json").read_text())
    assert not result["new_implementation_voltage_validation_established"]
    for check in result["comparisons"].values():
        assert check["max_absolute_difference_a"] <= 2e-15
