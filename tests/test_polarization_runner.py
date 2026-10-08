import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def runner_module():
    spec = importlib.util.spec_from_file_location(
        "polarization_runner", "scripts/diagnose_polarization.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_polarization_protocol_and_reference():
    runner = runner_module()
    assert (
        hashlib.sha256(Path("docs/polarization-protocol.md").read_bytes()).hexdigest()
        == runner.PROTOCOL_SHA256
    )
    assert (
        hashlib.sha256(
            Path("docs/benchmarks/thermal-grid120-reference.csv").read_bytes()
        ).hexdigest()
        == runner.REFERENCE_SHA256
    )


def test_supervised_worker_receives_exact_budget_and_output_directory():
    command = runner_module().worker_command(SimpleNamespace(timeout=37, out=Path("results/fake")))
    assert "--worker" in command
    assert command[command.index("--timeout") + 1] == "37"
    assert command[command.index("--out") + 1] == "results/fake"
