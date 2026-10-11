import copy
import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from physical_fpv.fpv.server import make_server
from physical_fpv.fpv.simulator import Simulator


def test_end_to_end_hover_replay_and_control():
    first = Simulator()
    second = Simulator()
    first.flight.state.position_m[2] = 2
    second.flight.state.position_m[2] = 2
    commands = [{"armed": True, "throttle": first.hover_duty, "pitch": 0.1}] * 20
    for command in commands:
        a = first.advance(command, 0.05)
        b = second.advance(command, 0.05)
        assert a == b
    assert a["flight"]["position_m"][0] > 0
    assert a["powertrain"]["current_a"] > 0
    assert min(np.array(a["powertrain"]["soc"]).flat) < 0.9
    assert a["flight"]["quaternion_wxyz"] != [1, 0, 0, 0]
    bundle = first.replay_bundle()
    assert json.loads(json.dumps(bundle))["sha256"] == bundle["sha256"]
    assert len(bundle["inputs"]) == 20
    assert abs(a["powertrain"]["power_balance_error_w"]) < 1e-8


def test_disarm_reset_and_transactional_reject():
    s = Simulator()
    s.advance({"armed": True, "throttle": 0.6}, 0.1)
    after = s.advance({"armed": False}, 0.05)
    assert after["duties"] == [0, 0, 0, 0]
    assert max(after["powertrain"]["thrust_n"]) == 0
    before = copy.deepcopy(s.telemetry())
    with pytest.raises(ValueError):
        s.advance({"throttle": float("nan")})
    assert s.telemetry() == before
    s.__init__()
    assert s.telemetry()["flight"]["time_s"] == 0
    assert s.controls["armed"] is False


def test_material_mass_reaches_dynamics():
    a = Simulator(frame_density_kg_m3=2700)
    b = Simulator(frame_density_kg_m3=5400)
    assert b.flight.config.mass_kg > a.flight.config.mass_kg
    assert b.hover_duty > a.hover_duty
    assert "supplied reference" in a.material_source


def test_http_controls_reset_and_reject():
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def req(path, body=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            base + path, data=None if body is None else json.dumps(body).encode(), headers=headers
        )
        return json.load(urllib.request.urlopen(request))

    try:
        assert req("/state")["controls"]["armed"] is False
        result = req("/step", {"controls": {"armed": True, "throttle": 0.5}, "duration_s": 0.05})
        assert result["flight"]["time_s"] == pytest.approx(0.05)
        with pytest.raises(urllib.error.HTTPError):
            req("/step", {"controls": {"armed": "yes"}})
        with pytest.raises(urllib.error.HTTPError):
            req("/reset", {}, origin="https://example.com")
        assert req("/reset", {})["flight"]["time_s"] == 0
        with urllib.request.urlopen(base + "/") as r:
            html = r.read().decode()
            assert "Gamepad API" in html and "SYNTHETIC BASELINE" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_export_roundtrip_and_tamper_rejection():
    from physical_fpv.fpv.__main__ import replay

    s = Simulator()
    for _ in range(5):
        s.advance({"armed": True, "throttle": 0.5}, 0.05)
    bundle = json.loads(json.dumps(s.replay_bundle()))
    assert replay(bundle)["passed"]
    bundle["inputs"][0]["controls"]["throttle"] = 0.6
    with pytest.raises(ValueError, match="checksum"):
        replay(bundle)


def test_whole_chain_time_refinement_and_initial_disarm():
    outputs = []
    for dt in [0.01, 0.005, 0.0025]:
        s = Simulator(substep_s=dt)
        assert s.telemetry()["powertrain"]["current_a"] == 0
        for _ in range(40):
            s.advance({"armed": True, "throttle": 0.46, "pitch": 0.1}, 0.05)
        outputs.append(np.array(s.telemetry()["flight"]["position_m"]))
    coarse = np.max(abs(outputs[0] - outputs[1]))
    fine = np.max(abs(outputs[1] - outputs[2]))
    assert fine < 0.002  # fixed local pair gate in metres, not measured accuracy
    assert 1.8 < coarse / fine < 2.2  # whole coupled forcing is first-order, not RK4 order


def test_zero_time_disarm_preserves_states_and_replay():
    from physical_fpv.fpv.__main__ import replay

    s = Simulator()
    s.advance({"armed": True, "throttle": 0.5}, 0.1)
    before = s.telemetry()
    after = s.advance({"armed": False, "throttle": 0}, 0)
    assert after["flight"] == before["flight"]
    assert after["powertrain"]["soc"] == before["powertrain"]["soc"]
    assert after["powertrain"]["cell_temperature_k"] == before["powertrain"]["cell_temperature_k"]
    assert after["powertrain"]["current_a"] == 0
    assert max(after["powertrain"]["thrust_n"]) == 0
    assert not after["controls"]["armed"]
    assert replay(s.replay_bundle())["passed"]


def test_exported_snapshots_do_not_alias_live_state():
    from physical_fpv.fpv.__main__ import replay

    s = Simulator()
    s.advance({"armed": True, "throttle": 0.5}, 0.1)
    bundle = s.replay_bundle()
    telemetry = s.telemetry()
    s.advance({"armed": False}, 0.05)
    assert replay(bundle)["passed"]
    telemetry["controls"]["armed"] = True
    telemetry["duties"][0] = 1
    telemetry["scene"][0]["low"][0] = 999
    assert s.controls["armed"] is False
    assert s.last_duties == [0] * 4
    assert s.telemetry()["scene"][0]["low"][0] == 8
