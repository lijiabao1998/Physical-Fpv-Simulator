"""Synthetic analytical and falsification checks, not hardware validation."""

import json
from dataclasses import replace

import numpy as np
import pytest

from physical_fpv.fpv.powertrain import Powertrain, PowertrainConfig


def test_identical_cells_have_analytical_series_parallel_equivalent():
    c = PowertrainConfig(series=3, parallel=4)
    p = Powertrain(c)
    out = p.evaluate([0.2, 0.3, 0.4, 0.5])
    expected_ocv = c.series * (c.ocv_empty_v + c.initial_soc * (c.ocv_full_v - c.ocv_empty_v))
    expected_r = (
        c.series / c.parallel * (c.cell_resistance_ohm + c.cell_harness_resistance_ohm)
        + c.harness_resistance_ohm
    )
    assert out.voltage_v == pytest.approx(expected_ocv - expected_r * out.current_a, abs=2e-12)
    np.testing.assert_allclose(out.cell_currents_a, out.current_a / c.parallel, atol=2e-12)
    np.testing.assert_allclose(out.cell_currents_a.sum(axis=1), out.current_a, atol=2e-12)


def heterogeneous():
    return PowertrainConfig(
        series=2,
        parallel=3,
        initial_soc=[[0.89, 0.80, 0.83], [0.88, 0.82, 0.91]],
        cell_capacity_ah=[[1.4, 1.5, 1.6], [1.5, 1.3, 1.7]],
        cell_resistance_ohm=[[0.02, 0.03, 0.04], [0.025, 0.02, 0.03]],
        cell_harness_resistance_ohm=[[0.001, 0.003, 0.002], [0.002, 0.004, 0.001]],
    )


def test_heterogeneous_parallel_branches_obey_kcl_kvl_and_power():
    c = heterogeneous()
    out = Powertrain(c).evaluate([0.3, 0.4, 0.5, 0.6])
    np.testing.assert_allclose(out.cell_currents_a.sum(axis=1), out.current_a, atol=4e-13)
    np.testing.assert_allclose(
        out.cell_ocv_v
        - out.cell_currents_a
        * (np.asarray(c.cell_resistance_ohm) + np.asarray(c.cell_harness_resistance_ohm)),
        np.broadcast_to(out.group_voltage_v[:, None], (2, 3)),
        atol=2e-14,
    )
    assert out.group_voltage_v.sum() - c.harness_resistance_ohm * out.current_a == (
        pytest.approx(out.voltage_v, abs=2e-12)
    )
    assert out.chemical_power_w == pytest.approx(
        out.bus_power_w
        + out.cell_heat_w.sum()
        + out.branch_harness_heat_w.sum()
        + out.shared_harness_heat_w,
        abs=2e-11,
    )
    assert abs(out.power_balance_error_w) < 2e-11


def test_unequal_cells_circulate_charge_and_heat_at_zero_external_load():
    c = PowertrainConfig(series=1, parallel=2, initial_soc=[[0.9, 0.7]])
    p = Powertrain(c)
    before = p.evaluate([0.0] * 4)
    expected = (
        (0.9 - 0.7)
        * (c.ocv_full_v - c.ocv_empty_v)
        / (2 * (c.cell_resistance_ohm + c.cell_harness_resistance_ohm))
    )
    assert before.current_a == 0.0
    np.testing.assert_allclose(before.cell_currents_a, [[expected, -expected]], atol=2e-14)
    assert before.chemical_power_w > 0
    assert before.bus_power_w == 0
    assert before.cell_heat_w.sum() > 0
    after = p.step([0.0] * 4, 0.1)
    assert after.soc[0, 0] < 0.9
    assert after.soc[0, 1] > 0.7
    assert after.soc.sum() == pytest.approx(1.6, abs=2e-15)
    assert np.all(after.cell_temperature_k > before.cell_temperature_k)


def test_unequal_resistance_splits_load_inversely_without_equal_current_shortcut():
    c = PowertrainConfig(
        series=1,
        parallel=2,
        cell_resistance_ohm=[[0.02, 0.04]],
        cell_harness_resistance_ohm=0.0,
    )
    out = Powertrain(c).evaluate([0.6] * 4)
    assert out.cell_currents_a[0, 0] == pytest.approx(2 * out.cell_currents_a[0, 1])


