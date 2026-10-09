"""Actual replay receipts stay distinct from rebased synthetic cache fixtures."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

CASES = {
    "k1": ("stanford_evidence_cache", "stanford-k1-current-source-20261009-evidence.json"),
    "thermal": ("grid_evidence_cache", "thermal-current-source-20261009-evidence.json"),
}


def load(case):
    script, filename = CASES[case]
    spec = importlib.util.spec_from_file_location(script, f"scripts/{script}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = json.loads((Path("docs/benchmarks") / filename).read_text())
    predicate = module.reusable_attempt if case == "k1" else module.reusable_evidence
    return module, receipt, predicate


@pytest.mark.parametrize("case", CASES)
def test_genuine_current_source_receipt_is_reusable_without_rebasing_hashes(case):
    module, receipt, predicate = load(case)
    assert receipt["commit_sha"] == "744794b02d44bcbfc702ad8e5c403782128d11b0"
    assert receipt["ci_run_id"] == 37887926852 and receipt["run_attempt"] == 1
    assert receipt["case"] == case and receipt["new_simulated_meshes"] == [120]
    assert receipt["external_exit"]["exit_code"] == 0
    assert receipt["supervisor_status"]["status"] == "completed"
    assert receipt["input_manifest"]["source_commit_sha"] == receipt["commit_sha"]
    key = "source_sha256" if case == "k1" else "calculation_contract"
    assert module.calculation_contract(Path.cwd()) == receipt[key]
    assert receipt["input_manifest"]["source_sha256"] == receipt[key]
    assert predicate(Path.cwd(), receipt)


@pytest.mark.parametrize("case", CASES)
def test_new_receipt_cannot_be_reused_with_changed_current_source_hash(case):
    _, receipt, predicate = load(case)
    key = "source_sha256" if case == "k1" else "calculation_contract"
    receipt[key]["src/physical_fpv/current_profile.py"] = "0" * 64
    assert not predicate(Path.cwd(), receipt)


def test_completed_k1_receipt_preserves_empirical_failure():
    module, receipt, predicate = load("k1")
    assert predicate(Path.cwd(), receipt)
    assert receipt["report"]["spatial_numerical_check"]["passed"]
    assert not receipt["report"]["electrical_pilot_gates_passed"]
    assert not receipt["report"]["cases"]["120"]["electrical_gates"]["voltage_rmse"]
    assert receipt["report"]["cases"]["120"]["voltage_rmse_v"] == pytest.approx(0.1914735217065252)
    missing = deepcopy(receipt)
    missing["report"] = None
    assert not module.reusable_attempt(Path.cwd(), missing)


def test_incomplete_or_failed_thermal_comparison_cannot_be_reused():
    _, receipt, predicate = load("thermal")
    missing = deepcopy(receipt)
    del missing["comparison"]
    with pytest.raises(KeyError):
        predicate(Path.cwd(), missing)
    receipt["comparison"]["passed"] = False
    assert not predicate(Path.cwd(), receipt)


def test_original_evidence_files_remain_byte_identical():
    expected = {
        "stanford-k1-v3-verified-evidence.json": (
            "0e51f42778c4b0b2c21064e3e10c4b7d2af86f5ef8d7690e1563c6c470d6e38b"
        ),
        "grid120-verified-evidence.json": (
            "b4a89cf81babee11414af2bbbbabdf9e600193ca0c5a3dd6999075f6c595d1f9"
        ),
    }
    for filename, digest in expected.items():
        assert (
            hashlib.sha256((Path("docs/benchmarks") / filename).read_bytes()).hexdigest() == digest
        )
