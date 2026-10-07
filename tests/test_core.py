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