def test_motor_back_emf_torque_esc_and_rotor_equations():
    c = PowertrainConfig()
    duty = np.array([0.0, 0.2, 0.6, 0.95])
    out = Powertrain(c).evaluate(duty)
    omega, current = out.rotor_speed_rad_s, out.motor_current_a
    np.testing.assert_allclose(
        out.motor_voltage_v,
        c.motor_resistance_ohm * current + c.motor_constant_si * omega,
        atol=2e-14,
    )
    np.testing.assert_allclose(
        c.motor_constant_si * current,
        out.rotor_torque_nm + c.motor_viscous_friction_nm_s * omega,
        atol=2e-16,
    )
    np.testing.assert_allclose(out.esc_input_current_a, duty * current, atol=1e-14)
    np.testing.assert_allclose(
        duty * out.voltage_v * current, out.esc_loss_w + out.motor_voltage_v * current, atol=2e-13
    )
    n = omega / (2 * np.pi)
    np.testing.assert_allclose(
        out.thrust_n,
        c.thrust_coefficient * c.air_density_kg_m3 * n**2 * c.propeller_diameter_m**4,
        atol=3e-15,
    )
    np.testing.assert_allclose(
        out.rotor_torque_nm,
        c.torque_coefficient * c.air_density_kg_m3 * n**2 * c.propeller_diameter_m**5,
        atol=2e-17,
    )
    assert out.bus_power_w == pytest.approx(
        float(
            out.motor_copper_loss_w.sum()
            + out.esc_loss_w.sum()
            + out.motor_friction_loss_w.sum()
            + out.rotor_power_w.sum()
        ),
        abs=3e-12,
    )
    area = np.pi * c.propeller_diameter_m**2 / 4
    ideal_power = out.thrust_n**1.5 / np.sqrt(2 * c.air_density_kg_m3 * area)
    assert np.all(out.rotor_power_w >= ideal_power)


def test_loading_another_motor_reduces_speed_through_shared_bus_sag():
    p = Powertrain()
    one = p.evaluate([0.7, 0, 0, 0])
    four = p.evaluate([0.7] * 4)
    assert four.current_a > one.current_a
    assert four.voltage_v < one.voltage_v
    assert four.rotor_speed_rad_s[0] < one.rotor_speed_rad_s[0]
    assert four.thrust_n[0] < one.thrust_n[0]


def test_higher_harness_resistance_reduces_thrust_with_no_arbitrary_buff():
    low = Powertrain().evaluate([0.6] * 4)
    high = Powertrain(PowertrainConfig(harness_resistance_ohm=0.1)).evaluate([0.6] * 4)
    assert high.voltage_v < low.voltage_v
    assert np.all(high.thrust_n < low.thrust_n)


def test_zero_duty_uniform_pack_is_true_electrical_rest():
    p = Powertrain()
    out = p.step([0.0] * 4, 0.1)
    assert out.current_a == out.bus_power_w == out.chemical_power_w == 0.0
    assert np.all(out.thrust_n == 0)
    np.testing.assert_array_equal(out.soc, np.full((4, 2), 0.9))
    np.testing.assert_allclose(out.cell_temperature_k, 298.15, atol=6e-14)


def test_integrated_charge_chemical_energy_and_heat_conserve_for_variable_loads():
    p = Powertrain(heterogeneous())
    initial = p.evaluate([0.0] * 4)
    for i in range(150):
        p.step([0.2 + 0.004 * (i % 100), 0.4, 0.6, 0.7], 0.05, airspeed_m_s=4.0)
    telemetry = p.telemetry()
    end = np.asarray(telemetry["soc"])
    charge = np.asarray(telemetry["integrals"]["cell_charge_drawn_c"])
    np.testing.assert_allclose(
        (initial.soc - end) * np.asarray(p.config.cell_capacity_ah) * 3600, charge, atol=2e-11
    )
    audit = telemetry["audits"]
    assert audit["charge_closure_max_abs_c"] < 2e-11
    assert audit["series_charge_closure_max_abs_c"] < 2e-11
    assert abs(audit["chemical_energy_integration_error_j"]) < 1e-8
    assert abs(audit["energy_balance_error_j"]) < 1e-8
    assert audit["thermal_balance_max_abs_j"] < 1e-8
    json.dumps(telemetry, allow_nan=False)


