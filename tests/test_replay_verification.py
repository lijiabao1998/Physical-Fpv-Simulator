"""Tiny synthetic archives exercise verification, never simulate physical cells."""

import hashlib
import json
import socket
import urllib.request
import zipfile
from pathlib import Path

import pytest

from physical_fpv import cli
from physical_fpv.replay_verification import WORKFLOW, verify_replay


def encoded(value):
    return json.dumps(value, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def zip_bytes(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, content in files.items():
            output.writestr(name, content)
    return path.read_bytes()


def bundle(tmp_path, case="k1", *, reported_rmse=0.1, interior_observation=False):
    # Explicitly synthetic data: a 0.1 V offset fails RMSE but passes maximum error.
    curve = b"time_s,voltage_v,capacity_ah,temperature_k\n0,4,0,300\n10,2.5,1,300\n"
    model = {
        "physical_audit": {"passed": True},
        "voltage_cutoff_reached": True,
        "config": {"mesh_points": 120},
    }
    coarse_model = {**model, "config": {"mesh_points": 80}}
    comparison = {
        "voltage_max_difference_v": 0.0,
        "temperature_max_difference_k": 0.0,
        "capacity_relative_difference": 0.0,
        "passed": True,
    }
    source = {
        WORKFLOW: b"synthetic workflow, never executed",
        "src/example.py": b"# synthetic source\n",
    }
    if case == "thermal":
        source.update(
            {
                "docs/benchmarks/thermal-grid80-reference.csv": curve,
                "docs/benchmarks/thermal-representative-grid80.json": encoded(coarse_model),
            }
        )
    manifest = {
        "case": case,
        "source_commit_sha": "a" * 40,
        "fixture_kind": "synthetic_unit_test",
        "config": {"mesh_points": 120},
        "source_sha256": {"src/example.py": digest(source["src/example.py"])},
        "staged_files_sha256": {name: digest(raw) for name, raw in source.items()},
    }
    inputs = {
        "manifest.json": encoded(manifest),
        **{"files/" + name: raw for name, raw in source.items()},
    }
    identity = {"run_id": "123", "source_commit": "a" * 40, "case": case}
    launch = dict(identity)
    exit_receipt = {**identity, "exit_code": 0}
    status = {"status": "completed"}
    prefix = f"current-source-replay/{case}/"
    outputs = {
        f"current-source-replay/{case}-inputs/manifest.json": inputs["manifest.json"],
        prefix + "launch.json": encoded(launch),
        prefix + "external-exit.json": encoded(exit_receipt),
        prefix + "status.json": encoded(status),
    }
    receipt = {
        "case": case,
        "commit_sha": "a" * 40,
        "ci_run_id": 123,
        "run_attempt": 1,
        "workflow_path": WORKFLOW,
        "workflow_sha256": digest(source[WORKFLOW]),
        "input_manifest": manifest,
        "input_manifest_sha256": digest(inputs["manifest.json"]),
        "launch_receipt": launch,
        "external_exit": exit_receipt,
        "supervisor_status": status,
    }
    if case == "k1":
        fine = {
            "model": model,
            "common_observed_interval_s": [0, 10],
            "voltage_rmse_v": reported_rmse,
            "voltage_max_absolute_error_v": 0.1,
            "empirical_thresholds": {"voltage_rmse_v": 0.05, "voltage_max_error_v": 0.3},
            "electrical_gates": {"voltage_rmse": False, "voltage_max": True},
            "electrical_gates_passed": False,
        }
        report = {
            "inputs": {"source_sha256": manifest["source_sha256"], "source_commit_sha": "a" * 40},
            "cases": {"80": {"model": coarse_model}, "120": fine},
            "spatial_numerical_check": comparison,
            "electrical_pilot_gates_passed": False,
        }
        observed = (
            b"commanded_step_time_s,voltage_v\n0,3.9\n"
            + (b"5,3.15\n" if interior_observation else b"")
            + b"10,2.4\n"
        )
        outputs.update(
            {
                prefix + "report.json": encoded(report),
                prefix + "input.json": encoded(report["inputs"]),
                prefix + "mesh80-timeseries.csv": curve,
                prefix + "mesh120-timeseries.csv": curve,
                prefix + "mesh120-residuals.csv": (
                    b"time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v\n"
                    b"0,3.9,4,0.1\n10,2.4,2.5,0.1\n"
                ),
                "source-inspection/observed-discharge.csv": observed,
            }
        )
        receipt.update({"source_sha256": manifest["source_sha256"], "report": report})
    else:
        outputs.update(
            {
                prefix + "comparison.json": encoded(comparison),
                prefix + "input.json": encoded(manifest["config"]),
                prefix + "metadata.json": encoded(model),
                prefix + "timeseries.csv": curve,
            }
        )
        receipt.update(
            {
                "calculation_contract": manifest["source_sha256"],
                "comparison": comparison,
                "metadata": model,
            }
        )
    input_path, output_path, receipt_path = (
        tmp_path / n for n in ["inputs.zip", "outputs.zip", "receipt.json"]
    )
    raw_inputs = zip_bytes(input_path, inputs)
    raw_outputs = zip_bytes(output_path, outputs)
    receipt.update(
        {
            "input_zip_sha256": digest(raw_inputs),
            "input_zip_bytes": len(raw_inputs),
            "artifact_zip_sha256": digest(raw_outputs),
            "artifact_zip_bytes": len(raw_outputs),
            "artifact_files": {name: digest(raw) for name, raw in outputs.items()},
        }
    )
    receipt_path.write_bytes(encoded(receipt))
    return receipt_path, input_path, output_path


@pytest.mark.parametrize("case,empirical", [("k1", False), ("thermal", None)])
def test_offline_verifier_separates_integrity_numerics_and_empirical(
    case, empirical, tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline verification must never solve or access the network")

    monkeypatch.setattr(cli, "simulate", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    result = verify_replay(*bundle(tmp_path, case))
    assert result["integrity"] == "verified_against_receipt"
    assert result["numerical"]["passed"] is True
    assert result["empirical"]["passed"] is empirical
    assert result["new_solver_runs"] == result["new_downloads"] == 0
    assert "no signature" in result["trust_anchor"]


def test_self_consistent_report_hashes_cannot_hide_wrong_recomputed_metric(tmp_path):
    with pytest.raises(ValueError, match="voltage RMSE"):
        verify_replay(*bundle(tmp_path, reported_rmse=0.01))


def test_missing_interior_observation_cannot_be_silently_cropped(tmp_path):
    with pytest.raises(ValueError, match="complete union"):
        verify_replay(*bundle(tmp_path, interior_observation=True))


def test_truncated_archive_is_not_a_scientific_failure(tmp_path):
    receipt, inputs, outputs = bundle(tmp_path)
    outputs.write_bytes(outputs.read_bytes()[:-10])
    with pytest.raises(ValueError, match="ZIP byte count"):
        verify_replay(receipt, inputs, outputs)


@pytest.mark.parametrize("member", ["../escape", "/absolute", "a/../b", "a\\b", "a//b"])
def test_unsafe_archive_names_rejected_even_with_rebased_outer_hash(tmp_path, member):
    receipt, inputs, outputs = bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    with zipfile.ZipFile(outputs, "a") as archive:
        archive.writestr(member, b"no extraction")
    value["artifact_zip_sha256"] = digest(outputs.read_bytes())
    value["artifact_zip_bytes"] = outputs.stat().st_size
    receipt.write_bytes(encoded(value))
    with pytest.raises(ValueError, match="Unsafe or ambiguous"):
        verify_replay(receipt, inputs, outputs)


def test_duplicate_zip_member_rejected(tmp_path):
    receipt, inputs, outputs = bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(outputs, "a") as archive:
            archive.writestr("current-source-replay/k1/status.json", b"{}")
    value["artifact_zip_sha256"] = digest(outputs.read_bytes())
    value["artifact_zip_bytes"] = outputs.stat().st_size
    receipt.write_bytes(encoded(value))
    with pytest.raises(ValueError, match="Duplicate or symlink"):
        verify_replay(receipt, inputs, outputs)


def test_duplicate_json_key_is_rejected(tmp_path):
    receipt, inputs, outputs = bundle(tmp_path)
    receipt.write_text('{"case":"thermal","case":"k1"}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        verify_replay(receipt, inputs, outputs)


@pytest.mark.parametrize("case", ["k1", "thermal"])
def test_cli_gate_exit_code_and_report_are_unambiguous(tmp_path, capsys, case):
    receipt, inputs, outputs = bundle(tmp_path, case)
    args = [
        "verify-replay",
        "--receipt",
        str(receipt),
        "--inputs",
        str(inputs),
        "--outputs",
        str(outputs),
    ]
    assert cli.main(args + ["--require-numerical-pass"]) == 0
    assert json.loads(capsys.readouterr().out)["numerical"]["passed"] is True
    assert cli.main(args + ["--require-empirical-pass"]) == 2
    assert json.loads(capsys.readouterr().out)["empirical"]["passed"] is not True
    with pytest.raises(SystemExit) as error:
        cli.main(args + ["--out", str(inputs)])
    assert error.value.code == 1


@pytest.mark.data
@pytest.mark.parametrize("case,name", [("k1", "stanford-k1"), ("thermal", "thermal")])
def test_actual_saved_replay_archives_without_fetching(case, name, monkeypatch):
    root = Path("results/current-source-replay-receipts")
    inputs = root / f"current-source-{case}-inputs-37887926852.zip"
    outputs = root / f"current-source-{case}-evidence-37887926852.zip"
    if not inputs.exists() or not outputs.exists():
        pytest.skip("Saved artifact ZIPs absent; never download them for a unit test")

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved-artifact verification must stay offline")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(cli, "simulate", forbidden)
    result = verify_replay(
        Path(f"docs/benchmarks/{name}-current-source-20261009-evidence.json"), inputs, outputs
    )
    assert result["numerical"]["passed"]
    assert result["empirical"]["passed"] is not True
    assert result == json.loads(
        Path(f"docs/benchmarks/offline-replay-verification-{case}.json").read_text()
    )
