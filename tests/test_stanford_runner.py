import importlib.util
import json
from pathlib import Path

import pytest


def runner():
    spec = importlib.util.spec_from_file_location(
        "stanford_runner", "scripts/run_stanford_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_truncated_or_partial_report_is_not_completed_numerical_evidence(tmp_path):
    module = runner()
    path = tmp_path / "report.json"
    assert not module.complete_evidence_available(path)
    path.write_text('{"cases":')
    assert not module.complete_evidence_available(path)
    module.write_json(path, {"cases": {"80": {}}})
    assert not module.complete_evidence_available(path)


def test_failed_scientific_gate_is_still_a_completed_report(tmp_path):
    module = runner()
    path = tmp_path / "report.json"
    module.write_json(
        path,
        {
            "cases": {str(n): {"model": {"config": {"mesh_points": n}}} for n in (80, 120)},
            "spatial_numerical_check": {"passed": False},
            "inputs": {"source_sha256": {"fixture": "synthetic-test"}},
        },
    )
    assert module.complete_evidence_available(path)


def test_interrupted_replace_keeps_previous_json_intact(tmp_path, monkeypatch):
    module = runner()
    path = tmp_path / "progress.json"
    module.write_json(path, {"status": "old valid snapshot"})

    def interrupted(*args):
        raise OSError("synthetic interrupted replacement")

    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError):
        module.write_json(path, {"status": "new snapshot"})
    assert json.loads(path.read_text()) == {"status": "old valid snapshot"}