def test_thermal_midpoint_matches_analytic_cooling_with_second_order_convergence():
    config = PowertrainConfig(
        initial_temperature_k=320.0,
        cooling_w_k=4.0,
        cell_thermal_capacity_j_k=2.0,
        max_step_s=0.2,
    )
    exact = config.ambient_temperature_k + (
        config.initial_temperature_k - config.ambient_temperature_k
    ) * np.exp(-config.cooling_w_k / config.cell_thermal_capacity_j_k)
    errors = []
    for dt in (0.1, 0.05, 0.025):
        p = Powertrain(config)
        for _ in range(round(1.0 / dt)):
            out = p.step([0.0] * 4, dt)
        errors.append(abs(out.cell_temperature_k[0, 0] - exact))
        assert p.telemetry()["audits"]["thermal_balance_max_abs_j"] < 2e-11
    assert 3.9 < errors[0] / errors[1] < 4.1
    assert 3.9 < errors[1] / errors[2] < 4.1


def test_parallel_soc_equalization_matches_analytic_exponential_second_order():
    c = PowertrainConfig(
        series=1,
        parallel=2,
        cell_capacity_ah=0.1,
        cell_resistance_ohm=0.01,
        cell_harness_resistance_ohm=0.0,
        initial_soc=[[0.9, 0.7]],
        max_step_s=1.0,
    )
    decay = (c.ocv_full_v - c.ocv_empty_v) / (c.cell_resistance_ohm * c.cell_capacity_ah * 3600)
    exact_difference = 0.2 * np.exp(-decay * 2)
    errors = []
    for dt in (0.2, 0.1, 0.05):
        p = Powertrain(c)
        for _ in range(round(2 / dt)):
            out = p.step([0.0] * 4, dt)
        errors.append(abs(out.soc[0, 0] - out.soc[0, 1] - exact_difference))
    assert 3.9 < errors[0] / errors[1] < 4.1
    assert 3.9 < errors[1] / errors[2] < 4.1


def test_airflow_increases_cooling_but_does_not_invent_dynamic_propeller_data():
    config = PowertrainConfig(initial_temperature_k=310.0)
    still, moving = Powertrain(config), Powertrain(config)
    for _ in range(20):
        a = still.step([0.5] * 4, 0.1)
        b = moving.step([0.5] * 4, 0.1, airspeed_m_s=20.0)
    assert np.all(b.cell_temperature_k < a.cell_temperature_k)
    np.testing.assert_array_equal(a.thrust_n, b.thrust_n)
    np.testing.assert_array_equal(a.soc, b.soc)


def test_capacity_variability_changes_soc_without_changing_initial_circuit():
    c = PowertrainConfig(series=1, parallel=2, cell_capacity_ah=[[1.0, 2.0]])
    p = Powertrain(c)
    initial = p.evaluate([0.7] * 4)
    np.testing.assert_allclose(initial.cell_currents_a[0, 0], initial.cell_currents_a[0, 1])
    out = p.step([0.7] * 4, 0.1)
    assert 0.9 - out.soc[0, 0] > 0.9 - out.soc[0, 1]
    assert out.cell_currents_a[0, 0] < out.cell_currents_a[0, 1]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"series": 0},
        {"series": True},
        {"series": 4.0},
        {"parallel": 13},
        {"cell_capacity_ah": 0},
        {"cell_resistance_ohm": -0.1},
        {"cell_harness_resistance_ohm": -1},
        {"initial_soc": 1.1},
        {"initial_temperature_k": float("nan")},
        {"initial_soc": [[0.5, 0.8]]},
        {"initial_soc": "0.8"},
        {"initial_soc": True},
        {"ocv_empty_v": 3.5, "ocv_full_v": 3.4},
        {"motor_constant_si": 0},
        {"cooling_w_k": float("inf")},
        {"max_step_s": 0},
        {"motor_resistance_ohm": "0.1"},
        {"motor_constant_si": complex(1, 2)},
        {"thrust_coefficient": 1.0, "torque_coefficient": 0.0001},
    ],
)
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Powertrain(PowertrainConfig(**kwargs))


