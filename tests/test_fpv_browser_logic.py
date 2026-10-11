"""Mocked input scheduling checks; these are not browser or hardware validation."""

import copy
import shutil
import subprocess
from pathlib import Path

import pytest

from physical_fpv.fpv.__main__ import replay
from physical_fpv.fpv.simulator import Simulator


def test_actual_ui_script_with_mocked_dom_and_gamepad():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable: mocked DOM/Gamepad checks NOT RUN")
    script = Path(__file__).with_name("fpv_browser_logic.cjs")
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "8 mocked DOM/Gamepad checks passed" in result.stdout


def test_snapshot_mutation_cannot_change_simulator_or_old_replay():
    sim = Simulator()
    sim.advance({"armed": True, "throttle": 0.5}, 0.05)
    expected = copy.deepcopy(sim.telemetry())
    snapshot = sim.telemetry()
    bundle = sim.replay_bundle()
    original_bundle = copy.deepcopy(bundle)

    snapshot["controls"]["armed"] = False
    snapshot["duties"][0] = 999
    snapshot["scene"][0]["low"][0] = 999
    snapshot["flight"]["position_m"][0] = 999
    snapshot["powertrain"]["soc"][0][0] = 999
    assert sim.telemetry() == expected

    sim.advance({"armed": False}, 0)
    sim.advance({}, 0.05)
    assert bundle == original_bundle
    assert replay(bundle)["passed"]
