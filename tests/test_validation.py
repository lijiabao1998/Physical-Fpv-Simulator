import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from physical_fpv.core import ModelConfig, SimulationResult
from physical_fpv.data import Discharge
from physical_fpv.validation import PROTOCOL_SHA256, compare_trace


def fixtures():
    time = np.array([0.0, 10.0, 20.0])
    data = Discharge(
        "02",
        7,
        0.5,
        time,
        np.full(3, 0.5),
        np.array([4.0, 3.0, 2.5]),
        np.full(3, 298.15),
        np.full(3, 298.15),
        0.5 * 20 / 3600,
        "fixture",
    )
    result = SimulationResult(
        ModelConfig(current_a=0.5),
        time,
        data.voltage_v.copy(),
        time * 0.5 / 3600,
        np.full(3, 298.15),
        np.ones(3),
        np.zeros(3),
        np.zeros(3),
        None,
        "event: Minimum voltage [V]",
        {"passed": True},
        "fixture",
    )
    return data, result


def test_frozen_protocol_is_not_silently_changed():
    text = Path("docs/validation-protocol.md").read_bytes()
    assert hashlib.sha256(text).hexdigest() == PROTOCOL_SHA256


def test_exact_trace_passes_metrics():
    data, result = fixtures()
    report = compare_trace(data, result)
    assert report["passed"]
    assert report["voltage_rmse_v"] == 0


def test_voltage_rmse_is_time_weighted_and_no_initial_alignment():
    data, result = fixtures()
    result.voltage_v += 0.1
    report = compare_trace(data, result)
    assert report["voltage_rmse_v"] == pytest.approx(0.1)
    assert not report["passed"]


def test_early_termination_cannot_hide_behind_common_interval():
    data, result = fixtures()
    for name in ["time_s", "voltage_v", "capacity_ah", "temperature_k", "lithium_mol"]:
        setattr(result, name, getattr(result, name)[:2])
    report = compare_trace(data, result)
    assert report["time_coverage"] == 0.5
    assert report["voltage_rmse_v"] == 0
    assert not report["passed"]


def test_temperature_termination_cannot_pass_experimental_gate():
    data, result = fixtures()
    result.termination = "event: Research temperature envelope"
    assert not compare_trace(data, result)["gates"]["voltage_cutoff_reached"]


def test_reject_mismatched_current_protocol():
    data, result = fixtures()
    result.config = replace(result.config, current_a=5)
    with pytest.raises(ValueError, match="different current"):
        compare_trace(data, result)


def test_model_knots_and_exact_piecewise_linear_squared_error():
    data, result = fixtures()
    data = replace(
        data,
        time_s=np.array([0.0, 20.0]),
        current_a=np.full(2, 0.5),
        voltage_v=np.array([4.0, 2.5]),
    )
    result.voltage_v = np.array([4.0, 4.25, 2.5])
    report = compare_trace(data, result)
    assert report["voltage_max_abs_error_v"] == pytest.approx(1.0)
    assert report["voltage_rmse_v"] == pytest.approx(np.sqrt(1 / 3))
