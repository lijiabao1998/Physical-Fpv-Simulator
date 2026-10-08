"""Persistence checks use synthetic arrays, never an electrochemical solve."""

import importlib.util
import json

import numpy as np
import pytest

from physical_fpv.core import ModelConfig, SimulationResult


def runner():
    spec = importlib.util.spec_from_file_location("k2_runner", "scripts/run_stanford_k2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic():
    time = np.array([0.0, 1.0, 2.0])
    return SimulationResult(
        ModelConfig(parameter_set="ORegan2022", thermal="lumped", mesh_points=80),
        time,
        np.array([4.1, 3.7, 2.5]),
        time * 5 / 3600,
        np.array([297.55, 298.0, 298.1]),
        np.full(3, 0.3),
        np.array([0.1, 0.2, 0.3]),
        np.array([-0.01, 0.01, 0.02]),
        np.array([65.0, 65.1, 65.2]),
        "event: Minimum voltage [V]",
        {"passed": False, "synthetic_failure": "retained"},
        "synthetic-test-only",
        current_protocol={"type": "synthetic current", "fingerprint_sha256": "synthetic"},
    )


def test_native_summary_roundtrip_keeps_heat_and_failed_audit(tmp_path):
    module = runner()
    original = synthetic()
    module.save_snapshot(tmp_path, 80, original)
    restored = module.load_snapshot(tmp_path, 80)
    for name in module.ARRAY_NAMES:
        np.testing.assert_array_equal(getattr(restored, name), getattr(original, name))
    assert restored.physical_audit == original.physical_audit
    assert restored.parameter_fingerprint == original.parameter_fingerprint
    assert restored.current_protocol == original.current_protocol
    index = json.loads((tmp_path / "mesh80-snapshot.json").read_text())
    assert "freshness not established" in index["model"]["scope"]


def test_saved_array_byte_corruption_is_rejected(tmp_path):
    module = runner()
    module.save_snapshot(tmp_path, 80, synthetic())
    path = tmp_path / "mesh80-arrays.npz"
    path.write_bytes(path.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="integrity"):
        module.load_snapshot(tmp_path, 80)


def test_wrong_saved_grid_cannot_be_called_a_refinement(tmp_path):
    module = runner()
    module.save_snapshot(tmp_path, 80, synthetic())
    for suffix in ("arrays.npz", "snapshot.json"):
        (tmp_path / f"mesh120-{suffix}").write_bytes((tmp_path / f"mesh80-{suffix}").read_bytes())
    with pytest.raises(ValueError, match="mesh identity"):
        module.load_snapshot(tmp_path, 120)


def test_missing_lumped_heat_capacity_is_not_silently_dropped(tmp_path):
    module = runner()
    result = synthetic()
    result.heat_capacity_j_k = None
    with pytest.raises(ValueError, match="thermal-capacity"):
        module.save_snapshot(tmp_path, 80, result)
    assert not (tmp_path / "mesh80-snapshot.json").exists()


def test_completed_numeric_failure_does_not_qualify_prediction(tmp_path):
    module = runner()
    path = tmp_path / "report.json"
    module.write_json(
        path,
        {
            "execution_budget_passed": True,
            "spatial_numerical_check": {"passed": False},
            "source_window_empirical_qualification_passed": True,
        },
    )
    state = module.qualification_status(path, "completed")
    assert state["missing_or_failed_numerical_stage_is_unverified"]
    assert not state["conditional_prediction_qualified"]


def test_empirical_disagreement_is_not_missing_numerical_execution(tmp_path):
    module = runner()
    path = tmp_path / "report.json"
    module.write_json(
        path,
        {
            "execution_budget_passed": True,
            "spatial_numerical_check": {"passed": True},
            "source_window_empirical_qualification_passed": False,
        },
    )
    state = module.qualification_status(path, "completed")
    assert not state["missing_or_failed_numerical_stage_is_unverified"]
    assert not state["conditional_prediction_qualified"]


def test_missing_or_over_budget_result_cannot_be_qualified(tmp_path):
    module = runner()
    path = tmp_path / "report.json"
    assert module.qualification_status(path, "budget_exhausted")["numerical_targets_passed"] is None
    module.write_json(
        path,
        {
            "execution_budget_passed": True,
            "spatial_numerical_check": {"passed": True},
            "source_window_empirical_qualification_passed": True,
        },
    )
    assert module.qualification_status(path, "completed")["conditional_prediction_qualified"]
    assert not module.qualification_status(path, "budget_exhausted")[
        "conditional_prediction_qualified"
    ]


def summary_fixture():
    return {
        "execution_budget_passed": True,
        "spatial_numerical_check": {"passed": True},
        "source_window_empirical_qualification_passed": True,
        "numerically_qualified_conditional_prediction_passed": True,
    }


def test_expired_shared_budget_never_starts_summary(tmp_path, monkeypatch):
    module = runner()

    def forbidden(out):
        pytest.fail("Summary must not start after deadline")

    monkeypatch.setattr(module, "summarize", forbidden)
    assert module.finish_summary(tmp_path, 0, 1200, lambda: 1200) == "budget_exhausted"
    assert not (tmp_path / "report.json").exists()
    assert json.loads((tmp_path / "stage.json").read_text())["status"] == "budget_exhausted"


@pytest.mark.parametrize("clock_values", [(1199, 1201), (1199, 1199.1, 1199.2, 1201)])
def test_summary_crossing_deadline_cannot_leave_report_pass(tmp_path, monkeypatch, clock_values):
    module = runner()
    monkeypatch.setattr(module, "summarize", lambda out: summary_fixture())
    clock = iter(clock_values)
    assert module.finish_summary(tmp_path, 0, 1200, lambda: next(clock)) == "budget_exhausted"
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["spatial_numerical_check"]["passed"]
    assert not report["execution_budget_passed"]
    assert not report["numerically_qualified_conditional_prediction_passed"]
    assert json.loads((tmp_path / "stage.json").read_text())["status"] == "budget_exhausted"


def test_summary_timeout_keeps_no_completed_stage(tmp_path, monkeypatch):
    module = runner()

    def expired(out):
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(module, "summarize", expired)
    assert module.finish_summary(tmp_path, 0, 1200, lambda: 1199) == "budget_exhausted"
    assert not (tmp_path / "report.json").exists()
    assert json.loads((tmp_path / "stage.json").read_text())["status"] == "budget_exhausted"


def test_summary_inside_budget_seals_consistent_completion(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module, "summarize", lambda out: summary_fixture())
    assert module.finish_summary(tmp_path, 0, 1200, lambda: 10) == "completed"
    path = tmp_path / "report.json"
    assert json.loads(path.read_text())["execution_budget_passed"]
    assert module.qualification_status(path, "completed")["conditional_prediction_qualified"]
    assert json.loads((tmp_path / "stage.json").read_text())["status"] == "completed"
