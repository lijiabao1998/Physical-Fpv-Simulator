"""Verification of the wind, turbulence and ground-effect models (wind.py)."""

import math
from dataclasses import replace

import numpy as np
import pytest
from scipy.signal import welch

from fpvsim.dynamics import Outputs, QuadModel
from fpvsim.performance import hover_point
from fpvsim.wind import FT, Dryden, WindSettings, dryden_scales, ground_effect


@pytest.fixture(scope="module")
def aircraft(reference_build):
    return reference_build.realize()


def test_log_profile():
    w = WindSettings(speed=8.0, ref_height=10.0, roughness=0.03)
    assert w.mean_speed(10.0) == pytest.approx(8.0)
    assert w.mean_speed(0.03) == 0.0 and w.mean_speed(0.01) == 0.0
    h = np.array([0.5, 1, 2, 5, 10, 20, 50])
    u = np.array([w.mean_speed(x) for x in h])
    assert (np.diff(u) > 0).all()
    # equal ratios of height give equal increments (logarithmic)
    assert w.mean_speed(20.0) - w.mean_speed(10.0) == pytest.approx(w.mean_speed(2.0) - w.mean_speed(1.0))
    # wind from the west (270 deg) blows towards the east
    n, e, d = WindSettings(speed=5.0, direction_from=math.radians(270.0)).mean_ned(10.0)
    assert n == pytest.approx(0.0, abs=1e-12) and e == pytest.approx(5.0) and d == 0.0


def test_dryden_scales_match_the_handbook_low_altitude_form():
    h_ft = 100.0
    L_u, L_v, L_w, s_u, s_v, s_w = dryden_scales(h_ft * FT, 10.0)
    a = 0.177 + 0.000823 * h_ft
    assert L_w == pytest.approx(h_ft * FT)
    assert L_u == L_v == pytest.approx(h_ft / a**1.2 * FT)
    assert s_w == pytest.approx(1.0)
    assert s_u == s_v == pytest.approx(1.0 / a**0.4)
    assert dryden_scales(0.5, 10.0) == dryden_scales(10 * FT, 10.0)  # clamped below 10 ft


def test_turbulence_variance_and_spectrum():
    """Long record at fixed height and airspeed: standard deviations equal sigma,
    and the spectra follow the Dryden forms."""
    wind = WindSettings(speed=8.0, turbulence_rate=200.0)
    gen = Dryden(wind, np.random.default_rng(3))
    height, V = 20.0, 10.0
    n = 200_000  # 1000 s
    out = np.array([gen.step(height, V) for _ in range(n)])
    to_n, to_e = wind.to_direction
    u = out[:, 0] * to_n + out[:, 1] * to_e
    v = -out[:, 0] * to_e + out[:, 1] * to_n
    w = out[:, 2]
    L_u, L_v, L_w, s_u, s_v, s_w = dryden_scales(height, wind.w20)
    # the u and v scale lengths are long (~120 m, 12 s at 10 m/s): 1000 s holds only ~40 independent
    # samples, so their sample std scatters by ~6 % (1 sigma)
    assert np.std(u) == pytest.approx(s_u, rel=0.15)
    assert np.std(v) == pytest.approx(s_v, rel=0.15)
    assert np.std(w) == pytest.approx(s_w, rel=0.04)
    fs = wind.turbulence_rate
    for x, sigma, L, kind in ((w, s_w, L_w, "vw"), (u, s_u, L_u, "u")):
        f, p = welch(x, fs=fs, nperseg=8192)
        omega = 2 * np.pi * f
        tau = L / V
        if kind == "u":
            model = sigma**2 * 2 * tau / (1 + (tau * omega) ** 2)
        else:
            model = sigma**2 * tau * (1 + 3 * (tau * omega) ** 2) / (1 + (tau * omega) ** 2) ** 2
        # welch gives a one-sided density per Hz: 2 pi times the per-rad/s two-sided density, times 2 / (2 pi)
        model_hz = 2 * model
        band = (f > 0.05) & (f < 5.0)
        ratio = p[band] / model_hz[band]
        assert np.median(ratio) == pytest.approx(1.0, rel=0.15), kind


