import hashlib
from pathlib import Path

import casadi
import numpy as np
import pybamm
import pytest

from physical_fpv import core
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.experimental_low_rate import (
    CORE_SHA,
    FIELDS,
    FINAL_INPUT_TIME_S,
    build,
    finite_witness,
    prepare,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def prepared():
    return prepare(ROOT)


def test_standard_core_lower_current_guard_is_unchanged():
    assert hashlib.sha256((ROOT / "src/physical_fpv/core.py").read_bytes()).hexdigest() == CORE_SHA
    with pytest.raises(ValueError, match="0.5"):
        core.simulate(core.ModelConfig(parameter_set="ORegan2022", current_a=0.25))


def test_exact_measured_support_and_assumed_start_are_explicit(prepared):
    assert len(prepared.observed) == 70370
    assert prepared.profile.time_s[-1] == FINAL_INPUT_TIME_S
    assert prepared.output_time_s[0] == 0
    assert prepared.output_time_s[-1] == FINAL_INPUT_TIME_S
    assert len(prepared.output_time_s) <= 71000
    assert not prepared.observed.flags.writeable
    assert prepared.initial_assumed_charge_ah == pytest.approx(0.00006945052080684238, abs=1e-15)
    assert prepared.metadata["observed_initial_charge_known"] is False
    assert prepared.metadata["initial_heat_capacity_domain_excursion_k"] > 0.65
    with pytest.raises(ValueError):
        prepared.profile.value_at(FINAL_INPUT_TIME_S + 1)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_actual_finite_witness_rejects_invalid_entries_ignored_by_extrema(bad):
    state = pybamm.StateVector(slice(0, 3))
    symbol = casadi.MX.sym("state", 3)
    expression = finite_witness(state).to_casadi(y=symbol)
    function = casadi.Function("full_field_witness", [symbol], [expression])
    for index in range(3):
        values = np.array([1.0, 2.0, 3.0])
        values[index] = bad
        assert not np.isfinite(float(function(values)))
    assert float(function([1, 2, 3])) == 6


def test_output_only_analytic_ode_preserves_observables_and_final_state():
    time = np.linspace(0, 1, 101)
    outputs = []
    for output_only in (False, True):
        model = pybamm.BaseModel()
        y, z = pybamm.Variable("y"), pybamm.Variable("z")
        model.rhs = {y: -y, z: -2 * z}
        model.initial_conditions = {y: 1, z: 2}
        model.variables = {
            "y": y,
            "z": z,
            "minimum": pybamm.minimum(y, z),
            "maximum": pybamm.maximum(y, z),
        }
        solver = pybamm.IDAKLUSolver(
            rtol=1e-9, atol=1e-9, output_variables=list(model.variables) if output_only else None
        )
        solution = solver.solve(model, [0, 1], t_interp=time)
        values = np.array([np.asarray(solution[name](time)) for name in model.variables])
        outputs.append((values, np.asarray(solution.last_state.y)))
        assert solution.y.shape[0] == (0 if output_only else 2)
    np.testing.assert_allclose(outputs[0][0], outputs[1][0], rtol=0, atol=1e-8)
    np.testing.assert_allclose(outputs[0][1], outputs[1][1], rtol=0, atol=1e-8)
    np.testing.assert_allclose(outputs[1][0][0], np.exp(-time), rtol=0, atol=1e-7)
    np.testing.assert_allclose(outputs[1][0][1], 2 * np.exp(-2 * time), rtol=0, atol=1e-7)


@pytest.mark.parametrize("mesh", [80, 120])
def test_non_solving_construction_matches_core_and_complete_array_reductions(
    prepared, mesh, monkeypatch
):
    captured = {}
    original = pybamm.Simulation

    class Captured(Exception):
        pass

    def intercept(model, **kwargs):
        captured.update(model=model, **kwargs)
        raise Captured

    monkeypatch.setattr(pybamm, "Simulation", intercept)
    with pytest.raises(Captured):
        core.simulate(
            core.ModelConfig(
                parameter_set="ORegan2022",
                thermal="lumped",
                initial_temperature_k=297.55456771850584,
                heat_transfer_coefficient_w_m2_k=15,
                mesh_points=mesh,
            ),
            CurrentProfile([0, 6000], [5, 5]),
            profile_schedule="adaptive",
        )
    low_construction = {}

    def observe_low(model, **kwargs):
        for key in ("rhs", "algebraic", "initial_conditions", "boundary_conditions"):
            low_construction[key] = dict(getattr(model, key))
        low_construction["events"] = [(e.name, e.event_type, e.expression) for e in model.events]
        return original(model, **kwargs)

    monkeypatch.setattr(pybamm, "Simulation", observe_low)

    def forbidden(*args, **kwargs):
        raise AssertionError("No battery solve in construction test")

    monkeypatch.setattr(pybamm.BaseSolver, "solve", forbidden)
    sim, outputs, metadata = build(prepared, mesh)
    for key in ("rhs", "algebraic", "initial_conditions", "boundary_conditions"):
        assert low_construction[key] == getattr(captured["model"], key)
    assert low_construction["events"] == [
        (e.name, e.event_type, e.expression) for e in captured["model"].events
    ]
    assert sim.var_pts == captured["var_pts"]
    for parameters in (sim.parameter_values, captured["parameter_values"]):
        parameters.update({"Current function [A]": 1.0, "Initial temperature [K]": 298.15})
    assert core.parameter_fingerprint(sim.parameter_values) == core.parameter_fingerprint(
        captured["parameter_values"]
    )
    assert len(outputs) == 21
    assert set(sim.solver.output_variables) == set(outputs.values())
    built = sim.built_model
    y = np.asarray(built.concatenated_initial_conditions.evaluate(t=0, inputs={})).copy()
    y += 0.0001 * np.sin(np.arange(y.size)).reshape(y.shape)
    for field, source in FIELDS.items():
        full = np.asarray(
            built.get_processed_variable(source).evaluate(t=0, y=y, inputs={})
        ).reshape(-1)
        assert len(full) == metadata["finite_witness_field_sizes"][field]
        for reduction in ["min"] if field == "electrolyte" else ["min", "max"]:
            value = float(
                np.asarray(
                    built.get_processed_variable(outputs[f"{field}_{reduction}_mol_m3"]).evaluate(
                        t=0, y=y, inputs={}
                    )
                ).reshape(-1)[0]
            )
            assert value == pytest.approx(getattr(np, reduction)(full), rel=0, abs=1e-8)
        witness = float(
            np.asarray(
                built.get_processed_variable(outputs[f"{field}_finite_sum_mol_m3"]).evaluate(
                    t=0, y=y, inputs={}
                )
            ).reshape(-1)[0]
        )
        assert witness == pytest.approx(
            float(np.sum(full)), rel=64 * np.finfo(float).eps, abs=1e-12
        )
    for name in outputs.values():
        assert int(np.prod(built.get_processed_variable(name).shape)) == 1


def test_unreviewed_mesh_is_rejected(prepared):
    with pytest.raises(ValueError, match="frozen meshes"):
        build(prepared, 40)


def synthetic_evidence(end=10):
    from types import SimpleNamespace

    from physical_fpv.experimental_low_rate import BASE_OUTPUTS

    time = np.arange(0.0, end + 1)
    profile = CurrentProfile([0, 10], [0.25, 0.25])
    prepared = SimpleNamespace(
        observed=np.array([[1, 0.25, 4.0, 298.15], [10, 0.25, 2.5, 298.15]]),
        profile=profile,
        initial_assumed_charge_ah=0.25 / 3600,
    )
    arrays = {
        "time_s": time,
        "voltage_v": np.interp(time, [0, 1, end], [4.1, 4.0, 2.5]),
        "capacity_ah": profile.charge_integral_ah(time),
        "temperature_k": np.full(len(time), 298.15),
        "lithium_inventory_mol": np.ones(len(time)),
        "heating_w": np.zeros(len(time)),
        "cooling_w": np.zeros(len(time)),
        "heat_capacity_volumetric_j_k_m3": np.full(len(time), 1e6),
    }
    for field in FIELDS:
        value = 1000 if field == "electrolyte" else 28000 if field.startswith("negative") else 12000
        for reduction in ["min"] if field == "electrolyte" else ["min", "max"]:
            arrays[f"{field}_{reduction}_mol_m3"] = np.full(len(time), value, dtype=float)
        arrays[f"{field}_finite_sum_mol_m3"] = np.full(len(time), value * 3, dtype=float)
    metadata = {
        "scalar_output_names": {key: key for key in arrays if key != "time_s"},
        "electrode_maximum_concentrations_mol_m3": {"negative": 30000, "positive": 20000},
        "cell_volume_m3": 1e-6,
    }
    assert set(BASE_OUTPUTS) <= set(arrays)
    return prepared, arrays, metadata


def test_complete_physical_audit_rejects_hidden_nonfinite_witness():
    from physical_fpv.experimental_low_rate import physical_audit

    prepared, arrays, metadata = synthetic_evidence()
    assert physical_audit(arrays, metadata, prepared)["passed"]
    arrays["negative_node_finite_sum_mol_m3"][3] = np.nan
    report = physical_audit(arrays, metadata, prepared)
    assert not report["passed"]
    assert report["nonfinite_scalar_columns"] == ["negative_node_finite_sum_mol_m3"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("negative_surface_min_mol_m3", -1.0),
        ("positive_node_max_mol_m3", 30000.0),
        ("electrolyte_min_mol_m3", 0.0),
        ("capacity_ah", 1.0),
        ("lithium_inventory_mol", 2.0),
    ],
)
def test_physical_audit_preserves_existing_failure_conditions(column, value):
    from physical_fpv.experimental_low_rate import physical_audit

    prepared, arrays, metadata = synthetic_evidence()
    arrays[column][3] = value
    assert not physical_audit(arrays, metadata, prepared)["passed"]


