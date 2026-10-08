import importlib.util
import json
from copy import deepcopy
from pathlib import Path


def module():
    spec = importlib.util.spec_from_file_location(
        "stanford_cache", "scripts/stanford_evidence_cache.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def fixture():
    contract = module().calculation_contract(Path.cwd())
    return {
        "ci_run_id": 1,
        "commit_sha": "1" * 40,
        "artifact_zip_sha256": "2" * 64,
        "source_sha256": contract,
        "supervisor_status": {
            "status": "completed",
            "missing_numerical_stage_is_unverified": False,
        },
        "report": {
            "cases": {str(n): {"model": {"config": {"mesh_points": n}}} for n in (80, 120)},
            "spatial_numerical_check": {"passed": False},
            "electrical_pilot_gates_passed": False,
            "inputs": {"source_sha256": contract, "source_commit_sha": "1" * 40},
        },
    }


def test_completed_failed_science_is_preserved_without_claiming_new_solve(tmp_path):
    cache, evidence = module(), fixture()
    assert cache.reusable_attempt(Path.cwd(), evidence)
    cache.export_reused(Path.cwd(), evidence, tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    assert not report["electrical_pilot_gates_passed"]
    assert not report["spatial_numerical_check"]["passed"]
    assert not json.loads((tmp_path / "status.json").read_text())["new_simulation_run"]


def test_changed_forcing_implementation_invalidates_recorded_attempt():
    evidence = deepcopy(fixture())
    evidence["source_sha256"]["src/physical_fpv/current_profile.py"] = "0" * 64
    assert not module().reusable_attempt(Path.cwd(), evidence)


def test_budget_failure_stays_unverified_and_does_not_create_final_report(tmp_path):
    evidence = fixture()
    evidence.update(
        {
            "report": None,
            "partial_case_reports": {"80": {"synthetic": True}},
            "supervisor_status": {
                "status": "budget_exhausted",
                "missing_numerical_stage_is_unverified": True,
            },
        }
    )
    module().export_reused(Path.cwd(), evidence, tmp_path)
    assert not (tmp_path / "report.json").exists()
    assert (tmp_path / "mesh80-report.json").exists()
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["status"] == "budget_exhausted"
    assert status["missing_numerical_stage_is_unverified"]


def test_unverifiable_provenance_or_incomplete_success_is_not_reused():
    evidence = fixture()
    evidence["commit_sha"] = "unknown"
    assert not module().reusable_attempt(Path.cwd(), evidence)
    evidence = fixture()
    evidence["report"]["cases"].pop("120")
    assert not module().reusable_attempt(Path.cwd(), evidence)
