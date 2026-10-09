import numpy as np
import pytest

from physical_fpv.full_rate_shape import LABELS, differences, evaluate, measured_summary


def cases():
    out = {}
    for label in LABELS:
        current = 0.25 if label.endswith("005c") else 5.0
        t = np.array([1.0, 1 + 18000 / current])
        r = 0.06 if label.startswith("k1") else 0.03
        out[label] = np.column_stack(
            [t, np.full(2, current), np.array([4.2, 3.0]) - current * r, np.array([298, 300])]
        )
    return out


def test_analytic_charge_mean_and_raw_cutoff():
    x = np.array([[1, 1, 4, 298], [3601, 3, 2.4, 300]], dtype=float)
    result = measured_summary(x)
    assert result["observed_charge_ah"] == 2
    assert result["current_a"]["time_weighted_mean"] == 2
    assert result["last_voltage_minus_nominal_cutoff_v"] == pytest.approx(-0.1)
    assert result["omitted_command_interval_s"] == [0.0, 1.0]
    assert result["missing_initial_charge_known"] is False
    assert result["exact_cutoff_crossing_verified"] is False


def test_frozen_descriptors_and_contrast_identity():
    descriptors = {"k1": 0.06, "k2": 0.03}
    result = evaluate(cases(), descriptors)
    assert result["frozen_descriptors_ohm"] == descriptors
    for point in result["conditional_charge_points"]:
        assert point["all_four_supported"]
        assert abs(point["contrasts"]["descriptive_w_v"]["rate_interaction"]) < 1e-12
        assert point["contrasts"]["voltage_v"]["rate_interaction"] == pytest.approx(0.1425)
        assert abs(point["contrasts"]["voltage_v"]["identity_closure"]) < 1e-12
        assert abs(point["contrasts"]["descriptive_w_v"]["specimen_k1_minus_k2"]["1c"]) < 1e-12


def test_unequal_support_preserves_available_pairs():
    x = cases()
    x["k1_005c"][1, 0] = 3601
    result = evaluate(x, {"k1": 0.06, "k2": 0.03})
    point = result["conditional_charge_points"][0]
    assert not point["all_four_supported"]
    assert point["unavailable_reasons"]["k1_005c"]
    assert point["contrasts"]["voltage_v"]["specimen_k1_minus_k2"]["1c"] is not None
    assert point["contrasts"]["voltage_v"]["within_specimen_low_minus_high"]["k2"] is not None
    assert point["contrasts"]["voltage_v"]["rate_interaction"] is None


def test_difference_order_and_all_missing():
    result = differences({"k1_005c": 4.0, "k2_005c": 3.9, "k1_1c": 3.8, "k2_1c": 3.5})
    assert result["rate_interaction"] == pytest.approx(-0.2)
    assert differences({})["rate_interaction"] is None


@pytest.mark.parametrize("current", [0, -1, np.nan])
def test_invalid_current_rejected(current):
    x = cases()
    x["k1_1c"][0, 1] = current
    with pytest.raises(ValueError):
        evaluate(x, {"k1": 0.06, "k2": 0.03})


def runner():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "full_shape_runner", root / "scripts/check_stanford_full_rate_shape.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(actual, expected):
    assert type(actual) is type(expected)
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            if key != "elapsed_s":
                compare(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            compare(a, b)
    elif isinstance(expected, float):
        assert np.isfinite(actual) and np.isfinite(expected)
        assert actual == pytest.approx(expected, rel=0, abs=1e-12)
    else:
        assert actual == expected


def test_offline_full_record_reproduction_and_hash_guard(tmp_path, monkeypatch):
    import json
    import shutil
    import socket

    module = runner()
    source = module.ROOT / "docs/benchmarks"

    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    report = module.run(source, tmp_path / "output")
    archived = json.loads((source / "stanford-full-rate-shape.json").read_text())
    compare(report, archived)
    assert {
        name: summary["rows"] for name, summary in report["comparison"]["record_summaries"].items()
    } == {"k1_005c": 70000, "k2_005c": 70370, "k1_1c": 3391, "k2_1c": 3436}
    assert report["historical_passed"] == {"k1": False, "k2": False}
    changed = tmp_path / "changed"
    changed.mkdir()
    for name in module.HASHES:
        shutil.copyfile(source / name, changed / name)
    target = changed / "stanford-k1-low-rate-discharge.csv.gz"
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Source hash changed"):
        module.run(changed, tmp_path / "rejected")


def test_reproduction_rejects_material_change_and_nonfinite():
    for value in (1.00001, np.nan, np.inf):
        with pytest.raises(AssertionError):
            compare({"charge_ah": value}, {"charge_ah": 1.0})
