"""Coarse solve checks accounting and exporter behavior, never scientific convergence."""

import csv
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pybamm
import pytest

from physical_fpv.core import ModelConfig, _simulation_template, simulate
from physical_fpv.polarization import VOLTAGE_TERMS, export_polarization


@pytest.fixture(scope="module")
def solved():
    config = ModelConfig(
        parameter_set="ORegan2022",
        thermal="lumped",
        mesh_points=10,
        current_a=5,
        initial_temperature_k=297.75,
        heat_transfer_coefficient_w_m2_k=15,
        sample_period_s=30,
    )
    result = simulate(config)
    solution = _simulation_template(
        config.model,
        config.thermal,
        config.parameter_set,
        config.mesh_points,
        config.tolerance,
        config.max_temperature_k,
        config.heat_transfer_coefficient_w_m2_k,
    ).solution
    parameters = pybamm.ParameterValues(config.parameter_set)
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.initial_temperature_k,
            "Total heat transfer coefficient [W.m-2.K-1]": 15,
        }
    )
    return result, solution, parameters


@pytest.mark.integration
def test_voltage_and_inventory_accounting_from_native_entries(tmp_path, solved):
    result, solution, parameters = solved
    report = export_polarization(tmp_path, result, solution, parameters)
    assert report["accounting_passed"]
    assert report["voltage_reconstruction_max_error_v"] <= 1e-6
    assert all(e <= 1e-6 for e in report["mean_stoichiometry_charge_max_error"].values())
    assert report == json.loads((tmp_path / "polarization.json").read_text())
    with (tmp_path / "polarization.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(result.time_s)
    for state in report["states"]:
        index = state["index"]
        assert state["time_s"] == result.time_s[index]
        for electrode in ("negative", "positive"):
            native = solution[f"{electrode.capitalize()} particle surface stoichiometry"].entries
            assert state["scalars"][f"{electrode}_surface_min_stoichiometry"] == np.min(
                native[:, index]
            )
            assert state["scalars"][f"{electrode}_surface_max_stoichiometry"] == np.max(
                native[:, index]
            )
            profile = state["profiles"][f"{electrode}_r_average_stoichiometry"]
            assert len(profile) == 10
            expected = np.asarray(
                solution[f"R-averaged {electrode} particle stoichiometry"].entries
            )[:, index]
            np.testing.assert_array_equal(profile, expected)
    assert rows[0]["imposed_surface_boundary_temperature_k"] == str(
        result.config.ambient_temperature_k
    )
    assert report["provenance"]["parameters"]["Negative electrode OCP [V]"]["source_sha256"]
    assert all(
        e <= 1e-6 for e in report["accounting"]["initial_mean_vs_declared_max_error"].values()
    )
    assert all("source" not in f for f in report["provenance"]["functions"])
    for key, _, sign in VOLTAGE_TERMS:
        assert sign == (-1 if key.startswith("negative") or key == "contact" else 1)
        for row in rows:
            assert float(row[f"{key}_signed_v"]) == sign * float(row[f"{key}_raw_v"])


class EntriesOnlySolution:
    """Refuse callable interpolation and optionally corrupt one raw observable."""

    def __init__(self, solution, corrupted=None):
        self.solution = solution
        self.t = solution.t
        self.all_models = solution.all_models
        self.corrupted = corrupted

    def __getitem__(self, name):
        variable = self.solution[name]
        values = variable.entries
        if name == self.corrupted:
            values = -values
        return SimpleNamespace(entries=values, mesh=variable.mesh)


@pytest.mark.integration
def test_export_does_not_interpolate_and_detects_raw_sign_corruption(tmp_path, solved):
    result, solution, parameters = solved
    report = export_polarization(
        tmp_path / "valid", result, EntriesOnlySolution(solution), parameters
    )
    assert report["accounting_passed"]
    corrupted = EntriesOnlySolution(solution, "Negative particle concentration overpotential [V]")
    report = export_polarization(tmp_path / "corrupt", result, corrupted, parameters)
    assert not report["accounting_passed"]
    assert report["voltage_reconstruction_max_error_v"] > 1e-6


@pytest.mark.integration
def test_result_and_parameter_corruption_cannot_pass(tmp_path, solved):
    result, solution, parameters = solved
    wrong_mean = EntriesOnlySolution(solution, "Negative electrode stoichiometry")
    report = export_polarization(tmp_path / "inventory", result, wrong_mean, parameters)
    assert not report["accounting_passed"]
    assert report["mean_stoichiometry_charge_max_error"]["negative"] > 1e-6
    wrong_voltage = replace(result, voltage_v=result.voltage_v + 0.01)
    assert not export_polarization(tmp_path / "voltage", wrong_voltage, solution, parameters)[
        "accounting_passed"
    ]
    wrong_parameters = parameters.copy()
    wrong_parameters.update({"Negative electrode thickness [m]": 1e-4})
    with pytest.raises(ValueError, match="fingerprint"):
        export_polarization(tmp_path / "parameters", result, solution, wrong_parameters)
    with pytest.raises(ValueError, match="output times"):
        export_polarization(
            tmp_path / "time", replace(result, time_s=result.time_s + 1), solution, parameters
        )
