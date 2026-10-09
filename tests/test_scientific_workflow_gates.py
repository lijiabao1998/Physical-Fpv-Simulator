"""PR cache misses must stay visibly unverified without launching a solver."""

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "filename,fallback_count", [("thermal-grid.yml", 1), ("stanford-pilot.yml", 2)]
)
def test_expensive_fallback_requires_explicit_dispatch(filename, fallback_count):
    text = (Path(".github/workflows") / filename).read_text()
    blocks = text.split("      - name: ")[1:]
    fallback = [b for b in blocks if "if: steps.saved.outputs.reuse != 'true'" in b]
    manual = [b for b in fallback if "&& github.event_name == 'workflow_dispatch'" in b]
    fail_closed = [b for b in fallback if "&& github.event_name != 'workflow_dispatch'" in b]
    assert len(manual) == fallback_count
    assert len(fail_closed) == 1
    assert "exit 1" in fail_closed[0]
    assert "UNVERIFIED" in fail_closed[0]
    assert "--timeout 1200" in text
    assert "timeout-minutes: 25" in text
    assert "continue-on-error" not in text


def load_script(name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_historical_thermal_evidence_cannot_validate_changed_evaluator():
    import json

    saved = json.loads(Path("docs/benchmarks/grid120-verified-evidence.json").read_text())
    assert not load_script("grid_evidence_cache").reusable_evidence(Path.cwd(), saved)


def test_historical_k1_evidence_cannot_validate_changed_evaluator():
    import json

    saved = json.loads(Path("docs/benchmarks/stanford-k1-v3-verified-evidence.json").read_text())
    assert not load_script("stanford_evidence_cache").reusable_attempt(Path.cwd(), saved)


def test_live_k2_summarizer_still_rejects_changed_calculation(tmp_path):
    import json
    import zipfile

    with zipfile.ZipFile("docs/benchmarks/stanford-k2-recovery-evidence.zip") as archive:
        inputs = json.loads(archive.read("stanford-k2-recovery/input.json"))
    (tmp_path / "input.json").write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="Frozen calculation changed"):
        load_script("run_stanford_k2").summarize(tmp_path)
