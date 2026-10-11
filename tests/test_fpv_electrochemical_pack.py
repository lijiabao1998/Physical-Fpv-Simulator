"""Implementation verification; none of these tests is empirical qualification."""

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from physical_fpv.fpv.electrochemical_pack import (
    ElectrochemicalPackConfig,
    _motor_state,
    solve_electrochemical_pack,
)
from physical_fpv.materials import PropertyEstimate, analytic_material_example


@pytest.fixture(scope="module")
def nominal():
    return solve_electrochemical_pack()


def test_actual_spm_is_simultaneously_load_coupled(nominal):
    r = nominal
    c = ElectrochemicalPackConfig()
    t, v, bus, i, pack, q = (
        np.array(r[key])
        for key in (
            "time_s",
            "cell_voltage_v",
            "bus_voltage_v",
            "cell_current_a",
            "pack_current_a",
            "cell_charge_c",
        )
    )
    assert t[0] == 0 and t[-1] == c.duration_s
    np.testing.assert_allclose(pack, c.parallel * i, atol=1e-12)
    resistance = c.harness_resistance_ohm + c.series * c.branch_harness_resistance_ohm / c.parallel
    np.testing.assert_allclose(bus, c.series * v - pack * resistance, atol=1e-12)
    np.testing.assert_allclose(pack, np.sum(r["esc_input_current_a"], axis=1), atol=1e-6)
    np.testing.assert_allclose(r["pack_charge_c"], c.parallel * q, atol=1e-12)
    assert 0.5 < np.min(i) < np.max(i) < 7.5
    assert np.max(v) - np.min(v) > 0.01
    assert np.max(i) - np.min(i) > 0.01  # Current changes despite constant command.
    assert np.min(np.array(r["cell_bulk_ocv_v"]) - v) > 0.05
    assert q[0] == 0 and np.all(np.diff(q) > 0)
    # Bounded derivative integral, independent of the lithium-state charge audit.
    integrated = np.trapezoid(i, t)
    assert abs(q[-1] - integrated) < 5e-4
    assert r["physical_audit"]["passed"]
    assert r["physical_audit"]["max_electrode_charge_error_c"] < 1e-7
    assert r["physical_audit"]["max_total_lithium_error_mol"] < 1e-12


def test_downstream_equations_match_existing_powertrain():
    c = ElectrochemicalPackConfig()
    reference = c.reference_load()
    for voltage in (3.0, 12.0, 18.0):
        duties = np.array([0.0, 0.2, 0.4, 0.7])
        actual = _motor_state(duties, voltage, c, np.sqrt)
        expected = reference._motors(duties, voltage)
        for a, b in zip(actual, expected[:3], strict=True):
            np.testing.assert_allclose(a, b, rtol=1e-14, atol=1e-12)


def test_circuit_power_is_cell_terminal_not_chemical(nominal):
    r = nominal
    terminal = np.array(r["cell_terminal_power_w"])
    harness = np.array(r["branch_harness_heat_w"]) + np.array(r["shared_harness_heat_w"])
    channels = sum(
        np.array(r[key])
        for key in (
            "motor_copper_loss_w",
            "esc_loss_w",
            "motor_friction_loss_w",
            "rotor_power_w",
        )
    )
    np.testing.assert_allclose(terminal, harness + channels.sum(axis=1), atol=1e-5)
    np.testing.assert_allclose(r["bus_power_w"], channels.sum(axis=1), atol=1e-5)
    assert "not cell thermodynamic energy" in r["physical_audit"]["terminal_power_scope"]


def test_controls_change_electrochemistry_and_shared_bus():
    c = ElectrochemicalPackConfig(duration_s=3)
    low = solve_electrochemical_pack([0.25] * 4, config=c)
    high = solve_electrochemical_pack([0.4] * 4, config=c)
    mixed = solve_electrochemical_pack([0.4, 0.25, 0.25, 0.25], config=c)
    assert high["cell_current_a"][0] > 3 * low["cell_current_a"][0]
    assert high["cell_voltage_v"][0] < low["cell_voltage_v"][0] - 0.05
    assert high["cell_charge_c"][-1] > low["cell_charge_c"][-1]
    assert mixed["rotor_thrust_n"][-1][0] > mixed["rotor_thrust_n"][-1][1]
    # Raising one motor's duty sags the shared bus and lowers other rotors' thrust.
    assert mixed["rotor_thrust_n"][-1][1] < low["rotor_thrust_n"][-1][1]


def test_series_parallel_scaling_is_current_sharing_not_cell_count_capacity():
    a = solve_electrochemical_pack(config=ElectrochemicalPackConfig(parallel=2, duration_s=2))
    b = solve_electrochemical_pack(config=ElectrochemicalPackConfig(parallel=4, duration_s=2))
    assert b["cell_current_a"][0] < a["cell_current_a"][0]
    assert b["cell_voltage_v"][0] > a["cell_voltage_v"][0]
    assert b["pack_current_a"][0] > a["pack_current_a"][0]
    assert b["pack_charge_c"][-1] == pytest.approx(4 * b["cell_charge_c"][-1])


