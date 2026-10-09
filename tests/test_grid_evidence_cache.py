import importlib.util
import json
from copy import deepcopy
from pathlib import Path


def module():
    spec = importlib.util.spec_from_file_location(
        "grid_cache", Path("scripts/grid_evidence_cache.py")
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def evidence():
    saved = json.loads(Path("docs/benchmarks/grid120-verified-evidence.json").read_text())
    # Exercise cache logic without requiring future numerical code to stay frozen.
    saved["calculation_contract"] = module().calculation_contract(Path.cwd())
    return saved


def test_exact_verified_calculation_can_be_reused():
    assert module().reusable_evidence(Path.cwd(), evidence())


def test_changed_calculation_fingerprint_cannot_be_reused():
    altered = deepcopy(evidence())
    altered["calculation_contract"]["src/physical_fpv/core.py"] = "0" * 64
    assert not module().reusable_evidence(Path.cwd(), altered)


def test_failed_numerical_evidence_cannot_be_reused():
    altered = deepcopy(evidence())
    altered["comparison"]["voltage_max_difference_v"] = 0.02
    assert not module().reusable_evidence(Path.cwd(), altered)
