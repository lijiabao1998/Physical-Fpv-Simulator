"""The generic prop against cited public test data, and the Reynolds-number correction.

The validation file (data/validation/props-5in-tri.toml) holds individually
cited thrust-stand points; these tests check that every point is cited, that
the coefficients are computed from the raw readings correctly, that the prop
component file carries exactly what the fit to those points gives, and that
the model lies within the class's uncertainty of every data group.
"""

import math
import tomllib

import numpy as np
import pytest

from fpvsim.atmosphere import Environment, viscosity
from fpvsim.bemt import coefficient_curves
from fpvsim.performance import full_throttle_point, hover_point
from fpvsim.prop import ReynoldsCorrection
from fpvsim.prop_validation import (calibrate_airfoil, class_shape, consistency, fit_class, load_validation, residuals,
                                    static_coefficients)
from fpvsim.units import G0

from conftest import ROOT

DATA = ROOT / "data" / "validation" / "props-5in-tri.toml"


@pytest.fixture(scope="module")
def vset():
    return load_validation(DATA)


@pytest.fixture(scope="module")
def fit(vset):
    return fit_class(vset)


@pytest.fixture(scope="module")
def aircraft(reference_build):
    return reference_build.realize()


def test_every_point_is_individually_cited(vset):
    for s in vset.series:
        assert s.url.startswith("https://") and s.locator and s.source and s.tested
        assert all(p.at for p in s.points)
        assert len(s.points) <= 8  # a few points per source, not whole tables (methodology section 7)
    for sh in vset.shapes:
        assert sh.url.startswith("https://") and sh.static_url.startswith("https://") and sh.locator
        assert len(sh.J) <= 10
    raw = tomllib.loads(DATA.read_text(encoding="utf-8"))
    for e in raw["excluded"]:
        assert e["what"] and e["reason"] and e["url"].startswith("https://")


def test_coefficients_of_a_cited_point(vset):
    """Tyto test wek, first step: 1.08065 kgf and 0.110713 N m at 25845 rpm (5.0 in, rho 1.225)."""
    p = next(p for p in vset.points if p.series == "tyto-wek")
    n, D = 25845 / 60, 5.0 * 0.0254
    assert p.thrust == pytest.approx(1.08065 * G0)
    assert p.ct == pytest.approx(1.08065 * G0 / (1.225 * n**2 * D**4), rel=1e-12)
    assert p.cp == pytest.approx(2 * math.pi * 0.110713 / (1.225 * n**2 * D**5), rel=1e-12)
    assert p.ct == pytest.approx(0.1792, abs=5e-5) and p.fm == pytest.approx(0.654, abs=5e-4)
    assert p.re == pytest.approx(2 * math.pi * n * 0.75 * D / 2 * 0.010 / (viscosity(288.15) / 1.225), rel=1e-12)


def test_torque_below_the_cutoff_is_left_out(vset):
    wek = next(s for s in vset.series if s.id == "tyto-wek")
    assert wek.torque_points_dropped == 1
    assert [p.torque is None for p in wek.points] == [False, False, False, True]
    assert all(p.torque is None for s in vset.series if s.id.startswith("mqtb") for p in s.points)


def test_class_fit(fit):
    levels = [t.level for g, t in fit.ct_groups.items() if g in fit.level_groups]
    assert min(levels) < fit.ct_level < max(levels)
    assert 0.0 < fit.ct_exponent < fit.fm_exponent  # FM rises with Re faster than Ct: Cp falls slightly
    assert fit.ct_level_u_rel > 0.05 and fit.fm_level_u_rel > 0.05  # at least the rig-to-rig term
    assert fit.re_min < fit.re_ref < fit.re_max


def test_prop_file_carries_the_fit(reference_build, vset, fit):
    checks = consistency(reference_build, fit, vset)
    assert len(checks) == 16
    assert all(c.ok for c in checks), [(c.name, c.fitted, c.in_file) for c in checks if not c.ok]


def test_model_lies_within_the_class_band_of_every_group(reference_build, vset, fit):
    res = residuals(vset, reference_build.realize().powertrain.prop)
    assert set(res) == {s.group for s in vset.series}
    for group, r in res.items():
        assert abs(r["ct"]) < 2 * fit.ct_level_u_rel, group
        if r["n_fm"]:
            assert abs(r["fm"]) < 2 * fit.fm_level_u_rel, group


