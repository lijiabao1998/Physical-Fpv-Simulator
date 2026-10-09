"""Verification of the oblique-flow rotor model (rotor_ff.py) and its use in the flight dynamics."""

import math
import shutil
from dataclasses import replace

import numpy as np
import pytest

from fpvsim import rotor_ff as rf
from fpvsim.design import DesignError, load_build
from fpvsim.dynamics import Outputs, QuadModel
from fpvsim.performance import hover_point

from conftest import REFERENCE_BUILD, ROOT


@pytest.fixture(scope="module")
def aircraft(reference_build):
    return reference_build.realize()


@pytest.fixture(scope="module")
def tables(reference_build):
    return rf.rotor_tables(*reference_build.prop_blade)


def lam_index(tables, lam):
    return int(np.argmin(np.abs(tables.lam - lam)))


# ------------------------------------------------------------ induced velocity


def test_axial_induced_velocity_is_continuous_and_momentum_outside_vrs():
    x = np.array([-2.0 - 1e-9, -2.0, -2.0 + 1e-9, -1e-9, 0.0, 1e-9])
    k = rf.axial_induced(x)
    assert k[0] == pytest.approx(k[2], abs=1e-4)  # meets the windmill brake state at -2
    assert k[3] == pytest.approx(k[5], abs=1e-6)  # meets momentum theory at hover
    assert k[4] == pytest.approx(1.0)
    climb = np.array([0.5, 1.0, 3.0])
    assert np.allclose(rf.axial_induced(climb), -climb / 2 + np.sqrt(climb**2 / 4 + 1))
    windmill = np.array([-2.5, -4.0])
    assert np.allclose(rf.axial_induced(windmill), -windmill / 2 - np.sqrt(windmill**2 / 4 - 1))
    # in the vortex ring state the induced velocity exceeds the hover value, and V_c + v_i = 0 near
    # V_c = -1.71 v_h (ideal autorotation, Leishman 2006 ch. 2); -1.73 with the continuity correction
    assert rf.axial_induced(np.array(-1.0)) > 1.5
    for x_auto in (-1.70, -1.76):
        assert np.sign(x_auto + rf.axial_induced(np.array(x_auto))) == (1.0 if x_auto > -1.73 else -1.0)


def test_glauert_in_level_forward_flight():
    """Level flight (V_c = 0): k^4 + y^2 k^2 = 1."""
    y = np.array([0.0, 0.5, 1.0, 2.0, 4.0])
    k = rf.induced_velocity(np.zeros_like(y), y, np.ones_like(y))
    exact = np.sqrt((-y**2 + np.sqrt(y**4 + 4)) / 2)
    assert np.allclose(k, exact, rtol=1e-9)


def test_induced_velocity_is_continuous_across_the_vrs_region():
    x = np.linspace(-4.0, 1.0, 1001)[:, None]
    y = np.linspace(0.0, 2.0, 801)[None, :]
    v = rf.induced_velocity(x, y, np.ones(1))
    # the windmill branch has an infinite slope at x = -2 (momentum theory); otherwise no jumps
    away = np.abs(x[1:] - (-2.0)) > 0.05
    assert np.abs(np.diff(v, axis=0))[away[:, 0]].max() < 0.02
    assert np.abs(np.diff(v, axis=1)).max() < 0.02
    # inside the fold region the vortex-ring value is used in full, far outside it Glauert's
    assert rf.induced_velocity(np.array(-1.0), np.array(0.1), np.array(1.0)) == pytest.approx(rf.axial_induced(np.array(-1.0)))
    assert rf.induced_velocity(np.array(-1.0), np.array(2.0), np.array(1.0)) == pytest.approx(rf.glauert(np.array(-1.0), np.array(2.0)))


# ---------------------------------------------------------------------- tables


def test_tables_converged_and_symmetric_in_axial_flow(tables):
    assert tables.converged.all()
    for name in ("ch", "cy", "cmx", "cmy", "chf"):
        assert np.abs(getattr(tables, name)[0]).max() < 1e-12, name
    # mu = 0 at hover: the blade-element C_T on rho A V_ref^2 equals the rotorcraft one
    assert 0.02 < tables.ct[0, lam_index(tables, 0.0)] < 0.03


