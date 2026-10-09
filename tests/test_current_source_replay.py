"""Preflight staging and singleton resource controls must not run science."""

import importlib.util
import json
import urllib.request
from pathlib import Path

import pybamm
import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "replay_prepare", "scripts/prepare_current_source_replay.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_thermal_preflight_authenticates_and_stages_without_solver_or_network(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No solver or acquisition in preflight")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setenv("PHYSICAL_FPV_RESEARCH_COMMIT", "a" * 40)
    out = tmp_path / "inputs"
    result = module().prepare("thermal", out)
    assert result["config"]["mesh_points"] == 120
    assert result["new_scientific_solves_planned"] == 1
    assert result["wall_limit_s"] == 1200
    assert result["worker_address_space_limit_bytes"] == 4_000_000_000
    assert result == json.loads((out / "manifest.json").read_text())
    assert all(
        str(path) in result["staged_files_sha256"] for path in Path("src/physical_fpv").glob("*.py")
    )
    import hashlib

    for path, digest in result["staged_files_sha256"].items():
        assert hashlib.sha256((out / "files" / path).read_bytes()).hexdigest() == digest
    with pytest.raises(ValueError, match="Never overwrite"):
        module().prepare("thermal", out)


def test_unreviewed_calculation_delta_is_rejected():
    m = module()
    key = "src/physical_fpv/current_profile.py"
    old = {key: "old", "core.py": "same"}
    new = {key: m.NEW_PROFILE_SHA256, "core.py": "same"}
    m.verify_implementation_delta(old, new)
    with pytest.raises(ValueError, match="only the reviewed"):
        m.verify_implementation_delta(old, {**new, "core.py": "changed"})
    with pytest.raises(ValueError, match="Unreviewed current"):
        m.verify_implementation_delta(old, {**new, key: "changed"})
    with pytest.raises(ValueError, match="file set"):
        m.verify_implementation_delta(old, {key: m.NEW_PROFILE_SHA256})


def test_launch_has_one_shot_sequential_and_preupload_guards():
    text = Path(".github/workflows/current-source-replay-20261009.yml").read_text()
    assert "pull_request:" not in text and "workflow_dispatch:" not in text
    assert "branches: [battery/research-core-v1]" in text
    assert "paths: [.github/workflows/current-source-replay-20261009.yml]" in text
    assert 'test "$GITHUB_RUN_ATTEMPT" = "1"' in text
    assert "data['total_count'] == 1" in text
    assert "max-parallel: 1" in text and "cancel-in-progress: false" in text
    assert "case: [k1, thermal]" in text and "timeout-minutes: 25" in text
    assert "ulimit -v 3906250 && timeout" in text and "1200s" in text
    assert "REPLAY_JOB_STARTED_AT" in text and "-le 180" in text
    assert text.index("Persist all authenticated inputs") < text.index(
        "Exactly one scientific solve"
    )
    assert "retention-days: 90" in text and "external-exit.json" in text
    assert "include-hidden-files: true" in text
    assert "continue-on-error" not in text
