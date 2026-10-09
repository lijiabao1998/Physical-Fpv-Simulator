import json

import numpy as np
import pytest

from physical_fpv.contrast_persistence import (
    charge_coordinates,
    evaluate,
    linear_summary,
    time_at_charge,
)


@pytest.mark.parametrize("currents", [(2, 2), (1, 3), (3, 1), (2, 2 + 1e-12)])
def test_charge_inverse_against_independent_polynomial(currents):
    t = np.array([1.0, 3601.0])
    x = np.column_stack([t, currents, [4, 3], [298, 299]])
    total = (currents[0] + currents[1]) / 2
    assert charge_coordinates(x)[-1] == total
    for fraction in (0, 0.01, 0.25, 0.5, 0.99, 1):
        target = total * fraction
        returned = time_at_charge(x, target)
        dt = returned - 1
        forward = (currents[0] * dt + (currents[1] - currents[0]) * dt**2 / 7200) / 3600
        assert abs(forward - target) <= 1e-12
    assert time_at_charge(x, 0) == 1
    assert time_at_charge(x, total) == 3601


def test_exact_charge_knots_and_unsupported_target():
    x = np.array([[1, 1, 4, 298], [3601, 3, 3.5, 299], [7201, 2, 3, 300]])
    assert time_at_charge(x, 2) == 3601
    with pytest.raises(ValueError, match="outside"):
        time_at_charge(x, 4.50001)
    x[1, 1] = 0
    with pytest.raises(ValueError, match="positive"):
        charge_coordinates(x)


def test_linear_summary_signed_mean_rms_and_knot_max():
    summary = linear_summary([0, 1, 3], [-1, 1, 1])
    assert summary["mean"] == pytest.approx(2 / 3)
    assert summary["rms"] == pytest.approx(np.sqrt(7 / 9))
    assert summary["max_abs"] == 1


def fixture_cases(variation=0):
    t = np.array([1.0, 10.0, 60.0, 300.0, 900.0, 1800.0, 4000.0])
    cases = {}
    descriptors = {"k1": 0.06, "k2": 0.03}
    anchors = {"k1": 4.18, "k2": 4.19}
    for name, current in (("k1", 5.0), ("k2", 4.0)):
        drop = current * descriptors[name] + 0.00001 * t
        if name == "k1":
            drop += variation * (t - 10)
        measured = np.column_stack(
            [t, np.full(len(t), current), anchors[name] - drop, 298 + t / 1000]
        )
        model = np.column_stack([t, 4.1 - t / 10000, 299 + t / 1000])
        cases[name] = measured, model
    return cases, descriptors, anchors


def test_constant_contrast_with_unequal_currents_and_common_error():
    result = evaluate(*fixture_cases())
    json.dumps(result, allow_nan=False)
    for window in result["time_windows"]:
        assert window["summaries"]["discrepancy_v"]["max_abs"] < 1e-12
        assert window["summaries"]["identity_closure_v"]["max_abs"] < 1e-12
    assert result["time_windows"][-1]["summaries"]["k1_individual_discrepancy_v"]["max_abs"] > 0.039
    assert (
        result["conditional_charge_points"][0]["times_s"]["k1"]
        != result["conditional_charge_points"][0]["times_s"]["k2"]
    )


def test_time_varying_contrast_is_retained_and_not_fitted():
    result = evaluate(*fixture_cases(1e-5))
    last = result["time_windows"][-1]["summaries"]["discrepancy_v"]
    assert last["end"] == pytest.approx(0.0399, abs=1e-12)
    assert last["rms"] > 0.02
    assert result["frozen_descriptor_ohm"] == {"k1": 0.06, "k2": 0.03}