def test_advance_ratio_shape(vset):
    x = np.linspace(0.0, 0.9, 19)
    g_t, g_p, s_t, s_p = class_shape(vset, x)
    assert g_t[0] == 1.0 and g_p[0] == 1.0
    assert np.all(np.diff(g_t[2:]) < 0) and np.all(np.diff(g_p[2:]) < 0)
    assert s_t.max() < 0.1 and s_p.max() < 0.1  # the two props agree within 10 % of static over x <= 0.9
    with pytest.raises(ValueError):
        class_shape(vset, np.array([0.0, 2.0]))


def test_bemt_cannot_match_the_static_level_and_the_shape_together(reference_build, vset, fit):
    """Why the axial curves come from data: with its polar fitted to the static
    level, BEMT still overpredicts Cp in forward flow by far more than the data spread."""
    geom, foil = reference_build.prop_blade
    cal = calibrate_airfoil(geom, foil, fit.ct_level, fit.fm_level)
    ct, cp = static_coefficients(geom, cal)
    assert ct == pytest.approx(fit.ct_level, rel=1e-6) and cp == pytest.approx(fit.cp_level, rel=1e-6)
    pd = 4.3 / 5.1
    curves = coefficient_curves(geom, cal, np.array([0.0, 0.5 * pd]))
    _, g_p, _, s_p = class_shape(vset, np.array([0.5]))
    assert curves.cp[1] / curves.cp[0] > g_p[0] + 3 * s_p[0] + 0.1


# --------------------------------------------------------------- Reynolds correction


def test_reynolds_factors_and_limits():
    rc = ReynoldsCorrection(chord75=0.01, re_ref=6e4, re_min=2.4e4, re_max=1e5, ct_exponent=0.1, fm_exponent=0.24)
    assert rc.factors(6e4) == (1.0, 1.0)
    assert rc.cp_exponent == pytest.approx(1.5 * 0.1 - 0.24)
    f_t, f_p = rc.factors(3e4)
    assert f_t == pytest.approx(0.5**0.1) and f_p == pytest.approx(0.5 ** (0.15 - 0.24))
    assert f_t**1.5 / f_p == pytest.approx(0.5**0.24)  # the figure of merit follows its own exponent
    assert rc.factors(1e4) == rc.factors(2.4e4) and rc.factors(5e5) == rc.factors(1e5)  # held at the data range
    with pytest.raises(ValueError):
        ReynoldsCorrection(chord75=0.01, re_ref=1e5, re_min=2e4, re_max=6e4, ct_exponent=0.1, fm_exponent=0.2)


def test_thrust_inversion_across_the_reynolds_limits(aircraft):
    prop, env = aircraft.powertrain.prop, aircraft.env
    rho, nu = env.rho, env.kinematic_viscosity
    for rpm in (3000, 7000, 9000, 20000, 34000, 45000):  # below, inside and above the fitted range
        omega = rpm * 2 * math.pi / 60
        thrust = prop.thrust_static(omega, rho, nu)
        assert prop.omega_for_thrust(thrust, rho, nu) == pytest.approx(omega, rel=1e-12)


def test_powertrain_closes_with_the_reynolds_correction(aircraft):
    """for_thrust (closed form) and at_duty (motor solve with the speed-dependent load) agree."""
    pt, env = aircraft.powertrain, aircraft.env
    for thrust in (1.0, 4.0, 12.0):
        op = pt.for_thrust(thrust, 25.0, 0.03, env)
        back = pt.at_duty(op.duty, 25.0, 0.03, env)
        assert back.thrust == pytest.approx(thrust, rel=1e-8)
        assert back.omega == pytest.approx(op.omega, rel=1e-8)


def test_hover_is_less_efficient_than_full_throttle(aircraft):
    prop, nu = aircraft.powertrain.prop, aircraft.env.kinematic_viscosity
    hp, ft = hover_point(aircraft), full_throttle_point(aircraft)
    fm_hover, fm_full = prop.figure_of_merit(hp.omega, nu), prop.figure_of_merit(ft.omega, nu)
    assert fm_hover < 0.9 * fm_full
    assert 0.45 < fm_hover < 0.56  # NeuroBEM stand at the same Re75 reads 0.48-0.50
    assert prop.figure_of_merit() == pytest.approx(0.583, abs=0.002)  # at Re_ref


def test_thin_air_lowers_the_reynolds_number(aircraft):
    prop = aircraft.powertrain.prop
    omega = 1500.0
    sea, high = Environment.isa(0.0), Environment.isa(3000.0)
    assert high.kinematic_viscosity == pytest.approx(1.869e-5, rel=0.005)  # ISA table at 3000 m
    assert prop.figure_of_merit(omega, high.kinematic_viscosity) < prop.figure_of_merit(omega, sea.kinematic_viscosity)