def test_calm_air_has_no_turbulence():
    gen = Dryden(WindSettings(), np.random.default_rng(1))
    assert gen.step(10.0, 5.0) == (0.0, 0.0, 0.0)
    gen = Dryden(WindSettings(speed=6.0, turbulence=False), np.random.default_rng(1))
    assert gen.step(10.0, 5.0) == (0.0, 0.0, 0.0)


def test_ground_effect_ratio():
    assert ground_effect(1.0) == pytest.approx(1.0 / (1.0 - 1.0 / 16.0))
    assert ground_effect(10.0) == pytest.approx(1.0, abs=1e-3)
    assert ground_effect(0.1) == ground_effect(0.5) == pytest.approx(4.0 / 3.0)  # held below z = R / 2
    z = np.linspace(0.5, 5.0, 50)
    assert (np.diff([ground_effect(x) for x in z]) < 0).all()


def test_ground_effect_in_the_flight_model(aircraft):
    m = QuadModel(aircraft, aircraft.extras)
    off = QuadModel(aircraft, aircraft.extras, ground_effect=False)
    hp = hover_point(aircraft)
    o = Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)
    R = aircraft.powertrain.prop.radius
    hubs_z = max(h[2] for h in m.hub)  # hub height relative to the CG (body z down)
    s = m.initial_state(position=(0, 0, -(R + hubs_z)), omega=hp.omega)  # lowest hub one radius above ground
    d_on = m.derivative(s, [hp.duty] * 4, out=o)
    d_off = off.derivative(s, [hp.duty] * 4)
    ratio = ground_effect(1.0)
    assert o.ground_effect == pytest.approx(ratio, rel=1e-6)
    thrust_off = (aircraft.env.g - d_off[5]) * m.mass
    thrust_on = (aircraft.env.g - d_on[5]) * m.mass
    assert thrust_on == pytest.approx(ratio * thrust_off, rel=1e-3)
    # far from the ground, nothing changes
    s_high = m.initial_state(position=(0, 0, -20.0), omega=hp.omega)
    assert m.derivative(s_high, [hp.duty] * 4) == off.derivative(s_high, [hp.duty] * 4)


def test_wind_moves_a_level_quad_downwind(aircraft, reference_build):
    """A quad with fixed level attitude in a steady wind accelerates downwind (drag)."""
    m = QuadModel(aircraft, replace(aircraft.extras))
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -20.0), omega=hp.omega)
    d = m.derivative(s, [hp.duty] * 4, wind=(0.0, 6.0, 0.0))
    assert d[4] > 0.05  # east
    assert abs(d[3]) < 0.2 * d[4]


def test_windy_flight_logs_wind_and_drifts_downwind(reference_build):
    from conftest import ROOT
    from fpvsim.flightcontroller import load_fc_config
    from fpvsim.pilot import MANEUVERS
    from fpvsim.sim import SimSettings, simulate

    cfg = load_fc_config(ROOT / "data" / "fc" / "acro-5in-baseline.toml")
    wind = WindSettings(speed=8.0, direction_from=math.radians(270.0))  # from the west
    log = simulate(reference_build, cfg, MANEUVERS["hover"], SimSettings(log_rate=250, wind=wind), duration=2.0)
    expected = wind.mean_speed(20.0)
    assert np.mean(log["wind_e"]) == pytest.approx(expected, rel=0.3)  # mean plus turbulence
    assert np.std(log["wind_d"]) > 0.05  # turbulence present
    assert log["airspeed"][0] == pytest.approx(math.sqrt(log["wind_n"][0] ** 2 + log["wind_e"][0] ** 2 + log["wind_d"][0] ** 2))
    assert log["vel_e"][-1] > 0.3  # blown east
    assert log.meta["wind"]["speed_m_s"] == 8.0
    calm = simulate(reference_build, cfg, MANEUVERS["hover"], SimSettings(log_rate=250), duration=0.2)
    assert not calm["wind_n"].any() and not calm["wind_e"].any()
