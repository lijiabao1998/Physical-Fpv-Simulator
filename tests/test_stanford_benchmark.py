import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from physical_fpv.core import ModelConfig, SimulationResult
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.stanford_benchmark import (
    PROTOCOL_SHA256,
    evaluate_pilot,
    prepare_pilot,
    product_integral,
    verify_protocol,
)


def fixture(endpoint=20.0):
    profile = CurrentProfile([0, 60], [5, 5])
    t = np.array([0, 10, endpoint])
    v = 4.0 - 0.05 * t
    result = SimulationResult(
        ModelConfig(),
        t,
        v,
        5 * t / 3600,
        np.full(3, 298.15),
        np.ones(3),
        np.zeros(3),
        np.zeros(3),
        None,
        "event: Minimum voltage [V]",
        {"passed": True},
        "synthetic-test",
        current_protocol={"fingerprint_sha256": profile.fingerprint_sha256},
    )
    source_t = np.array([1.0006, 10.0, 20.0])
    observed = np.column_stack((source_t, np.full(3, -5), 4 - 0.05 * source_t, np.full(3, 298.15)))
    return observed, profile, result


def test_missing_start_charge_is_excluded_symmetrically():
    observed, profile, model = fixture()
    report = evaluate_pilot(observed, profile, model)
    assert report["capacity_relative_error"] == pytest.approx(0, abs=1e-14)
    assert report["energy_relative_error"] == pytest.approx(0, abs=1e-14)
    assert report["measured_observed_capacity_ah"] == pytest.approx(5 * (20 - 1.0006) / 3600)
    assert report["initial_assumed_charge_excluded_from_metrics_ah"] == pytest.approx(
        5 * 1.0006 / 3600
    )
    assert report["electrical_gates_passed"]
    assert not report["independent_thermal_validation_established"]


def test_early_cutoff_cannot_hide_capacity_loss_by_cropping_overlap():
    observed, profile, model = fixture(endpoint=12)
    report = evaluate_pilot(observed, profile, model)
    assert report["voltage_rmse_v"] == pytest.approx(0, abs=1e-14)
    assert report["capacity_relative_error"] > 0.4
    assert report["observed_time_coverage"] < 0.6
    assert not report["electrical_gates_passed"]


def test_late_cutoff_uses_explicit_command_continuation_without_extending_observations():
    observed, profile, model = fixture(endpoint=30)
    report = evaluate_pilot(observed, profile, model)
    assert report["common_observed_interval_s"] == [1.0006, 20]
    assert report["unobserved_late_continuation_used_s"] == 10
    assert report["capacity_relative_error"] > 0.5
    assert not report["electrical_gates_passed"]


def test_energy_uses_exact_product_of_linear_current_and_voltage():
    # Integral (1+t)(2+3t), t=0..2, is22 rather than endpoint-trapezoid26.
    assert product_integral(np.array([0, 2]), np.array([1, 3]), np.array([2, 8])) == pytest.approx(
        22
    )


def test_wrong_forcing_or_temperature_stop_cannot_pass():
    observed, profile, model = fixture()
    model.termination = "event: Research temperature envelope"
    assert not evaluate_pilot(observed, profile, model)["electrical_gates_passed"]
    observed[:, 1] = -4.85
    with pytest.raises(ValueError, match="amperes"):
        evaluate_pilot(observed, profile, model)


def test_prediction_protocol_is_frozen_and_chronology_is_qualified():
    assert (
        hashlib.sha256(Path("docs/stanford-validation-protocol.md").read_bytes()).hexdigest()
        == PROTOCOL_SHA256
    )
    assert verify_protocol(Path.cwd())["recorded_order_qualified"]


@pytest.mark.data
def test_measured_pilot_preparation_preserves_gap_and_unfitted_boundary():
    if not Path("data/stanford/raw/NMC_k1_1C_25degC.xlsx").exists():
        pytest.skip("Acquire the predeclared Stanford pilot")
    pytest.importorskip("openpyxl")
    observed, profile, config, assumptions = prepare_pilot(
        Path("data/stanford/raw"), json.loads(Path("data/stanford-manifest.json").read_text())
    )
    assert observed[0, 0] == 1.0006
    np.testing.assert_array_equal(profile.value_at(observed[:, 0]), -observed[:, 1])
    assert config.current_a == pytest.approx(5.000325282873757)
    assert config.initial_temperature_k == pytest.approx(298.33794059753)
    assert not assumptions["initial_interval_is_measured"]
    assert not assumptions["parameter_fitting_performed"]