def test_missing_cutoff_cannot_pass_capacity_or_energy():
    from physical_fpv.experimental_low_rate import empirical_report

    prepared, arrays, _ = synthetic_evidence()
    report = empirical_report(prepared, arrays, "final time", {"passed": True})
    assert report["voltage_rmse_v"] < 1e-12
    assert report["capacity_relative_error"] is None
    assert report["energy_relative_error"] is None
    assert not report["electrical_gates_passed"]
    assert not report["cutoff_qualification_available"]


def test_true_cutoff_accounts_for_full_observed_start_energy_and_charge():
    from physical_fpv.experimental_low_rate import empirical_report

    prepared, arrays, _ = synthetic_evidence(end=8)
    report = empirical_report(prepared, arrays, "event: Minimum voltage [V]", {"passed": True})
    assert report["cutoff_qualification_available"]
    assert report["predicted_cutoff_observed_start_charge_ah"] == pytest.approx(0.25 * 7 / 3600)
    assert report["predicted_cutoff_observed_start_energy_wh"] == pytest.approx(
        0.25 * 3.25 * 7 / 3600
    )
    assert report["capacity_relative_error"] == pytest.approx(2 / 9)
    assert report["energy_relative_error"] == pytest.approx(2 / 9)
    assert not report["electrical_gates"]["capacity"]
    assert not report["electrical_gates"]["energy"]


