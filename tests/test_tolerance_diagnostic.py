"""Frozen-tolerance diagnostic controls; no scientific solve or source download."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
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
    return load("run_stanford_k2_tolerance")


def test_preparation_freezes_every_baseline_input_and_only_two_tolerances(
    tmp_path, monkeypatch, runner
):
    monkeypatch.setattr(
        pybamm.Simulation, "solve", lambda *a, **k: pytest.fail("No solve in preparation")
    )
    out = tmp_path / "inputs"
    manifest = runner.prepare_inputs(out)
    assert runner.verify_inputs(out) == manifest
    assert manifest["planned_meshes"] == [80]
    assert manifest["maximum_battery_dfns"] == 1
    assert manifest["tolerance_changes"] == {"rtol": [1e-7, 1e-8], "atol": [1e-7, 1e-8]}
    assert manifest["baseline_configurations"]["80"] == {
        **manifest["planned_configurations"]["80"],
        "tolerance": 1e-7,
    }
    assert manifest["baseline_run_id"] == "37948404436"
    assert "parameters-mesh120.json" not in manifest["derived_input_sha256"]
    original_runtime = manifest["runtime_versions"]
    manifest["runtime_versions"] = {**original_runtime, "python": "unexpected"}
    runner.write_json(out / "manifest.json", manifest)
    with pytest.raises(ValueError, match="baseline"):
        runner.validate_managed_launch(out, tmp_path / "unused", {})
    manifest["runtime_versions"] = original_runtime
    manifest["maximum_battery_dfns"] = 2
    runner.write_json(out / "manifest.json", manifest)
    with pytest.raises(ValueError, match="bounds"):
        runner.verify_inputs(out)


@pytest.mark.parametrize("code", [0, 2, 124, -9])
def test_one_stage_even_on_success_no_hidden_fine_or_retry(tmp_path, monkeypatch, runner, code):
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
    assert calls[0][calls[0].index("--mesh") + 1] == "80"
    assert (result == 0) == (code == 0)
    ledger = json.loads((args.out / "launch.json").read_text())
    assert ledger["maximum_battery_dfns"] == 1
    assert ledger["shared_wall_limit_s"] == 1200
    assert ledger["worker_address_space_limit_bytes"] == 4_000_000_000
    with pytest.raises(ValueError, match="duplicate"):
        runner.execute(args)


def test_effective_tolerance_override_or_cached_vector_rejected(runner):
    model = SimpleNamespace(len_rhs_and_alg=3)
    solver = SimpleNamespace(rtol=1e-8, _setup={"atol": np.full(3, 1e-8)})
    sim = SimpleNamespace(built_model=model, solver=solver)
    assert runner.effective_tolerances(sim)["expanded_atol_count"] == 3
    solver._setup["atol"][1] = 1e-7
    with pytest.raises(ValueError, match="Effective"):
        runner.effective_tolerances(sim)
    solver._setup["atol"][1] = 1e-8
    model.atol = 1e-8
    with pytest.raises(ValueError, match="Effective"):
        runner.effective_tolerances(sim)


def test_comparison_uses_exact_queries_and_separate_endpoints(runner):
    comparison = load("compare_stanford_k2_tolerance")
    left = {
        "time_s": np.array([0.0, 1.0, 2.0]),
        "voltage_v": np.array([4.0, 3.0, 2.5]),
        "temperature_k": np.array([298.0, 299.0, 300.0]),
        "capacity_ah": np.array([0.0, 0.5, 1.0]),
    }
    right = {
        "time_s": np.array([0.0, 1.0, 1.9]),
        "voltage_v": np.array([4.0, 3.004, 2.5]),
        "temperature_k": np.array([298.0, 299.05, 300.0]),
        "capacity_ah": np.array([0.0, 0.5, 0.999]),
    }
    result = comparison.common_query_comparison(left, right, 0.0)
    assert result["exact_shared_samples"] == 2
    assert result["exact_shared_interval_s"] == [0.0, 1.0]
    assert result["maximum_voltage_difference_v"] == pytest.approx(0.004)
    assert result["signed_cutoff_time_difference_s"] == pytest.approx(-0.1)
    assert result["endpoint_capacity_relative_difference"] == pytest.approx(0.001 / 0.999)
    assert result["descriptive_tolerance_stability_passed"]
    assert not result["spatial_convergence_claimed"]
    right["voltage_v"][1] = 3.006
    assert not comparison.common_query_comparison(left, right, 0.0)[
        "descriptive_tolerance_stability_passed"
    ]
    right["capacity_ah"][0] = np.nan
    with pytest.raises(ValueError, match="scalar"):
        comparison.common_query_comparison(left, right, 0.0)


def test_saved_upload_receipt_binds_manifest_run_head(tmp_path, runner):
    comparison = load("compare_stanford_k2_tolerance")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    manifest = {"run_id": "123", "source_commit": "a" * 40}
    runner.write_json(inputs / "manifest.json", manifest)
    receipt = {
        "artifact_id": 456,
        "verified_not_expired": True,
        **manifest,
        "manifest_sha256": runner.digest(inputs / "manifest.json"),
        "artifact_sha256": "sha256:" + "b" * 64,
    }
    runner.write_json(tmp_path / "upload-receipt.json", receipt)
    assert comparison.verify_upload_receipt(tmp_path / "evidence", manifest) == receipt
    for key, value in (
        ("run_id", "999"),
        ("source_commit", "c" * 40),
        ("manifest_sha256", "d" * 64),
        ("artifact_id", -1),
        ("verified_not_expired", False),
        ("artifact_sha256", "missing"),
    ):
        runner.write_json(tmp_path / "upload-receipt.json", {**receipt, key: value})
        with pytest.raises(ValueError, match="receipt"):
            comparison.verify_upload_receipt(tmp_path / "evidence", manifest)