def test_charge_beyond_model_support_not_rezeroed_or_extrapolated():
    cases, descriptors, anchors = fixture_cases()
    measured, model = cases["k1"]
    cases["k1"] = measured, model[:4]
    result = evaluate(cases, descriptors, anchors)
    assert all(not point["supported"] for point in result["conditional_charge_points"])
    assert result["time_windows"][-1]["empty"]
    assert result["conditional_charge_points"][0]["unavailable_reasons"]["k1"] == (
        "Charge-matched time outside archived model support"
    )


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_nonfinite_signal_rejected(bad):
    cases, descriptors, anchors = fixture_cases()
    cases["k1"][0][2, 2] = bad
    with pytest.raises(ValueError, match="Nonfinite"):
        evaluate(cases, descriptors, anchors)


def test_charge_beyond_measured_support_has_reason():
    cases, descriptors, anchors = fixture_cases()
    measured, model = cases["k2"]
    cases["k2"] = measured[:4], model
    result = evaluate(cases, descriptors, anchors)
    assert result["conditional_charge_points"][0]["unavailable_reasons"]["k2"] == (
        "Charge target outside measured support"
    )


def test_signed_descriptor_remains_descriptive():
    cases, descriptors, anchors = fixture_cases()
    descriptors["k1"] = -0.01
    result = evaluate(cases, descriptors, anchors)
    assert result["frozen_descriptor_ohm"]["k1"] == -0.01


def test_unsynchronized_native_breakpoint_is_included():
    cases, descriptors, anchors = fixture_cases()
    measured, model = cases["k1"]
    point = np.array([40.0, 5.0, anchors["k1"] - 0.3 - 0.0004 - 0.02, 298.04])
    measured = np.insert(measured, 2, point, axis=0)
    model_times = np.array([1, 25, 100, 350, 1050, 2000, 4000], dtype=float)
    model = np.column_stack([model_times, 4.1 - model_times / 10000, 299 + model_times / 1000])
    cases["k1"] = measured, model
    summary = evaluate(cases, descriptors, anchors)["time_windows"][0]["summaries"]["discrepancy_v"]
    assert summary["mean"] == pytest.approx(0.01, abs=1e-12)
    assert summary["rms"] == pytest.approx(0.02 / np.sqrt(3), abs=1e-12)
    assert summary["max_abs"] == pytest.approx(0.02, abs=1e-12)


def load_runner():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "persistence_runner", root / "scripts/check_stanford_contrast_persistence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_reproduced(actual, expected):
    assert type(actual) is type(expected)
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            if key != "elapsed_s":
                assert_reproduced(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            assert_reproduced(a, b)
    elif isinstance(expected, float):
        assert np.isfinite(actual) and np.isfinite(expected)
        assert actual == pytest.approx(expected, rel=0, abs=1e-12)
    else:
        assert actual == expected


def test_offline_reproduction_and_changed_source_rejection(tmp_path, monkeypatch):
    import shutil
    import socket

    runner = load_runner()
    source = runner.ROOT / "docs/benchmarks"

    def forbidden(*args, **kwargs):
        raise AssertionError("No network permitted")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = runner.run(source, tmp_path / "output")
    archived = json.loads((source / "stanford-contrast-persistence.json").read_text())
    assert_reproduced(report, archived)
    assert report["historical_passed"] == {"k1": False, "k2": False}
    assert report["new_dfns_solved"] == 0
    assert report["parameters_fitted"] is False
    changed = tmp_path / "changed"
    changed.mkdir()
    for name in runner.HASHES:
        shutil.copyfile(source / name, changed / name)
    target = changed / "stanford-k1-discharge-records.csv.gz"
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Source hash changed"):
        runner.run(changed, tmp_path / "rejected")


def test_materially_changed_result_and_flag_rejected():
    expected = {"value_v": 0.1, "physical_passed": False}
    with pytest.raises(AssertionError):
        assert_reproduced({"value_v": 0.100001, "physical_passed": False}, expected)
    with pytest.raises(AssertionError):
        assert_reproduced({"value_v": 0.1, "physical_passed": True}, expected)
