import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_worker_receives_requested_grid_and_budget():
    path = Path("scripts/verify_thermal_grid.py")
    spec = importlib.util.spec_from_file_location("grid_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = module.worker_command(
        SimpleNamespace(mesh=120, timeout=1200, out=Path("results/test"))
    )
    assert command[command.index("--mesh") + 1] == "120"
    assert command[command.index("--timeout") + 1] == "1200"
    assert command[command.index("--out") + 1] == "results/test"
