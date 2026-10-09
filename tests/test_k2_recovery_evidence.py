"""Verify recorded k2 evidence, never launch a numerical model."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


def verifier():
    spec = importlib.util.spec_from_file_location(
        "k2_verify", "scripts/verify_stanford_k2_recovery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_evidence(root):
    (root / "docs/benchmarks").mkdir(parents=True)
    for name in ("stanford-k2-recovery-evidence.zip", "stanford-k2-recovery-summary.json"):
        shutil.copyfile(Path("docs/benchmarks") / name, root / "docs/benchmarks" / name)


def test_recorded_recovery_has_numeric_pass_empirical_fail_without_solve(monkeypatch):
    import physical_fpv.core

    def forbidden(*args, **kwargs):
        raise AssertionError("Evidence verification must never simulate")

    monkeypatch.setattr(physical_fpv.core, "simulate", forbidden)
    result = verifier().verify()
    assert result["verified"] and result["numerical_pass"]
    assert not result["empirical_pass"] and not result["new_simulation_run"]


def test_changed_archive_is_rejected(tmp_path):
    copy_evidence(tmp_path)
    path = tmp_path / "docs/benchmarks/stanford-k2-recovery-evidence.zip"
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="artifact bytes"):
        verifier().verify(tmp_path)


def test_original_attempt_cannot_be_promoted(tmp_path):
    copy_evidence(tmp_path)
    path = tmp_path / "docs/benchmarks/stanford-k2-recovery-summary.json"
    data = json.loads(path.read_text())
    data["original_attempt_status"] = "completed"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provenance"):
        verifier().verify(tmp_path)


def test_historical_array_scope_does_not_certify_changed_current_implementation():
    result = verifier().verify()
    assert (
        result["verification_scope"]
        == "authenticated historical arrays and original source commit only"
    )
    assert result["current_calculation_compatible"] is False
    assert result["current_source_mismatches"] == ["src/physical_fpv/current_profile.py"]
    assert result["source_commit_sha"] == verifier().SOURCE_COMMIT


def test_historical_array_analysis_dependencies_still_fail_closed():
    recorded = {"src/physical_fpv/current_profile.py": "old", "src/physical_fpv/core.py": "same"}
    current = {**recorded, "src/physical_fpv/current_profile.py": "new"}
    assert verifier().historical_dependency_check(recorded, current) == [
        "src/physical_fpv/current_profile.py"
    ]
    current["src/physical_fpv/core.py"] = "tampered"
    with pytest.raises(ValueError, match="dependencies changed"):
        verifier().historical_dependency_check(recorded, current)