def test_rotor_drag_positive_and_translational_lift(tables, aircraft):
    j0 = lam_index(tables, 0.0)
    band = slice(lam_index(tables, -0.1), lam_index(tables, 0.1) + 1)
    assert (tables.ch[1:, band] > 0.0).all()  # H opposes the edgewise motion
    assert (tables.chf[1:26, band] > 0.0).all()  # flapping tilts the disk back (up to mu = 0.5)
    assert (tables.cmx[1:26, j0] < 0.0).all()  # advancing side (-e2 for CCW) lifts
    # translational lift: at constant rpm, level, thrust grows with forward speed
    rotor = rf.anchored_rotor(aircraft.powertrain.prop, 0.5)
    thrust = [rotor.loads((v, 0.0, 0.0), 900.0, 1.0, 1.2)["thrust"] for v in (0.0, 5.0, 10.0, 15.0)]
    assert (np.diff(thrust) > 0.0).all()


def test_rotor_drag_below_momentum_bound(aircraft):
    """The momentum-theory rotor drag rho A v_i V_e (all incoming in-plane momentum
    turned with the wake) is an upper bound; the blade-element H force, with or
    without flapping, is below it and of the same order at small advance ratio."""
    prop = aircraft.powertrain.prop
    rigid, free = rf.anchored_rotor(prop, 0.0), rf.anchored_rotor(prop, 1.0)
    rho, omega = 1.2, 900.0
    thrust = rigid.loads((0.0, 0.0, 0.0), omega, 1.0, rho)["thrust"]
    v_i = math.sqrt(thrust / (2 * rho * prop.disk_area))
    for v in (2.0, 5.0):  # mu = 0.03, 0.09
        bound = rho * prop.disk_area * v_i * v
        h_rigid = rigid.loads((v, 0.0, 0.0), omega, 1.0, rho)["h_force"]
        h_free = free.loads((v, 0.0, 0.0), omega, 1.0, rho)["h_force"]
        assert 0.05 * bound < h_rigid < h_free < bound


def test_anchoring_reproduces_axial_curves(aircraft):
    prop = aircraft.powertrain.prop
    rotor = rf.anchored_rotor(prop, 0.5)
    lam = rotor.tables.lam
    lam_rot = lam / np.sqrt(np.clip(1 - lam**2, 1e-12, None))
    sel = (lam_rot >= 0.0) & (lam_rot <= rf.AXIAL_ANCHOR_MAX + 1e-9)
    assert sel.sum() >= 8
    J = np.pi * lam_rot[sel]
    s2 = 1 - lam[sel] ** 2
    ct_axial = prop.ct_scale * np.interp(J, prop.curves.J, prop.curves.ct) * 4 / np.pi**3 * s2
    cp_axial = prop.cp_scale * np.interp(J, prop.curves.J, prop.curves.cp) * 4 / np.pi**4 * s2
    assert np.allclose(rotor.coefficients["ct"][0, sel], ct_axial, rtol=1e-12)
    assert np.allclose(rotor.coefficients["cq"][0, sel], cp_axial, rtol=1e-12)
    # in physical terms: axial climb at a grid point gives the axial curve's thrust and torque
    omega, rho = 2000.0, 1.2
    k = int(np.nonzero(sel)[0][4])
    v_c = lam_rot[k] * omega * prop.radius
    loads = rotor.loads((0.0, 0.0, -v_c), omega, 1.0, rho)
    n = omega / (2 * np.pi)
    J_k = v_c / (n * prop.diameter)
    assert loads["thrust"] == pytest.approx(prop.ct_scale * prop.curves.ct_at(J_k) * rho * n**2 * prop.diameter**4, rel=1e-9)
    assert loads["torque"] == pytest.approx(prop.cp_scale * prop.curves.cp_at(J_k) * rho * n**2 * prop.diameter**5 / (2 * np.pi),
                                            rel=1e-9)
    # scaling the axial curves scales the anchored tables
    scaled = rf.anchored_rotor(replace(prop, ct_scale=1.1 * prop.ct_scale), 0.5)
    assert np.allclose(scaled.coefficients["ct"], 1.1 * rotor.coefficients["ct"], rtol=1e-12)


