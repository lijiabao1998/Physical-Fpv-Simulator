"""Small synthetic software fixtures; never a new scientific k2 experiment."""

import importlib.util
from types import SimpleNamespace

import numpy as np
import pybamm
import pytest

from physical_fpv.core import ModelConfig, simulate
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.polarization import export_polarization


def runner():
    spec = importlib.util.spec_from_file_location(
        "k2_state", "scripts/diagnose_stanford_k2_state.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture(scope="module")
def profile_fixture():
    profile = CurrentProfile([0, 100, 3000, 6000], [5, 5.2, 4.8, 5])
    config = ModelConfig(
        parameter_set="ORegan2022",
        thermal="lumped",
        mesh_points=10,
        initial_temperature_k=297.75,
        heat_transfer_coefficient_w_m2_k=15,
        sample_period_s=60,
    )
    original = pybamm.Simulation.solve
    result, simulation, solution = runner().capture_one_solve(simulate, config, profile)
    assert pybamm.Simulation.solve is original
    actual = simulation.parameter_values.copy()
    assert np.array_equal(actual["Current function [A]"].x[0], profile.time_s)
    actual.update({"Current function [A]": config.current_a})
    return result, solution, actual, profile


@pytest.mark.integration
def test_actual_variable_current_state_accounting(tmp_path, profile_fixture):
    result, solution, parameters, profile = profile_fixture
    report = export_polarization(tmp_path, result, solution, parameters, current_profile=profile)
    assert report["accounting_passed"]
    assert (
        report["provenance"]["current_profile"]["actual_solution_current_max_difference_a"] <= 1e-9
    )
    assert report["voltage_reconstruction_max_error_v"] <= 1e-6


@pytest.mark.integration
def test_waveform_identity_cannot_be_relabelled(tmp_path, profile_fixture):
    result, solution, parameters, profile = profile_fixture
    wrong = CurrentProfile(profile.time_s, profile.current_a + 0.01)
    with pytest.raises(ValueError, match="current-profile identity"):
        export_polarization(tmp_path, result, solution, parameters, current_profile=wrong)
    with pytest.raises(ValueError, match="fingerprint"):
        export_polarization(tmp_path, result, solution, parameters)


@pytest.mark.integration
def test_actual_solution_current_checked(tmp_path, profile_fixture):
    result, solution, parameters, profile = profile_fixture

    class CorruptCurrent:
        t = solution.t

        def __getitem__(self, name):
            value = solution[name]
            if name == "Current [A]":
                return SimpleNamespace(entries=value.entries + 0.001)
            return value

    with pytest.raises(ValueError, match="Solved current"):
        export_polarization(tmp_path, result, CorruptCurrent(), parameters, current_profile=profile)


def test_observer_restored_on_simulation_error():
    original = pybamm.Simulation.solve

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic solver failure")

    with pytest.raises(RuntimeError, match="synthetic solver failure"):
        runner().capture_one_solve(broken, None, None)
    assert pybamm.Simulation.solve is original


def test_missing_solve_is_rejected():
    with pytest.raises(RuntimeError, match="authenticate"):
        runner().capture_one_solve(lambda *a, **k: None, None, None)


def test_support_crossings_are_observed_brackets_not_continuous_times(tmp_path):
    path = tmp_path / "synthetic.csv"
    path.write_text(
        "time_s,negative_surface_min_stoichiometry,negative_surface_max_stoichiometry,"
        "positive_surface_min_stoichiometry,positive_surface_max_stoichiometry\n"
        "0,0.2,0.5,0.3,0.8\n1,0.1,0.5,0.3,0.9\n2,0.09,0.5,0.3,0.95\n"
    )
    result = runner().summarize_states(path, 2)
    for electrode in ("negative", "positive"):
        crossing = result["support_crossings"][electrode]
        assert crossing["first_observed_outside_s"] == 1
        assert crossing["preceding_observation_s"] == 0
        assert crossing["outside_saved_samples"] == 2
    assert result["continuous_crossing_or_outside_duration_inferred"] is False


def test_observer_blocks_a_second_solve(monkeypatch):
    calls = []

    def original(simulation, *args, **kwargs):
        calls.append(1)
        simulation.solution = object()
        return simulation.solution

    monkeypatch.setattr(pybamm.Simulation, "solve", original)

    def twice(config, **kwargs):
        value = SimpleNamespace()
        pybamm.Simulation.solve(value)
        pybamm.Simulation.solve(value)

    with pytest.raises(RuntimeError, match="More than one"):
        runner().capture_one_solve(twice, None, None)
    assert len(calls) == 1
    assert pybamm.Simulation.solve is original
