import numpy as np
import pytest

from physical_fpv.core import ModelConfig, simulate


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model": "fake"},
        {"thermal": "fake"},
        {"current_a": -5},
        {"current_a": 0},
        {"current_a": 10},
        {"current_a": float("nan")},
        {"current_a": float("inf")},
        {"ambient_temperature_k": 250},
        {"ambient_temperature_k": 500},
        {"mesh_points": 81},
        {"mesh_points": 20.5},
        {"tolerance": 1e-2},
        {"sample_period_s": 0.5},
        {"max_temperature_k": 400},
        {"max_temperature_k": 290},
    ],
)
def test_configuration_rejects_out_of_scope(kwargs):
    with pytest.raises(ValueError):
        ModelConfig(**kwargs).validate()


@pytest.mark.integration
@pytest.mark.parametrize("model", ["SPM", "SPMe", "DFN"])
def test_models_stop_at_voltage_and_conserve_lithium(model):
    result = simulate(ModelConfig(model=model))
    assert "Minimum voltage" in result.termination
    assert abs(result.voltage_v[-1] - 2.5) < 1e-5
    assert 4 < result.capacity_ah[-1] < 5.5
    assert result.physical_audit["passed"]
    assert np.all(np.diff(result.time_s) > 0)
    assert result.metadata()["temperature_status"] == "imposed, not predicted"
    assert result.metadata()["voltage_cutoff_reached"]


@pytest.mark.integration
def test_thermal_energy_audit_and_honest_status():
    result = simulate(ModelConfig(model="SPM", thermal="lumped"))
    balance = result.physical_audit["thermal_energy_balance"]
    assert balance["relative_residual"] < 0.01
    assert result.temperature_k[-1] > result.temperature_k[0]
    assert "NOT validated" in result.metadata()["temperature_status"]


@pytest.mark.integration
def test_temperature_guard_is_not_a_voltage_cutoff():
    result = simulate(ModelConfig(model="SPM", thermal="lumped", max_temperature_k=298.16))
    assert "temperature" in result.termination
    assert result.time_s[-1] < 2
    assert not result.metadata()["voltage_cutoff_reached"]
    assert result.metadata()["cutoff_capacity_ah"] is None


@pytest.mark.integration
def test_cached_template_never_carries_state_between_inputs():
    from physical_fpv.core import _simulation_template

    _simulation_template.cache_clear()
    first = simulate(ModelConfig(model="SPM", current_a=5))
    different = simulate(ModelConfig(model="SPM", current_a=2.5, ambient_temperature_k=300.15))
    repeated = simulate(ModelConfig(model="SPM", current_a=5))
    assert different.time_s[-1] > first.time_s[-1]
    np.testing.assert_allclose(first.voltage_v, repeated.voltage_v, rtol=1e-9, atol=1e-9)
    assert first.capacity_ah[0] == repeated.capacity_ah[0] == 0
    assert different.temperature_k[0] == 300.15
    assert repeated.temperature_k[0] == 298.15
    assert first.metadata()["compiled_template_cache"]["hit"] is False
    assert repeated.metadata()["compiled_template_cache"]["hit"] is True
    _simulation_template.cache_clear()
    fresh = simulate(ModelConfig(model="SPM", current_a=5))
    np.testing.assert_allclose(repeated.voltage_v, fresh.voltage_v, rtol=1e-9, atol=1e-9)


def test_bounded_oregan_representative_grid_extension():
    ModelConfig(parameter_set="ORegan2022", mesh_points=120).validate()
    with pytest.raises(ValueError):
        ModelConfig(parameter_set="ORegan2022", mesh_points=121).validate()


@pytest.mark.integration
def test_native_concentration_audit_matches_full_values_without_interpolation_buffers(monkeypatch):
    from pybamm.solvers.processed_variable import ProcessedVariable1D, ProcessedVariable2D

    from physical_fpv.core import _simulation_template

    def forbid_padding(*args, **kwargs):
        raise AssertionError("Spatial interpolation buffers must not be built for native audits")

    config = ModelConfig(model="DFN", mesh_points=10)
    with monkeypatch.context() as scoped:
        scoped.setattr(ProcessedVariable1D, "_interp_setup", forbid_padding)
        scoped.setattr(ProcessedVariable2D, "_interp_setup", forbid_padding)
        result = simulate(config)
    assert result.physical_audit["passed"]
    solution = _simulation_template(
        config.model,
        config.thermal,
        config.parameter_set,
        config.mesh_points,
        config.tolerance,
        config.max_temperature_k,
        config.heat_transfer_coefficient_w_m2_k,
    ).solution
    for electrode in ("Negative", "Positive"):
        native = solution[f"{electrode} particle concentration [mol.m-3]"]
        surface = solution[f"{electrode} particle surface concentration [mol.m-3]"]
        assert not native.entries_raw_initialized
        assert not surface.entries_raw_initialized
        np.testing.assert_array_equal(native.observe_raw(), native.entries)
        np.testing.assert_array_equal(surface.observe_raw(), surface.entries)
        audit = result.physical_audit["concentration_bounds"][electrode.lower()]
        assert audit["node_min_mol_m3"] == native.entries.min()
        assert audit["node_max_mol_m3"] == native.entries.max()
        assert audit["surface_min_mol_m3"] == surface.entries.min()
        assert audit["surface_max_mol_m3"] == surface.entries.max()
