"""Verification of the battery selection sweep (battery_sweep.py) and mission endurance (mission.py)."""

import numpy as np
import pytest

from fpvsim.battery_sweep import family_params, recommend, run_sweep, scaled_battery, variant_build
from fpvsim.flightcontroller import load_fc_config
from fpvsim.mission import fly_mission, lap_table, repeated
from fpvsim.performance import evaluate
from fpvsim.pilot import MANEUVERS

from conftest import ROOT


def test_scaling_laws(reference_build):
    params = family_params(reference_build)
    v = params.nominal()
    same = scaled_battery(v, 1.0)
    for key, value in same.items():
        assert value == pytest.approx(v[key], rel=1e-12)
    double = scaled_battery(v, 2.0)
    overhead = v["battery_family.overhead_mass"]
    assert double["battery.capacity"] == pytest.approx(2 * v["battery.capacity"])
    assert double["battery.mass"] == pytest.approx(overhead + 2 * (v["battery.mass"] - overhead))
    assert double["battery.r0_cell"] == pytest.approx(v["battery.r0_cell"] / 2 ** v["battery_family.resistance_exponent"])
    assert double["battery.ha_hover"] == pytest.approx(v["battery.ha_hover"] * 2 ** (2 / 3))


def test_variant_keeps_the_bottom_face_and_moves_the_strap(reference_build):
    params = family_params(reference_build)
    big = variant_build(reference_build, 1.5, params)
    old = {p.name: p for p in reference_build.parts}
    new = {p.name: p for p in big.parts}
    b0, b1 = old["battery"], new["battery"]
    assert b1.shape.lx == pytest.approx(b0.shape.lx * 1.5 ** (1 / 3))
    # above the frame (z up is negative): the bottom face (largest z) stays
    assert b1.position[2] + b1.shape.lz / 2 == pytest.approx(b0.position[2] + b0.shape.lz / 2)
    grow = b1.shape.lz - b0.shape.lz
    assert new["battery_strap"].position[2] == pytest.approx(old["battery_strap"].position[2] - grow)
    assert np.allclose(new["camera"].position, old["camera"].position)


def test_sweep_at_the_base_capacity_is_the_design_report(reference_build):
    base_mah = reference_build.params["battery.capacity"].value / 3.6
    points = run_sweep(reference_build, [0.8 * base_mah, base_mah, 1.4 * base_mah], samples=20, seed=3)
    nominal = evaluate(reference_build.realize())
    mid = points[1]
    for key, value in nominal.items():
        if np.isfinite(value):
            assert mid.nominal[key] == pytest.approx(value, rel=1e-9, abs=1e-12), key
    # more capacity: longer hover, heavier, same draws in every point (paired)
    e = [p.nominal["endurance"] for p in points]
    m = [p.nominal["auw"] for p in points]
    assert e[0] < e[1] < e[2] and m[0] < m[1] < m[2]
    assert all(p.mc.inputs is points[0].mc.inputs for p in points)
    assert recommend(points) in points


def test_repeated_maneuver():
    base = MANEUVERS["freestyle"]
    plan = repeated(base, 3)
    assert plan.duration == pytest.approx(3 * base.duration)
    assert len(plan.segments) == 3 * len(base.segments)
    assert plan.segments[len(base.segments)].start == pytest.approx(base.segments[0].start + base.duration)


def test_short_mission_conserves_charge(reference_build):
    cfg = load_fc_config(ROOT / "data" / "fc" / "acro-5in-baseline.toml")
    cap = reference_build.params["battery.capacity"].value
    result = fly_mission(reference_build, cfg, overrides={"battery.capacity": 0.04 * cap}, max_laps=3)
    log = result.log
    assert result.reason in ("reserve_soc", "low_voltage")
    assert 0.0 < result.time < result.hover_endurance  # flown hard: shorter than hover
    used = (1.0 - log["soc"][-1]) * 0.04 * cap / 3.6
    assert log["mah"][-1] == pytest.approx(used, rel=5e-3)
    laps = lap_table(result, reference_build.battery_series)
    assert laps and laps[0]["mah"] > 0
