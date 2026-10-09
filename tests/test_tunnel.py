"""Verification of the virtual wind tunnel (tunnel.py) and the balance-data fit (tunnel_fit.py)."""

import math
import subprocess
import sys

import numpy as np
import pytest

from fpvsim.performance import hover_endurance, hover_point
from fpvsim.sysid import read_csv
from fpvsim.tunnel import BalanceNoise, Tunnel, balance_data, cruise_endurance, trim_curve, write_balance_csv
from fpvsim.tunnel_fit import fit_tunnel, frame_values

from conftest import REFERENCE_BUILD, ROOT


@pytest.fixture(scope="module")
def aircraft(reference_build):
    return reference_build.realize()


@pytest.fixture(scope="module")
def tunnel(aircraft):
    return Tunnel(aircraft)


def drag_areas(ac):
    return [ac.extras.cda[k] + sum(a[k] for _, a in ac.extras.drag_points) for k in range(3)]


def test_props_removed_drag_is_the_drag_area(tunnel, aircraft):
    S = drag_areas(aircraft)
    q = 0.5 * tunnel.rho * 15.0**2
    r0 = tunnel.reading(15.0, 0.0, 0.0, "off")
    r90 = tunnel.reading(15.0, math.pi / 2, 0.0, "off")
    assert r0.drag == pytest.approx(q * S[0], rel=1e-9)
    assert r90.drag == pytest.approx(q * S[2], rel=1e-9)
    assert r0.lift == pytest.approx(0.0, abs=1e-9)
    # quadratic drag: the drag area does not depend on speed
    assert tunnel.reading(30.0, 0.3, 0.0, "off").drag / 30.0**2 == pytest.approx(tunnel.reading(10.0, 0.3, 0.0, "off").drag / 10.0**2)
    # stopped props add drag
    assert tunnel.reading(15.0, 0.0, 0.0, "stopped").drag > r0.drag


def test_pitching_moment_is_r_cross_f(tunnel, aircraft):
    """Props removed at alpha = 0: M_y = sum over drag points of z_i F_x,i."""
    cg = aircraft.mass_props.cg
    r = tunnel.reading(20.0, 0.0, 0.0, "off")
    q = 0.5 * tunnel.rho * 20.0**2
    expected = sum((p[2] - cg[2]) * (-q * a[0]) for p, a in
                   [(aircraft.extras.cda_center, aircraft.extras.cda)] + list(aircraft.extras.drag_points))
    assert r.moment[1] == pytest.approx(expected, rel=1e-6, abs=1e-12)


def test_trim_balances_forces_and_matches_hover(tunnel, aircraft):
    tp = tunnel.trim(0.0)
    hp = hover_point(aircraft)
    assert tp.tilt == pytest.approx(0.0, abs=1e-9)
    assert tp.collective == pytest.approx(hp.duty, rel=2e-3)
    assert tp.p_bus == pytest.approx(hp.v_bus * hp.i_bus, rel=2e-3)
    curve = trim_curve(tunnel, np.arange(0.0, 30.0001, 5.0))
    tilts = [p.tilt for p in curve.points]
    assert (np.diff(tilts) > 0).all()  # more tilt for more speed
    for p in curve.points:  # the drag budget: thrust's horizontal part balances airframe and rotor drag
        assert p.body_drag >= 0.0 and p.rotor_drag >= -1e-9
        assert abs(p.roll_residual) < 2e-3 and abs(p.yaw_residual) < 2e-3  # N m


def test_power_curve_and_top_speed(tunnel):
    curve = trim_curve(tunnel)
    v_e, v_r = curve.best_speeds()
    assert 0.0 < v_e < v_r < curve.v_max  # minimum power before minimum power per speed
    top = curve.v_max_point
    assert max(top.duties) == pytest.approx(1.0, abs=5e-3)  # at full throttle
    assert tunnel.trim(curve.v_max + 1.0, top.x) is None or not tunnel.trim(curve.v_max + 1.0, top.x).feasible


def test_cruise_endurance_at_zero_speed_is_hover_endurance(tunnel, aircraft):
    e = cruise_endurance(tunnel, 0.0)
    h = hover_endurance(aircraft)
    assert e.reason == h.reason
    assert e.time == pytest.approx(h.endurance, rel=5e-3)


def test_fit_recovers_known_values(tunnel, aircraft, tmp_path):
    S = drag_areas(aircraft)
    exact = balance_data(tunnel, seed=1, noise=BalanceNoise(0.0, 0.0, 0.0))
    write_balance_csv(exact, tmp_path / "exact.csv")
    fit = fit_tunnel(read_csv(tmp_path / "exact.csv"), aircraft)
    for i, ax in enumerate("xyz"):
        assert fit.cda[ax].value == pytest.approx(S[i], rel=1e-4)
    assert fit.flap_fraction.value == pytest.approx(aircraft.extras.flap_fraction, abs=1e-4)
    fv = frame_values(fit, aircraft)
    assert np.allclose(fv["drag_center"], aircraft.extras.cda_center, atol=2e-5)
    # with load-cell noise the estimates stay within three standard errors
    noisy = balance_data(tunnel, seed=4)
    write_balance_csv(noisy, tmp_path / "noisy.csv")
    fit = fit_tunnel(read_csv(tmp_path / "noisy.csv"), aircraft)
    for i, ax in enumerate("xyz"):
        assert abs(fit.cda[ax].value - S[i]) < 3.0 * fit.cda[ax].u + 1e-9
    assert abs(fit.flap_fraction.value - aircraft.extras.flap_fraction) < 3.0 * fit.flap_fraction.u


def test_cli_round_trip(tmp_path):
    csv = tmp_path / "balance.csv"
    out = tmp_path / "fit"
    cmd = [sys.executable, "-m", "fpvsim.cli"]
    subprocess.run(cmd + ["tunnel", str(REFERENCE_BUILD), "--synthetic", str(csv), "--synthetic-only"], check=True, cwd=ROOT,
                   capture_output=True)
    res = subprocess.run(cmd + ["fit-tunnel", str(csv), "--build", str(REFERENCE_BUILD), "--out", str(out)], check=True,
                         cwd=ROOT, capture_output=True, text=True)
    assert "flap_fraction" in res.stdout
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "drag_center = { value = [" in report and (out / "fit.png").exists()