def test_idle_and_stopped_props(aircraft):
    """Low rpm at high air speed: the total-speed normalisation keeps the loads
    physical. A windmilling prop in a fast climb brakes the aircraft, roughly
    like the blades' flat-plate drag; a stopped prop has a small edgewise drag."""
    prop = aircraft.powertrain.prop
    rotor = rf.anchored_rotor(prop, 0.5)
    rho = 1.2
    coast = rotor.loads((0.0, 0.0, -40.0), 244.0, 1.0, rho)  # punch-out coast at idle
    assert coast["lambda_rotor"] > 2.0
    blade_area = 3 * 0.011 * 0.055  # three blades, about 11 mm mean chord over 55 mm
    flat_plate = 0.5 * rho * 40.0**2 * blade_area
    assert -2.0 * flat_plate < coast["thrust"] < -0.2 * flat_plate
    stopped = rotor.loads((20.0, 0.0, 0.0), 0.0, 1.0, rho)
    assert 0.0 < stopped["h_force"] < 0.5 * rho * 20.0**2 * blade_area
    assert math.isinf(stopped["mu_rotor"])


def test_flap_fraction_blends_the_limits(aircraft):
    prop = aircraft.powertrain.prop
    rigid, free = rf.anchored_rotor(prop, 0.0), rf.anchored_rotor(prop, 1.0)
    half = rf.anchored_rotor(prop, 0.5)
    assert np.allclose(half.coefficients["ch"], 0.5 * (rigid.coefficients["ch"] + free.coefficients["ch"]))
    assert np.abs(free.coefficients["cmx"]).max() == 0.0 and np.abs(free.coefficients["cmy"]).max() == 0.0
    band = (rigid.tables.lam >= -0.1) & (rigid.tables.lam <= 0.1)  # flapping back in normal flight
    assert (free.coefficients["ch"][1:21, band] > rigid.coefficients["ch"][1:21, band]).all()  # mu up to 0.4


# -------------------------------------------------------------- flight model


def test_mirror_spin_directions(aircraft):
    rotor = rf.anchored_rotor(aircraft.powertrain.prop, 0.3)
    omega, rho = 2500.0, aircraft.env.rho
    v_hub = (8.0, 3.0, 1.0)
    ccw = rotor.loads(v_hub, omega, -1.0, rho)
    cw = rotor.loads(v_hub, omega, 1.0, rho)
    assert cw["thrust"] == pytest.approx(ccw["thrust"])
    assert cw["h_force"] == pytest.approx(ccw["h_force"])
    assert cw["torque"] == pytest.approx(ccw["torque"])
    assert cw["side_force"] == pytest.approx(-ccw["side_force"])
    # the in-plane force opposes the motion
    fx, fy, _ = ccw["force"]
    assert fx * v_hub[0] + fy * v_hub[1] < 0.0
    # rolling moment (about the direction of motion) flips, pitching moment stays
    e1 = np.array(v_hub[:2]) / math.hypot(*v_hub[:2])
    e2 = np.array([e1[1], -e1[0]])
    m_ccw, m_cw = np.array(ccw["moment"][:2]), np.array(cw["moment"][:2])
    assert m_cw @ e1 == pytest.approx(-(m_ccw @ e1))
    assert m_cw @ e2 == pytest.approx(m_ccw @ e2)


def test_quad_in_forward_flight_sums_rotor_loads(aircraft):
    """With body rates zero every hub sees the body velocity, so the model's force
    equals the sum of the single-rotor loads (frame drag off, thrust interference on)."""
    m = QuadModel(aircraft, replace(aircraft.extras, cda=(0.0, 0.0, 0.0), drag_points=()))
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    s[3], s[5] = 12.0, 1.5  # forward and descending
    d = m.derivative(s, [hp.duty] * 4)
    total = np.zeros(3)
    for sp in m.spin:
        f = np.array(m.rotor.loads((12.0, 0.0, 1.5), hp.omega, sp, aircraft.env.rho)["force"])
        f[2] *= m.interference
        total += f
    accel = total / m.mass + np.array([0.0, 0.0, aircraft.env.g])
    assert np.allclose(d[3:6], accel, rtol=1e-9, atol=1e-9)