@pytest.mark.parametrize(
    "duty",
    [
        0.5,
        [0.5] * 3,
        [0.5] * 5,
        [0, 0, 0, -0.1],
        [0, 0, 0, 1.1],
        [0, 0, 0, np.nan],
        [True] * 4,
        ["0.5"] * 4,
    ],
)
def test_invalid_duties_reject_without_state_change(duty):
    p = Powertrain()
    before = p.telemetry()
    with pytest.raises(ValueError):
        p.step(duty, 0.01)
    assert before == p.telemetry()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dt_s": 0},
        {"dt_s": -0.1},
        {"dt_s": 0.11},
        {"dt_s": np.nan},
        {"dt_s": True},
        {"dt_s": 0.01, "airspeed_m_s": -1},
        {"dt_s": 0.01, "airspeed_m_s": 51},
    ],
)
def test_invalid_step_arguments_are_atomic(kwargs):
    p = Powertrain()
    before = p.telemetry()
    with pytest.raises(ValueError):
        p.step([0.5] * 4, **kwargs)
    assert before == p.telemetry()


def test_soc_domain_exit_rejects_instead_of_clipping_or_advancing_time():
    p = Powertrain(PowertrainConfig(initial_soc=0.05001, cell_capacity_ah=0.1))
    before = p.telemetry()
    with pytest.raises(ValueError, match="SOC"):
        p.step([0.6] * 4, 0.1)
    assert before == p.telemetry()


def test_temperature_domain_exit_is_atomic():
    p = Powertrain(PowertrainConfig(initial_temperature_k=333.15, cooling_w_k=0))
    before = p.telemetry()
    with pytest.raises(ValueError, match="temperature"):
        p.step([0.6] * 4, 0.1)
    assert before == p.telemetry()


def test_overcurrent_is_rejected_instead_of_an_unaccounted_current_clamp():
    p = Powertrain(PowertrainConfig(parallel=1, cell_resistance_ohm=0.001))
    before = p.telemetry()
    with pytest.raises(ValueError, match="cell current"):
        p.step([1.0] * 4, 0.1)
    assert before == p.telemetry()


def test_evaluate_does_not_advance_state_and_outputs_cannot_mutate_live_state():
    p = Powertrain()
    out = p.evaluate([0.7] * 4)
    assert p.telemetry()["elapsed_s"] == 0
    assert p.telemetry()["integrals"]["chemical_energy_j"] == 0
    with pytest.raises(ValueError):
        out.soc[0, 0] = 0.5
    # Even deliberately unlocking a returned copy cannot affect the internal state.
    out.soc.setflags(write=True)
    out.soc[0, 0] = 0.4
    assert p.evaluate([0.7] * 4).soc[0, 0] == 0.9


def test_config_array_is_copied_and_determinism_requires_no_rng():
    capacities = np.full((4, 2), 1.5)
    p = Powertrain(PowertrainConfig(cell_capacity_ah=capacities))
    capacities[:] = 19
    q = Powertrain()
    for _ in range(10):
        a = p.step([0.2, 0.4, 0.6, 0.8], 0.05)
        b = q.step([0.2, 0.4, 0.6, 0.8], 0.05)
    assert a.as_dict() == b.as_dict()
    assert p.telemetry() == q.telemetry()
    assert not p.telemetry()["provenance"]["empirically_validated"]
    assert not p.telemetry()["provenance"]["pybamm_parameter_mapping"]


def test_oversized_step_for_fast_cooling_is_rejected():
    p = Powertrain(
        replace(PowertrainConfig(), cell_thermal_capacity_j_k=1.0, cooling_w_k=10, max_step_s=1)
    )
    with pytest.raises(ValueError, match="monotone cooling"):
        p.step([0.0] * 4, 1.0)


def test_fixed_seed_heterogeneous_circuit_sweep_preserves_conservation():
    rng = np.random.default_rng(729)
    for _ in range(100):
        p = Powertrain(
            PowertrainConfig(
                initial_soc=rng.uniform(0.65, 0.95, (4, 2)),
                cell_resistance_ohm=rng.uniform(0.015, 0.05, (4, 2)),
                cell_capacity_ah=rng.uniform(1.0, 2.0, (4, 2)),
            )
        )
        out = p.evaluate(rng.uniform(0, 1, 4))
        assert abs(out.power_balance_error_w) < 1e-9
        assert abs(out.circuit_residual_v) < 1e-12
        np.testing.assert_allclose(
            out.cell_currents_a.sum(axis=1), out.current_a, rtol=0, atol=2e-12
        )


def test_numpy_integer_topology_is_jsonable():
    p = Powertrain(PowertrainConfig(series=np.int64(4), parallel=np.int64(2)))
    json.dumps(p.telemetry(), allow_nan=False)
