"""Battery thermal model, Arrhenius resistance, ageing and design points."""

import math

import numpy as np
import pytest

from fpvsim.battery import R_GAS, Battery, BatteryState
from fpvsim.design import DesignError, load_build
from fpvsim.performance import full_throttle_burst

from conftest import REFERENCE_BUILD

OCV_SOC = np.array([0.0, 0.5, 1.0])
OCV_V = np.array([3.3, 3.8, 4.2])


def _battery(**kw):
    base = dict(series=6, parallel=1, capacity=1.3 * 3600, r0_cell=0.004, r1_cell=0.0, tau1=20.0,
                ocv_soc=OCV_SOC, ocv_cell=OCV_V, max_current=130.0)
    base.update(kw)
    return Battery(**base)


def test_thermal_node_matches_the_analytic_solution():
    """Constant current and conductance, temperature-independent R: exponential approach to steady state."""
    b = _battery(heat_capacity=215.0, ha_hover=0.5, ha_ref=0.5)
    current, ambient, t0 = 30.0, 288.15, 298.15
    q = current**2 * b.r0
    t_ss = ambient + q / 0.5
    state = BatteryState(1.0, 0.0, t0)
    for _ in range(600):  # 600 s in 1 s steps
        state = state.step(b, current, 1.0, ambient=ambient)
    expected = t_ss + (t0 - t_ss) * math.exp(-0.5 * 600 / 215.0)
    assert state.temperature == pytest.approx(expected, rel=1e-9)


def test_idle_pack_relaxes_to_ambient_and_cooling_grows_with_air_speed():
    b = _battery(heat_capacity=215.0, ha_hover=0.3, ha_ref=0.6, ha_speed=10.0)
    state = BatteryState(1.0, 0.0, 320.0)
    for _ in range(20000):
        state = state.step(b, 0.0, 1.0, ambient=290.0)
    assert state.temperature == pytest.approx(290.0, abs=1e-6)
    assert b.conductance(0.0) == pytest.approx(0.3)
    assert b.conductance(10.0) == pytest.approx(0.6)
    assert b.conductance(40.0) == pytest.approx(0.3 + 0.3 * 2.0)  # laminar: grows with sqrt(v)


def test_arrhenius_resistance():
    ea = 20e3
    b = _battery(activation_energy=ea, r_ref_temperature=298.15)
    assert b.resistance_factor(298.15) == pytest.approx(1.0)
    ratio = b.resistance_factor(273.15)
    assert ratio == pytest.approx(math.exp(ea / R_GAS * (1 / 273.15 - 1 / 298.15)))
    assert 1.8 < ratio < 2.2  # 20 kJ/mol roughly doubles R at 0 degC
    assert b.r0_at(273.15) == pytest.approx(b.r0 * ratio)


def test_ageing_scales_capacity_and_resistance():
    build = load_build(REFERENCE_BUILD)
    new, old = build.realize(), build.realize({"env.battery_cycles": 100.0})
    fade = build.params["battery.capacity_fade"].value
    growth = build.params["battery.resistance_growth"].value
    assert old.battery.capacity == pytest.approx(new.battery.capacity * (1 - fade))
    assert old.battery.r0 == pytest.approx(new.battery.r0 * (1 + growth))
    assert old.battery.cycles == 100.0 and new.battery.cycles == 0.0


def test_design_points_from_the_spec():
    build = load_build(REFERENCE_BUILD)
    points = {d.id: d for d in build.spec.design_points}
    assert set(points) >= {"winter", "aged", "worst"}
    assert points["winter"].overrides["env.battery_temperature"] == pytest.approx(278.15)
    assert points["aged"].overrides == {"env.battery_cycles": 200.0}
    cold = build.realize(points["winter"].overrides)
    assert cold.env.temperature == pytest.approx(273.15)


def test_design_point_without_pack_temperature_assumes_soaked_pack(tmp_path):
    spec = (REFERENCE_BUILD.parent.parent / "specs" / "freestyle-5in-6s.toml").read_text(encoding="utf-8")
    spec += '\n[[design_points]]\nid = "frost"\ntemperature = { value = -10, unit = "degC", source = "nominal" }\n'
    path = tmp_path / "spec.toml"
    path.write_text(spec, encoding="utf-8")
    build_text = REFERENCE_BUILD.read_text(encoding="utf-8").replace('"../', f'"{REFERENCE_BUILD.parent}/../')
    build_text = build_text.replace(f'spec = "{REFERENCE_BUILD.parent}/../specs/freestyle-5in-6s.toml"', f'spec = "{path}"')
    build_path = tmp_path / "build.toml"
    build_path.write_text(build_text, encoding="utf-8")
    frost = {d.id: d for d in load_build(build_path).spec.design_points}["frost"]
    assert frost.overrides["env.battery_temperature"] == pytest.approx(263.15)
    path.write_text(spec + 'humidity = 3\n', encoding="utf-8")
    with pytest.raises(DesignError, match="unknown keys"):
        load_build(build_path)


def test_full_throttle_burst_limits():
    build = load_build(REFERENCE_BUILD)
    ac = build.realize()
    burst = full_throttle_burst(ac)
    assert burst.reason == "battery_temperature"
    assert burst.end_temperature == pytest.approx(ac.battery.max_temperature, abs=0.5)
    times = [row[0] for row in burst.trace]
    assert times[-1] >= burst.duration > 5.0
    # a cold, aged pack sags below the burst limit at once
    worst = {d.id: d for d in build.spec.design_points}["worst"]
    cold = full_throttle_burst(build.realize(worst.overrides))
    assert cold.duration == 0.0 and cold.reason == "burst_cell_voltage"


def test_dynamics_battery_heating_matches_the_battery_model():
    from fpvsim.dynamics import QuadModel

    ac = load_build(REFERENCE_BUILD).realize()
    model = QuadModel(ac, ac.extras)
    state = model.initial_state(position=(0, 0, -50.0), omega=1500.0, temperature=300.0)
    state[14 + model.n] = 0.2  # some polarisation voltage
    out_rate = model.derivative(state, [0.5] * model.n)[15 + model.n]
    from fpvsim.dynamics import Outputs

    out = Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)
    model.derivative(state, [0.5] * model.n, out=out)
    b = ac.battery
    expected = (b.heat(out.i_bus, 0.2, 300.0) - b.conductance(0.0) * (300.0 - ac.env.temperature)) / b.heat_capacity
    assert out_rate == pytest.approx(expected, rel=1e-9)
