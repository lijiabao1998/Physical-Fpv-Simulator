"""One-shot refinement controls and complete deduplicated reference provenance."""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pybamm
import pytest


def load(name):
    sys.path.insert(0, str(Path("scripts").resolve()))
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load("run_stanford_k2_mesh120")


def test_prepare_persists_exact_reference_without_recursive_archives(tmp_path, monkeypatch, runner):
    def forbidden(*args, **kwargs):
        raise AssertionError("No solve during preparation")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    out = tmp_path / "inputs"
    manifest = runner.prepare_inputs(out)
    assert runner.verify_inputs(out) == manifest
    assert manifest["planned_meshes"] == [120]
    assert manifest["maximum_battery_dfns"] == 1
    assert manifest["fixed_tolerances"] == {"rtol": 1e-8, "atol": 1e-8}
    assert manifest["baseline_run_id"] == "37954785347"
    assert manifest["baseline_preparation_receipt"]["archived_source_files_verified"] == 56
    assert manifest["baseline_preparation_receipt"]["selected_members_persisted"] == 8
    assert not manifest["baseline_preparation_receipt"]["recursive_archive_duplication"]
    for name in runner.DEDUPLICATED_OLD_ARCHIVES:
        assert not (out / "files" / name).exists()
        assert name not in manifest["source_sha256"]
    assert (
        manifest["derived_input_sha256"]["parameters-mesh120.json"]
        == runner.BASELINE_PINS["derived_input_sha256"]["parameters-mesh80.json"]
    )
    baseline = json.loads((out / "baseline/evidence/mesh80/report.json").read_text())
    assert baseline["physical_audit"]["passed"]
    assert (
        baseline["arrays_sha256"]
        == runner.BASELINE_PINS["members"]["evidence/mesh80/scalar-arrays.npz"]["sha256"]
    )
    (out / "baseline/evidence/mesh80/report.json").write_text("{}")
    with pytest.raises(ValueError, match="baseline member"):
        runner.verify_inputs(out)


def test_manifest_pin_omission_is_rejected_before_extraction(tmp_path, monkeypatch, runner):
    pins = copy.deepcopy(runner.BASELINE_PINS)
    pins["source_sha256"].pop(next(iter(pins["source_sha256"])))
    monkeypatch.setattr(runner, "BASELINE_PINS", pins)
    with pytest.raises(ValueError, match="Complete baseline manifest"):
        runner.extract_baseline(tmp_path / "baseline")


@pytest.mark.parametrize("code", [0, 2, 124, -9])
def test_one_mesh120_even_after_failure_or_success(tmp_path, monkeypatch, runner, code):
    monkeypatch.setattr(runner, "validate_managed_launch", lambda *a: {})
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    calls = []

    def fake(command, deadline):
        calls.append(command)
        out = Path(command[command.index("--out") + 1])
        runner.write_json(out / "report.json", {"physical_audit": {"passed": code == 0}})
        return {"exit_code": code, "status": "exited"}

    monkeypatch.setattr(runner, "run_process_with_deadline", fake)
    args = SimpleNamespace(
        prepared=tmp_path / "inputs", upload_receipt=tmp_path / "upload", out=tmp_path / "evidence"
    )
    result = runner.execute(args)
    assert len(calls) == 1
    assert calls[0][calls[0].index("--mesh") + 1] == "120"
    assert (result == 0) == (code == 0)
    ledger = json.loads((args.out / "launch.json").read_text())
    assert ledger["maximum_battery_dfns"] == 1
    assert ledger["shared_wall_limit_s"] == 1200
    assert ledger["worker_address_space_limit_bytes"] == 4_000_000_000
    with pytest.raises(ValueError, match="duplicate"):
        runner.execute(args)


def test_mesh_only_comparison_rejects_parameter_or_tolerance_drift(runner):
    baseline = copy.deepcopy(runner.BASELINE_PINS["config"])
    refined = {**baseline, "mesh_points": 120, "finite_witness_field_sizes": {"test": 123}}
    runner.assert_mesh_only_change(baseline, refined)
    for key, value in (
        ("tolerance", 1e-7),
        ("initial_temperature_k", 299.0),
        ("mean_observed_current_a", 5.0),
    ):
        with pytest.raises(ValueError, match="Physics or tolerances"):
            runner.assert_mesh_only_change(baseline, {**refined, key: value})


def test_joint_gate_keeps_numerical_empirical_and_thermal_proxy_distinct(runner):
    module = load("compare_stanford_k2_mesh120")
    mesh = {"full_numerical_qualification_passed": True}
    empirical = {
        "electrical_gates_passed": True,
        "thermal_proxy_gates": {"rmse": True, "maximum": True},
    }
    result = module.qualify(mesh, empirical, empirical)
    assert result["joint_mesh_pair_and_dataset_gates_passed"]
    assert not result["independent_validation_established"]
    bad_proxy = {**empirical, "thermal_proxy_gates": {"rmse": True, "maximum": False}}
    result = module.qualify(mesh, empirical, bad_proxy)
    assert result["both_mesh_empirical_electrical_gates_passed"]
    assert not result["joint_mesh_pair_and_dataset_gates_passed"]
    assert not module.qualify({"full_numerical_qualification_passed": False}, empirical, empirical)[
        "joint_mesh_pair_and_dataset_gates_passed"
    ]
    assert not module.qualify(mesh, empirical, {**empirical, "electrical_gates_passed": False})[
        "joint_mesh_pair_and_dataset_gates_passed"
    ]
