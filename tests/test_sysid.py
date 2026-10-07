import math

import numpy as np
import pytest

from fpvsim import sysid
from fpvsim.stand import run_stand, write_csv

RHO, D = 1.2, 0.127


def synthetic_stand(ct0, cp0, noise, seed=0, proportional=True):
    """Stand readings with Gaussian noise, either proportional to the reading
    (typical load cell) or of constant size (noise given relative to the maximum)."""
    rng = np.random.default_rng(seed)
    omega = np.linspace(500, 3500, 25)
    n = omega / (2 * math.pi)
    thrust = ct0 * RHO * n**2 * D**4
    torque = cp0 / (2 * math.pi) * RHO * n**2 * D**5
    scale_t = thrust if proportional else thrust.max()
    scale_q = torque if proportional else torque.max()
    return (
        omega,
        thrust + noise * scale_t * rng.standard_normal(25),
        torque + noise * scale_q * rng.standard_normal(25),
    )


def test_prop_fit_is_exact_on_noiseless_data():
    fits = sysid.fit_prop_static(*synthetic_stand(0.2, 0.11, 0.0), rho=RHO, diameter=D)
    assert fits["ct0"].values["ct0"] == pytest.approx(0.2, rel=1e-12)
    assert fits["cp0"].values["cp0"] == pytest.approx(0.11, rel=1e-12)


def test_prop_fit_recovers_truth_within_its_stated_uncertainty():
    fits = sysid.fit_prop_static(*synthetic_stand(0.2, 0.11, 0.02, seed=3), rho=RHO, diameter=D)
    for key, truth in (("ct0", 0.2), ("cp0", 0.11)):
        fit = fits[key]
        assert abs(fit.values[key] - truth) < 4 * fit.stderr[key]
        assert 0 < fit.u_rel(key) < 0.02


@pytest.mark.parametrize("proportional", [True, False])
def test_stated_uncertainty_matches_actual_scatter(proportional):
    """Coverage check: the standard error must describe repeat-experiment spread,
    whether the noise grows with the reading or not."""
    estimates, errors = [], []
    for seed in range(300):
        stand = synthetic_stand(0.2, 0.11, 0.02, seed=seed, proportional=proportional)
        fit = sysid.fit_prop_static(*stand, rho=RHO, diameter=D)["ct0"]
        estimates.append(fit.values["ct0"])
        errors.append(fit.stderr["ct0"])
    assert np.std(estimates, ddof=1) == pytest.approx(np.mean(errors), rel=0.2)


def test_motor_fits_on_noiseless_data():
    kv, rm, i0a, i0b = 183.0, 0.08, 0.5, 2.7e-4
    omega = np.linspace(500, 4000, 12)
    current = i0a + i0b * omega
    voltage = omega / kv + current * rm
    fits = sysid.fit_motor_no_load(voltage, current, omega, rm)
    assert fits["kv"].values["kv"] == pytest.approx(kv, rel=1e-10)
    assert fits["i0"].values["i0_const"] == pytest.approx(i0a, rel=1e-9)
    assert fits["i0"].values["i0_slope"] == pytest.approx(i0b, rel=1e-9)

    i_load = np.linspace(2, 40, 12)
    loaded = sysid.fit_motor_loaded(omega / kv + i_load * 0.083, i_load, omega)
    assert loaded.values["ke"] == pytest.approx(1 / kv, rel=1e-10)
    assert loaded.values["r_circuit"] == pytest.approx(0.083, rel=1e-9)


def test_virtual_stand_csv_round_trip(reference_build, tmp_path):
    """Virtual stand -> CSV -> identification recovers the model's coefficients."""
    ac = reference_build.realize()
    path = tmp_path / "stand.csv"
    write_csv(run_stand(ac, voltage=25.2), path)
    data = sysid.read_csv(path)
    fits = sysid.fit_prop_static(data["rpm"], data["thrust"], data["torque"], ac.env.rho, ac.powertrain.prop.diameter)
    assert fits["ct0"].values["ct0"] == pytest.approx(ac.powertrain.prop.ct0, rel=1e-4)
    assert fits["cp0"].values["cp0"] == pytest.approx(ac.powertrain.prop.cp0, rel=1e-4)


def test_csv_headers_must_carry_units(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("rpm,thrust [gf]\n1000,100\n")
    with pytest.raises(ValueError):
        sysid.read_csv(path)
