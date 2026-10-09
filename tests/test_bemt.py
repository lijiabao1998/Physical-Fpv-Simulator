import math
from dataclasses import replace

import numpy as np
import pytest

from fpvsim.bemt import Airfoil, BladeGeometry, coefficient_curves, rotor_loads

R = 0.0648
GEOM = BladeGeometry(
    radius=R,
    hub_radius=0.006,
    r_over_R=np.array([0.15, 0.5, 1.0]),
    chord=np.array([0.010, 0.012, 0.005]),
    pitch=0.109,
    blades=3,
)
FOIL = Airfoil(
    cl_alpha=5.7, alpha0=math.radians(-4), cl_max=1.2, cl_min=-0.5, cd_min=0.03, cl_cd_min=0.4, k_cd=0.04
)


def test_converges_with_element_count():
    coarse = coefficient_curves(GEOM, FOIL, np.array([0.0, 0.4]), n_elements=40)
    fine = coefficient_curves(GEOM, FOIL, np.array([0.0, 0.4]), n_elements=160)
    assert np.allclose(coarse.ct, fine.ct, rtol=5e-3)
    assert np.allclose(coarse.cp, fine.cp, rtol=5e-3)


def test_coefficients_are_dimensionless():
    """Without Reynolds or Mach effects, rpm and density must not change Ct, Cp."""
    a = coefficient_curves(GEOM, FOIL, np.array([0.0, 0.3]), rpm_ref=10000, rho=1.225)
    b = coefficient_curves(GEOM, FOIL, np.array([0.0, 0.3]), rpm_ref=30000, rho=1.0)
    assert np.allclose(a.ct, b.ct, rtol=1e-7)
    assert np.allclose(a.cp, b.cp, rtol=1e-7)


def test_drag_free_rotor_obeys_momentum_theory():
    """Momentum theory is the ideal limit: figure of merit must stay below 1."""
    ideal = replace(FOIL, cd_min=0.0, k_cd=0.0)
    c = coefficient_curves(GEOM, ideal, np.array([0.0]))
    fm = c.ct[0] ** 1.5 * math.sqrt(2 / math.pi) / c.cp[0]
    assert 0.7 < fm < 1.0
    real = coefficient_curves(GEOM, FOIL, np.array([0.0]))
    assert real.ct[0] ** 1.5 * math.sqrt(2 / math.pi) / real.cp[0] < fm


def test_trends_with_advance_ratio_and_pitch():
    c = coefficient_curves(GEOM, FOIL, np.linspace(0.0, 0.9, 10))
    assert all(np.diff(c.ct) < 0)  # thrust falls as inflow rises
    flatter = coefficient_curves(replace(GEOM, pitch=0.09), FOIL, np.array([0.0]))
    assert flatter.ct[0] < c.ct[0]
    # at J = 0 more pitch stops paying once the blade is past stall (post-stall polar)
    stalled = coefficient_curves(replace(GEOM, pitch=0.15), FOIL, np.array([0.0]))
    assert stalled.ct[0] < c.ct[0]


def test_polar_blends_into_flat_plate():
    from fpvsim.bemt import FLAT_PLATE_CN, polar

    a = np.radians([5.0, 19.9, 45.0, 90.0, 180.0, -90.0])
    cl, cd = polar(FOIL, a)
    assert cl[0] == pytest.approx(FOIL.cl_alpha * (a[0] - FOIL.alpha0))  # attached
    assert cl[2] == pytest.approx(FLAT_PLATE_CN * 0.5)  # flat plate at 45 degrees
    assert cl[3] == pytest.approx(0.0, abs=1e-12) and cd[3] == pytest.approx(FOIL.cd_min + FLAT_PLATE_CN)
    assert cl[4] == pytest.approx(0.0, abs=1e-12) and cd[4] == pytest.approx(FOIL.cd_min)  # reverse flow, edge on
    assert cd[5] == pytest.approx(cd[3])


def test_descent_is_rejected():
    with pytest.raises(ValueError):
        rotor_loads(GEOM, FOIL, omega=2000.0, v_axial=-1.0, rho=1.225)
