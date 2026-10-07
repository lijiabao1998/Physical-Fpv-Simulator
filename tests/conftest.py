from pathlib import Path

import numpy as np
import pytest

from fpvsim.design import load_build
from fpvsim.motor import ESC, Motor
from fpvsim.powertrain import Powertrain
from fpvsim.prop import Prop, PropCurves
from fpvsim.units import RPM_TO_RADS

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_BUILD = ROOT / "data" / "builds" / "ref-5in-6s-freestyle.toml"


@pytest.fixture(scope="session")
def reference_build():
    return load_build(REFERENCE_BUILD)


def make_powertrain(n_rotors: int = 4, p_aux: float = 5.0) -> Powertrain:
    """A self-contained powertrain with round numbers, independent of the data files."""
    curves = PropCurves(np.array([0.0, 0.5]), np.array([0.20, 0.10]), np.array([0.11, 0.09]))
    prop = Prop(diameter=0.127, blades=3, pitch=0.11, mass=0.004, spin_inertia=5e-6, curves=curves)
    motor = Motor(
        kv=1750 * RPM_TO_RADS,
        rm=0.08,
        i0_ref=1.0,
        v_i0_ref=10.0,
        i0_speed_fraction=0.5,
        rotor_inertia=2e-6,
        max_current=45.0,
    )
    esc = ESC(r_on=0.003, quiescent_power=0.5, max_current=50.0)
    return Powertrain(motor, prop, esc, n_rotors, p_aux)


@pytest.fixture
def powertrain():
    return make_powertrain()
