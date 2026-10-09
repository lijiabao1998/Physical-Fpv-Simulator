"""No scientific solve: test input persistence, stopping and result honesty."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pybamm
import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load("run_stanford_k2_low_rate_model")


@pytest.fixture(scope="module")
def comparison(runner):
    return load("compare_stanford_k2_rates")


def test_durable_preparation_never_solves_and_guards_upload(tmp_path, monkeypatch, runner):
    def forbidden(*args, **kwargs):
        raise AssertionError("Scientific solve forbidden during input preparation")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    out = tmp_path / "inputs"
    manifest = runner.prepare_inputs(out)
    assert runner.verify_inputs(out) == manifest
    assert manifest["planned_meshes"] == [80, 120]
    assert manifest["maximum_battery_dfns"] == 2
    assert manifest["planned_configurations"]["120"]["mesh_points"] == 120
    parameters = json.loads((out / "parameters-mesh120.json").read_text())
    assert parameters["Initial concentration in negative electrode [mol.m-3]"] == 28866
    assert "def " in parameters["Negative electrode OCP [V]"]
    assert "src/physical_fpv/attribution.py" in manifest["source_sha256"]
    receipt = tmp_path / "upload.json"
    data = {
        "artifact_id": "345",
        "verified_not_expired": True,
        "run_id": "123",
        "source_commit": "a" * 40,
        "manifest_sha256": runner.digest(out / "manifest.json"),
    }
    runner.write_json(receipt, data)
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
    }
    assert runner.validate_managed_launch(out, receipt, env) == manifest
    with pytest.raises(ValueError, match="first reviewed"):
        runner.validate_managed_launch(out, receipt, {**env, "GITHUB_RUN_ATTEMPT": "2"})
    runner.write_json(receipt, {**data, "artifact_id": ""})
    with pytest.raises(ValueError, match="upload required"):
        runner.validate_managed_launch(out, receipt, env)
    (out / "forcing.csv").write_text("changed")
    with pytest.raises(ValueError, match="derived input changed"):
        runner.verify_inputs(out)


@pytest.mark.parametrize("failure_code", [2, 124, -9])
def test_coarse_failure_never_starts_fine(tmp_path, monkeypatch, runner, failure_code):
    monkeypatch.setattr(runner, "validate_managed_launch", lambda *a: {})
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    calls = []

    def execute(command, deadline):
        calls.append((command, deadline))
        return {"exit_code": failure_code, "status": "test_failure"}

    monkeypatch.setattr(runner, "run_process_with_deadline", execute)
    args = SimpleNamespace(
        prepared=tmp_path / "inputs", upload_receipt=tmp_path / "upload", out=tmp_path / "evidence"
    )
    assert runner.execute(args) != 0
    assert len(calls) == 1
    assert calls[0][0][calls[0][0].index("--mesh") + 1] == "80"
    assert "--upload-receipt" in calls[0][0] and "--deadline-monotonic" in calls[0][0]
    ledger = json.loads((args.out / "launch.json").read_text())
    assert ledger["status"] == "UNVERIFIED_or_physical_failure_no_further_stage"
    with pytest.raises(ValueError, match="duplicate"):
        runner.execute(args)


def test_empirical_failure_still_allows_one_fine_stage(tmp_path, monkeypatch, runner):
    monkeypatch.setattr(runner, "validate_managed_launch", lambda *a: {})
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    deadlines = []

    def execute(command, deadline):
        deadlines.append(deadline)
        out = Path(command[command.index("--out") + 1])
        runner.write_json(
            out / "report.json",
            {
                "physical_audit": {"passed": True},
                "empirical": {"electrical_gates_passed": False},
            },
        )
        return {"exit_code": 0, "status": "exited"}

    monkeypatch.setattr(runner, "run_process_with_deadline", execute)
    args = SimpleNamespace(
        prepared=tmp_path / "inputs", upload_receipt=tmp_path / "upload", out=tmp_path / "evidence"
    )
    assert runner.execute(args) == 0
    assert len(deadlines) == 2 and deadlines[0] == deadlines[1]
    ledger = json.loads((args.out / "launch.json").read_text())
    assert [v["mesh"] for v in ledger["stages"]] == [80, 120]


def test_deadline_race_and_kill_do_not_launch_retry(monkeypatch, runner):
    class Process:
        pid = 1234

        def __init__(self):
            self.calls = 0

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls < 3:
                raise subprocess.TimeoutExpired("fake", timeout)
            return -9

    process = Process()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(runner.time, "monotonic", lambda: 100)
    signals = []

    def vanished(pid, signal):
        signals.append(signal)
        raise ProcessLookupError

    monkeypatch.setattr(runner.os, "killpg", vanished)
    assert runner.run_process_with_deadline(["fake"], 110)["exit_code"] == 124
    assert len(signals) == 2 and process.calls == 3
    assert runner.run_process_with_deadline(["fake"], 99)["status"].endswith("before_stage")


def test_reproduction_allows_roundoff_but_rejects_changed_science(comparison):
    saved = {"passed": False, "threshold": 0.05, "identity": "abc", "missing": None}
    comparison.require_reproduction(saved, {**saved, "threshold": np.nextafter(0.05, 1.0).item()})
    for changed in (
        {**saved, "passed": True},
        {**saved, "identity": "xyz"},
        {**saved, "threshold": 0.05001},
        {**saved, "threshold": float("nan")},
        {**saved, "threshold": float("inf")},
        {**saved, "extra": 1},
    ):
        with pytest.raises(ValueError):
            comparison.require_reproduction(saved, changed)


def test_pinned_high_reference_and_unsupported_low_never_extrapolate(comparison):
    observed, high, profile, metadata = comparison.historical_inputs()
    assert len(observed) == 3436 and metadata["config"]["mesh_points"] == 80
    assert high["time_s"][0] == 0 and profile.charge_integral_ah(1.0003) > 0
    prepared = comparison.prepare(comparison.ROOT)
    low = {
        "time_s": np.array([0.0, 2.0]),
        "voltage_v": np.array([4.2, 4.1]),
        "temperature_k": np.array([298.0, 298.0]),
        "capacity_ah": np.array([0.0, 0.0001]),
    }
    result = comparison.rate_points(prepared, low)
    assert len(result["points"]) == 9
    for row in result["points"]:
        assert not row["both_models_supported"]
        assert "observed_low_minus_high_gap_v" in row
        assert "model_minus_observed_rate_gap_v" not in row
        assert not row["cases"]["low"]["model_supported"]


def test_saved_scalar_pipeline_recomputes_metrics_and_rejects_tampering(
    tmp_path, monkeypatch, runner, comparison
):
    from physical_fpv.experimental_low_rate import FIELDS, build, empirical_report, physical_audit

    prepared = comparison.prepare(comparison.ROOT)
    time = prepared.output_time_s
    arrays = {
        "time_s": time,
        "voltage_v": np.interp(time, [0, time[-1]], [4.18, 2.5]),
        "capacity_ah": prepared.profile.charge_integral_ah(time),
        "temperature_k": np.full(len(time), 298.15),
        "lithium_inventory_mol": np.ones(len(time)),
        "heating_w": np.zeros(len(time)),
        "cooling_w": np.zeros(len(time)),
        "heat_capacity_volumetric_j_k_m3": np.full(len(time), 1e6),
    }
    for field in FIELDS:
        for reduction in ["min"] if field == "electrolyte" else ["min", "max"]:
            arrays[f"{field}_{reduction}_mol_m3"] = np.full(len(time), 1000.0)
        arrays[f"{field}_finite_sum_mol_m3"] = np.full(len(time), 3000.0)
    evidence = tmp_path / "evidence"
    manifest = {
        "source_commit": "a" * 40,
        "run_id": "123",
        "planned_configurations": {},
        "runtime_versions": runner.runtime_versions(),
    }
    runner.write_json(tmp_path / "inputs/manifest.json", manifest)
    runner.write_json(
        tmp_path / "upload-receipt.json",
        {
            "manifest_sha256": runner.digest(tmp_path / "inputs/manifest.json"),
            "source_commit": "a" * 40,
            "run_id": "123",
        },
    )
    reports = {}
    for mesh in (80, 120):
        sim, outputs, metadata = build(prepared, mesh)
        final_state = np.asarray(sim.built_model.concatenated_initial_conditions.evaluate())
        del sim
        manifest["planned_configurations"][str(mesh)] = metadata
        directory = evidence / f"mesh{mesh}"
        directory.mkdir(parents=True)
        np.savez_compressed(directory / "scalar-arrays.npz", **arrays)
        np.save(directory / "final-state.npy", final_state, allow_pickle=False)
        audit = physical_audit(arrays, metadata, prepared)
        assert audit["passed"]
        report = {
            "arrays_sha256": runner.digest(directory / "scalar-arrays.npz"),
            "final_state_sha256": runner.digest(directory / "final-state.npy"),
            "output_receipt": {
                "requested_grid_preserved": True,
                "true_endpoint_preserved": True,
                "stored_full_history_values": 0,
                "last_state_shape": list(final_state.shape),
                "endpoint_scalar_checks": dict.fromkeys(outputs, True),
            },
            "config": metadata,
            "battery_dfns_solved": 1,
            "source_commit": "a" * 40,
            "source_sha256": runner.source_digests(),
            "parameter_fitting": False,
            "runtime_versions": runner.runtime_versions(),
            "physical_audit": audit,
            "empirical": empirical_report(prepared, arrays, "final time", audit),
        }
        runner.write_json(directory / "report.json", report)
        reports[mesh] = report
    monkeypatch.setattr(comparison, "verify_inputs", lambda path: manifest)
    # Analytic arrays test the pipeline; separate construction/toy tests exercise
    # native-state reevaluation. These arrays are not a solved battery trajectory.
    monkeypatch.setattr(
        comparison, "verify_endpoint", lambda sim, a, y, outputs: dict.fromkeys(outputs, True)
    )
    ledger = {
        "status": "two_stages_complete_scientific_verdict_pending",
        "shared_wall_limit_s": 1200,
        "worker_address_space_limit_bytes": 4_000_000_000,
        "maximum_battery_dfns": 2,
        "elapsed_s": 100.0,
        "source_commit": "a" * 40,
        "run_id": "123",
        "stages": [{"mesh": v, "exit_code": 0} for v in (80, 120)],
    }
    runner.write_json(evidence / "launch.json", ledger)
    result = comparison.run(evidence)
    assert not result["conditional_protocol_gates_passed"]
    assert not result["numerical"]["full_numerical_qualification_passed"]
    assert result["numerical"]["common_support_mesh_check_passed"]
    assert all(r["both_models_supported"] for r in result["rate_comparison"]["points"])
    assert result == json.loads((evidence / "comparison.json").read_text())
    reports[120]["empirical"]["voltage_rmse_v"] += 0.001
    runner.write_json(evidence / "mesh120/report.json", reports[120])
    with pytest.raises(ValueError, match="numeric evidence"):
        comparison.run(evidence)
    reports[120]["arrays_sha256"] = "0" * 64
    runner.write_json(evidence / "mesh120/report.json", reports[120])
    with pytest.raises(ValueError, match="identity mismatch"):
        comparison.run(evidence)