def test_frozen_coefficients_match_fresh_lookup(aircraft):
    m = QuadModel(aircraft, aircraft.extras)
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    s[3], s[10], s[11] = 10.0, 0.5, -0.3
    fresh = m.derivative(s, [hp.duty] * 4)
    held = m.derivative(s, [hp.duty] * 4, fresh=False)
    assert held == fresh
    # an RK4 step with held coefficients stays close to one with a lookup at every stage
    dt = 1.0 / 8000

    def step_fresh(state):
        k1 = m.derivative(state, [hp.duty] * 4)
        k2 = m.derivative([a + 0.5 * dt * b for a, b in zip(state, k1)], [hp.duty] * 4)
        k3 = m.derivative([a + 0.5 * dt * b for a, b in zip(state, k2)], [hp.duty] * 4)
        k4 = m.derivative([a + dt * b for a, b in zip(state, k3)], [hp.duty] * 4)
        return [a + dt / 6 * (b + 2 * c + 2 * e + f) for a, b, c, e, f in zip(state, k1, k2, k3, k4)]

    a, b = list(s), list(s)
    for _ in range(800):  # 0.1 s
        a = m.step(a, [hp.duty] * 4, dt)
        b = step_fresh(b)
    assert np.allclose(a[3:6], b[3:6], atol=1e-4)
    assert np.allclose(a[10:13], b[10:13], atol=1e-3)


def test_validity_outputs(aircraft):
    m = QuadModel(aircraft, aircraft.extras)
    hp = hover_point(aircraft)
    o = Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    s[5] = 0.8 * m.v_induced_hover  # straight down, in the vortex ring region
    m.derivative(s, [hp.duty] * 4, out=o)
    assert o.descent_ratio == pytest.approx(0.8)
    assert not o.off_design
    s[3] = 2.0 * m.v_induced_hover  # same descent with fast forward flight: wake blown away
    m.derivative(s, [hp.duty] * 4, out=o)
    assert o.descent_ratio == 0.0
    assert o.edgewise_ratio == pytest.approx(2.0 * m.v_induced_hover / (hp.omega * m.radius))
    s = m.initial_state(position=(0, 0, -50.0), omega=300.0)
    s[3] = 30.0  # fast dive at idle: flat-plate regime
    m.derivative(s, [0.05] * 4, out=o)
    assert o.off_design and o.edgewise_ratio > rf.CLASSICAL_LIMIT


def test_descent_raises_thrust_at_constant_rpm(aircraft):
    """Descending lowers the inflow through the disk, so a fixed-pitch prop at fixed
    rpm makes more thrust (mean flow; the vortex-ring fluctuations are not modelled)."""
    rotor = rf.anchored_rotor(aircraft.powertrain.prop, 0.5)
    omega, rho = 2500.0, aircraft.env.rho
    hover = rotor.loads((0.0, 0.0, 0.0), omega, 1.0, rho)["thrust"]
    descent = rotor.loads((0.0, 0.0, 4.0), omega, 1.0, rho)["thrust"]
    climb = rotor.loads((0.0, 0.0, -4.0), omega, 1.0, rho)["thrust"]
    assert climb < hover < descent


# --------------------------------------------------------------------- loading


def test_prop_data_must_match_the_rotor_model(tmp_path):
    """A prop with blade geometry needs flap_fraction and must not carry the legacy factor."""
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data", data)
    prop = data / "components" / "props" / "generic-5.1x4.3x3.toml"
    text = prop.read_text(encoding="utf-8")
    lines = text.splitlines()
    flap = next(l for l in lines if l.startswith("flap_fraction"))
    build = data / "builds" / REFERENCE_BUILD.name
    prop.write_text(text.replace(flap, flap + '\nrotor_drag_factor = { value = 0.5, unit = "1", source = "estimate" }'),
                    encoding="utf-8")
    with pytest.raises(DesignError, match="rotor_drag_factor is not used"):
        load_build(build)
    prop.write_text(text.replace(flap + "\n", ""), encoding="utf-8")
    with pytest.raises(DesignError, match="needs flap_fraction"):
        load_build(build)
