from dataclasses import replace

import numpy as np
import pytest

from physical_fpv.core import ModelConfig, simulate
from physical_fpv.current_profile import CurrentProfile


@pytest.mark.integration
def test_constant_profile_reproduces_existing_constant_current_solver():
    config = ModelConfig(model="DFN", mesh_points=10)
    reference = simulate(config)
    profile = CurrentProfile([0, 6000], [5, 5])
    candidate = simulate(config, current_profile=profile)
    common = np.linspace(0, min(reference.time_s[-1], candidate.time_s[-1]), 101)
    np.testing.assert_allclose(
        np.interp(common, candidate.time_s, candidate.voltage_v),
        np.interp(common, reference.time_s, reference.voltage_v),
        atol=1e-6,
    )
    assert candidate.capacity_ah[-1] == pytest.approx(reference.capacity_ah[-1], abs=1e-6)
    assert candidate.physical_audit["passed"]
    assert candidate.current_protocol["fingerprint_sha256"] == profile.fingerprint_sha256
    assert not candidate.solver_cache_info["profile_template_reused"]


@pytest.mark.integration
def test_variable_current_integrates_charge_and_keeps_profiles_separate():
    config = ModelConfig(model="SPM", mesh_points=10, sample_period_s=5)
    first = CurrentProfile([0, 100, 200, 6000], [5, 3, 5, 5])
    other = CurrentProfile([0, 100, 200, 6000], [5, 7, 5, 5])
    low = simulate(config, current_profile=first)
    high = simulate(config, current_profile=other)
    assert low.physical_audit["charge_integral_error_ah"] < 1e-6
    assert high.physical_audit["charge_integral_error_ah"] < 1e-6
    assert low.time_s[-1] > high.time_s[-1]
    assert low.parameter_fingerprint != high.parameter_fingerprint
    assert low.current_protocol["fingerprint_sha256"] != high.current_protocol["fingerprint_sha256"]
    # A subsequent constant solve must still use its own constant input and initial state.
    constant = simulate(replace(config, current_a=2.5))
    assert constant.capacity_ah[0] == 0
    assert constant.physical_audit["charge_integral_error_ah"] < 1e-6


def test_profile_domain_and_research_current_limits_are_enforced_before_solve():
    with pytest.raises(ValueError, match="coverage"):
        simulate(ModelConfig(), current_profile=CurrentProfile([0, 100], [5, 5]))
    with pytest.raises(ValueError, match="research envelope"):
        simulate(ModelConfig(), current_profile=CurrentProfile([0, 6000], [5, 8]))
    with pytest.raises(ValueError, match="schedule"):
        simulate(ModelConfig(), profile_schedule="unknown")


@pytest.mark.integration
def test_adaptive_schedule_preserves_forcing_and_sampled_audit_grid():
    config = ModelConfig(model="SPM", mesh_points=10, sample_period_s=5)
    profile = CurrentProfile([0, 100.3, 200.7, 6000], [5, 3, 5, 5])
    reference = simulate(config, current_profile=profile)
    adaptive = simulate(config, current_profile=profile, profile_schedule="adaptive")
    assert reference.parameter_fingerprint == adaptive.parameter_fingerprint
    assert 100.3 in adaptive.time_s and 200.7 in adaptive.time_s
    stop = min(reference.time_s[-1], adaptive.time_s[-1])
    np.testing.assert_array_equal(
        reference.time_s[reference.time_s < stop], adaptive.time_s[adaptive.time_s < stop]
    )
    assert adaptive.physical_audit["charge_integral_error_ah"] <= 1e-6
    assert adaptive.physical_audit["passed"]
    assert not adaptive.current_protocol["solver_stops_at_profile_knots"]