def test_mesh_agreement_does_not_replace_cutoff_or_physical_audit():
    from physical_fpv.experimental_low_rate import compare_meshes, empirical_report

    prepared, arrays, _ = synthetic_evidence()
    report = {
        "physical_audit": {"passed": True},
        "empirical": empirical_report(prepared, arrays, "final time", {"passed": True}),
    }
    result = compare_meshes(arrays, arrays, report, report)
    assert result["common_support_mesh_check_passed"]
    assert not result["full_numerical_qualification_passed"]
    report["empirical"] = empirical_report(
        prepared, arrays, "event: Minimum voltage [V]", {"passed": True}
    )
    assert compare_meshes(arrays, arrays, report, report)["full_numerical_qualification_passed"]
    perturbed = {**arrays, "voltage_v": arrays["voltage_v"] + 0.006}
    assert not compare_meshes(perturbed, arrays, report, report)[
        "full_numerical_qualification_passed"
    ]
    report["physical_audit"]["passed"] = False
    assert not compare_meshes(arrays, arrays, report, report)["full_numerical_qualification_passed"]


def test_mesh_capacity_denominator_excludes_unobserved_initial_charge():
    from copy import deepcopy

    from physical_fpv.experimental_low_rate import compare_meshes, empirical_report

    prepared, arrays, _ = synthetic_evidence()
    fine = {
        "physical_audit": {"passed": True},
        "empirical": empirical_report(
            prepared, arrays, "event: Minimum voltage [V]", {"passed": True}
        ),
    }
    coarse = deepcopy(fine)
    q = fine["empirical"]["predicted_endpoint_observed_start_charge_ah"]
    coarse["empirical"]["predicted_endpoint_observed_start_charge_ah"] = q * 1.01001
    result = compare_meshes(arrays, arrays, coarse, fine)
    assert result["endpoint_capacity_relative_difference"] == pytest.approx(0.01001)
    assert not result["full_numerical_qualification_passed"]


def test_actual_event_endpoint_and_grid_retained_in_output_mode():
    from types import SimpleNamespace

    from physical_fpv.experimental_low_rate import collect_outputs

    model = pybamm.BaseModel()
    y = pybamm.Variable("y")
    model.rhs = {y: -1}
    model.initial_conditions = {y: 1}
    model.variables = {"y": y}
    model.events = [pybamm.Event("toy endpoint", y - 0.3)]
    sim = pybamm.Simulation(
        model, solver=pybamm.IDAKLUSolver(rtol=1e-9, atol=1e-9, output_variables=["y"])
    )
    grid = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    solution = sim.solve([0, 1], t_interp=grid)
    prepared = SimpleNamespace(output_time_s=grid)
    arrays, receipt = collect_outputs(sim, solution, {"value": "y"}, prepared)
    assert arrays["time_s"][-1] == pytest.approx(0.7, abs=1e-8)
    assert arrays["value"][-1] == pytest.approx(0.3, abs=1e-8)
    assert receipt["true_endpoint_preserved"]
    assert receipt["stored_full_history_values"] == 0
    prepared.output_time_s = np.sort(np.r_[grid, 0.1])
    with pytest.raises(ValueError, match="dropped or changed"):
        collect_outputs(sim, solution, {"value": "y"}, prepared)
