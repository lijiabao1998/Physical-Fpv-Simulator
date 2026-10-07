import hashlib
from pathlib import Path

import numpy as np
import pytest

from physical_fpv.core import ModelConfig, simulate
from physical_fpv.thermal_benchmark import (
    THERMAL_PROTOCOL_SHA256,
    piecewise_error,
    temperature_domains,
)
from physical_fpv.thermal_data import inspect_cohort, load_thermal_cohort, verify_archive


def test_frozen_thermal_protocol():
    assert (
        hashlib.sha256(Path("docs/thermal-protocol.md").read_bytes()).hexdigest()
        == THERMAL_PROTOCOL_SHA256
    )


def test_thermal_archive_corruption_rejected():
    with pytest.raises(ValueError, match="SHA256"):
        verify_archive(b"invalid archive")


def test_exact_thermal_piecewise_error():
    rmse, peak = piecewise_error(np.array([0.0, 10.0, 20.0]), np.array([0.0, 3.0, 0.0]))
    assert rmse == pytest.approx(np.sqrt(3))
    assert peak == 3


def test_property_domain_flags_use_full_temperature_trajectories():
    report = temperature_domains(np.array([297.65, 330.0]), np.array([297.65, 315.0]))
    breaches = report["breaches"]
    assert any(b["property"] == "heat_capacity_measurements" for b in breaches)
    assert any(
        b["property"] == "solid_diffusion_measurements"
        and b["trajectory"] == "surface_measurement_c"
        for b in breaches
    )
    assert not report["inside_all_listed_measurement_domains"]


@pytest.mark.data
def test_real_thermal_parser_and_cumulative_accumulators():
    path = Path("data/oregan/raw/validation.zip")
    if not path.exists():
        pytest.skip("Run physical-fpv thermal-fetch-data")
    traces = load_thermal_cohort(path)
    report = inspect_cohort(traces)
    assert report["files"] == 36
    assert report["unique_cells"] == 12
    assert report["duplicate_records"] == 361
    assert report["changed_duplicate_records"] == 5
    assert all(
        abs(t.discharge.measured_capacity_ah - t.discharge.reported_capacity_ah) < 0.001
        for t in traces
    )
    assert all(abs(t.measured_energy_wh - t.accumulator_energy_wh) < 0.003 for t in traces)
    assert sum(t.discharge.cell == "791" for t in traces) == 3
    assert all(t.quality_flags for t in traces if t.discharge.cell == "791")
    assert all(np.all(np.diff(t.discharge.time_s) > 0) for t in traces)


@pytest.mark.integration
def test_oregan_temperature_dependent_energy_and_provenance():
    result = simulate(
        ModelConfig(
            parameter_set="ORegan2022",
            thermal="lumped",
            current_a=5,
            heat_transfer_coefficient_w_m2_k=15,
        )
    )
    assert result.metadata()["parameter_set"] == "ORegan2022"
    assert result.physical_audit["thermal_energy_balance"]["passed"]
    assert np.ptp(result.heat_capacity_j_k) > 0.01
    assert result.physical_audit["thermal_energy_balance"]["relative_to_generated_heat"] < 0.01


@pytest.mark.integration
def test_particle_audit_uses_physical_nodes_not_plotting_ghost_extrapolation():
    from physical_fpv.core import _simulation_template

    config = ModelConfig(
        parameter_set="ORegan2022",
        thermal="lumped",
        current_a=5,
        heat_transfer_coefficient_w_m2_k=15,
    )
    result = simulate(config)
    simulation = _simulation_template(
        config.model,
        config.thermal,
        config.parameter_set,
        config.mesh_points,
        config.tolerance,
        config.max_temperature_k,
        config.heat_transfer_coefficient_w_m2_k,
    )
    variable = simulation.solution["Negative particle concentration [mol.m-3]"]
    assert np.min(variable(simulation.solution.t)) < 0  # Plotting-only ghost extrapolation.
    assert np.min(variable.entries) > 0  # Actual finite-volume unknowns are physical.
    audit = result.physical_audit["concentration_bounds"]["negative"]
    assert audit["node_array_shape"][:2] == [20, 20]
    assert audit["surface_min_mol_m3"] > 0
    assert result.physical_audit["passed"]


def test_refinement_failure_preserves_other_numerical_stage(monkeypatch):
    from types import SimpleNamespace

    import physical_fpv.thermal_benchmark as module

    primary = SimpleNamespace(config=ModelConfig(parameter_set="ORegan2022", mesh_points=40))

    def controlled_solve(config):
        if config.mesh_points == 80:
            raise RuntimeError("explicit simulated resource failure")
        return primary

    monkeypatch.setattr(module, "simulate", controlled_solve)
    monkeypatch.setattr(module, "thermal_numerics", lambda a, b: {"passed": True})
    checks = module.audit_refinements(primary)
    assert checks["mesh"]["passed"] is False
    assert "resource failure" in checks["mesh"]["error"]
    assert checks["solver_tolerance"]["passed"] is True
