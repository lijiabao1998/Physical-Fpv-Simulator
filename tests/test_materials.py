from dataclasses import replace

import numpy as np
import pytest

from physical_fpv.materials import (
    BOLTZMANN_EV_K,
    PropertyEstimate,
    analytic_material_example,
    uncorrelated_jump_diffusivity,
)


def test_cubic_random_walk_matches_analytic_solution():
    jumps = np.vstack([np.eye(3), -np.eye(3)]) * 3e-10
    value = uncorrelated_jump_diffusivity(jumps, np.full(6, 0.5), np.full(6, 1e13), 298.15)
    expected = 1e13 * np.exp(-0.5 / (BOLTZMANN_EV_K * 298.15)) * (3e-10) ** 2
    np.testing.assert_allclose(value, expected * np.eye(3), rtol=1e-14)


def test_migration_barrier_reduces_diffusion_without_arbitrary_bonus():
    jumps = np.vstack([np.eye(3), -np.eye(3)]) * 3e-10
    low = uncorrelated_jump_diffusivity(jumps, np.full(6, 0.3), np.full(6, 1e13), 298.15)
    high = uncorrelated_jump_diffusivity(jumps, np.full(6, 0.5), np.full(6, 1e13), 298.15)
    assert np.trace(high) < np.trace(low)


def test_reject_drifting_or_wrong_unit_jump_network():
    with pytest.raises(ValueError, match="drift"):
        uncorrelated_jump_diffusivity([[3e-10, 0, 0]], [0.5], [1e13], 298.15)
    with pytest.raises(ValueError, match="metres"):
        uncorrelated_jump_diffusivity([[3, 0, 0]], [0.5], [1e13], 298.15)


def estimate():
    return PropertyEstimate(
        "chemical_diffusivity",
        1e-14,
        "m2/s",
        298.15,
        (298.15, 298.15),
        0.2,
        "measured",
        "GITT with stated model assumptions",
        "test fixture, not experimental evidence",
        "a" * 64,
        "test-phase",
        (0.1, 0.9),
        "intrinsic_particle",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"unit": "cm2/s"},
        {"value": -1},
        {"value": float("inf")},
        {"source": ""},
        {"structure_sha256": "bad"},
        {"uncertainty_fraction": -1},
        {"temperature_k": 250},
    ],
)
def test_reject_unqualified_property(change):
    with pytest.raises(ValueError):
        replace(estimate(), **change).validate()


def test_never_map_tracer_diffusion_directly_to_chemical_diffusion():
    with pytest.raises(ValueError, match="tracer"):
        replace(estimate(), name="tracer_diffusivity").electrode_mapping(
            "negative", 298.15, phase="test-phase", stoichiometry_range=(0.2, 0.8)
        )


def test_never_extrapolate_scalar_property_or_use_analytic_benchmark():
    with pytest.raises(ValueError, match="extrapolated"):
        estimate().electrode_mapping(
            "positive", 310, phase="test-phase", stoichiometry_range=(0.2, 0.8)
        )
    with pytest.raises(ValueError, match="benchmarks"):
        replace(estimate(), evidence_kind="analytic_benchmark").electrode_mapping(
            "negative", 298.15, phase="test-phase", stoichiometry_range=(0.2, 0.8)
        )
    assert not analytic_material_example()["battery_parameter_mapping_allowed"]


def test_qualified_mapping_retains_physical_parameter_units():
    assert estimate().electrode_mapping(
        "negative", 298.15, phase="test-phase", stoichiometry_range=(0.2, 0.8)
    ) == {"Negative particle diffusivity [m2.s-1]": 1e-14}


def test_reject_stoichiometry_extrapolation_and_wrong_phase_or_scope():
    with pytest.raises(ValueError, match="stoichiometry"):
        estimate().electrode_mapping(
            "negative", 298.15, phase="test-phase", stoichiometry_range=(0.0, 1.0)
        )
    with pytest.raises(ValueError, match="phase"):
        estimate().electrode_mapping(
            "negative", 298.15, phase="different-phase", stoichiometry_range=(0.2, 0.8)
        )
    with pytest.raises(ValueError, match="scope"):
        replace(estimate(), spatial_scope="effective_electrode").electrode_mapping(
            "negative", 298.15, phase="test-phase", stoichiometry_range=(0.2, 0.8)
        )