def test_mesh_and_internal_timestep_refinement():
    c = ElectrochemicalPackConfig(duration_s=10, max_step_s=0.5, sample_period_s=0.25)
    commands = [[0.3] * 4, [0.43, 0.4, 0.38, 0.36]]
    runs = [
        solve_electrochemical_pack(
            commands, duty_times_s=[0, 10], config=replace(c, mesh_points=mesh)
        )
        for mesh in (20, 40, 80)
    ]
    voltage = [np.array(r["cell_voltage_v"]) for r in runs]
    coarse_error = np.max(abs(voltage[0] - voltage[1]))
    fine_error = np.max(abs(voltage[1] - voltage[2]))
    assert 0 < fine_error < coarse_error < 0.01
    assert fine_error < 0.003  # Explicitly a ~mV discretization check, not exact convergence.
    assert abs(runs[1]["cell_charge_c"][-1] - runs[2]["cell_charge_c"][-1]) < 0.04
    refined = solve_electrochemical_pack(
        commands, duty_times_s=[0, 10], config=replace(c, mesh_points=40, max_step_s=0.1)
    )
    np.testing.assert_allclose(refined["cell_voltage_v"], voltage[1], atol=2e-6, rtol=0)
    np.testing.assert_allclose(refined["cell_current_a"], runs[1]["cell_current_a"], atol=2e-5)
    np.testing.assert_allclose(refined["cell_charge_c"], runs[1]["cell_charge_c"], atol=5e-5)
    assert all(r["physical_audit"]["passed"] for r in runs + [refined])


def test_schedule_knots_are_retained_and_command_interpolation_is_explicit():
    r = solve_electrochemical_pack(
        [[0.25] * 4, [0.4] * 4, [0.3] * 4],
        duty_times_s=[0, 0.37, 2],
        config=ElectrochemicalPackConfig(duration_s=2, sample_period_s=0.2),
    )
    assert 0.37 in r["time_s"]
    expected = np.interp(r["time_s"], [0, 0.37, 2], [0.25, 0.4, 0.3])
    np.testing.assert_allclose(np.array(r["duties"])[:, 0], expected)
    assert r["physical_audit"]["passed"]


@pytest.mark.parametrize("duties", [[0.01] * 4, [0.8] * 4, [0] * 4])
def test_initial_current_outside_chen_envelope_fails_closed(duties):
    with pytest.raises(ValueError, match="supported bridge domain"):
        solve_electrochemical_pack(duties, config=ElectrochemicalPackConfig(duration_s=1))


def test_current_domain_exit_during_ramp_is_not_returned_as_partial_success():
    with pytest.raises(ValueError, match="supported domain"):
        solve_electrochemical_pack(
            [[0.3] * 4, [0.8] * 4],
            duty_times_s=[0, 2],
            config=ElectrochemicalPackConfig(duration_s=2),
        )


def test_motor_speed_domain_is_also_an_event_guard():
    config = ElectrochemicalPackConfig(
        series=12,
        parallel=2,
        thrust_coefficient=0.001,
        torque_coefficient=0.0001,
        duration_s=1,
    )
    with pytest.raises(ValueError, match="motor 0 speed envelope"):
        solve_electrochemical_pack([0.5] * 4, config=config)


@pytest.mark.parametrize(
    "change",
    [
        {"temperature_k": 299.15},
        {"temperature_k": np.nan},
        {"duration_s": 31},
        {"duration_s": 0},
        {"duration_s": True},
        {"mesh_points": 9},
        {"mesh_points": 81},
        {"mesh_points": True},
        {"max_step_s": 0},
        {"sample_period_s": 0.001},
        {"parallel": [[2]]},
        {"series": True},
        {"branch_harness_resistance_ohm": -1},
        {"motor_constant_si": 0},
        {"thrust_coefficient": 0.9, "torque_coefficient": 0.0001},
    ],
)
def test_configuration_domain_guard_before_solve(change):
    with pytest.raises(ValueError):
        solve_electrochemical_pack(config=ElectrochemicalPackConfig(**change))


@pytest.mark.parametrize(
    ("duties", "times"),
    [
        (0.3, None),
        ([True] * 4, None),
        ([0.3, 0.3, np.nan, 0.3], None),
        ([0.3, 0.3, 0.3, 1.1], None),
        ([0.3, 0.3], None),
        ([[0.3] * 4] * 2, [1, 10]),
        ([[0.3] * 4] * 2, [0, 11]),
        ([[0.3] * 4] * 3, [0, 0, 10]),
        ([[0.3] * 3] * 2, [0, 10]),
    ],
)
def test_schedule_domain_guard(duties, times):
    with pytest.raises(ValueError):
        solve_electrochemical_pack(duties, duty_times_s=times)


def test_unqualified_material_does_not_become_a_cell_parameter():
    p = PropertyEstimate(**analytic_material_example()["estimate"])
    with pytest.raises(ValueError, match="not qualified battery properties"):
        solve_electrochemical_pack(estimates=(("negative", p.phase, p),))


def test_evidence_scope_and_reproducible_hash(nominal):
    assert nominal["empirical_gate"] == "NOT ESTABLISHED"
    assert nominal["validity_uplift"] is False
    assert nominal["sources"][0]["independently_validated"] is False
    assert "invented" in nominal["downstream_provenance"]
    assert "imposed" in nominal["temperature_status"]
    assert "no lagged current" in nominal["coupling"]
    payload = {k: v for k, v in nominal.items() if k not in {"sha256", "cpu_time_s"}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    assert digest == nominal["sha256"]
    assert nominal["cpu_time_s"] < 240
    assert len(nominal["parameter_fingerprint"]) == 64
