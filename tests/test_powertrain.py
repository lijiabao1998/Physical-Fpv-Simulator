
import numpy as np
import pytest

from fpvsim.battery import Battery, BatteryState
from fpvsim.motor import solve_omega

from conftest import make_powertrain

RHO = 1.225


def test_no_load_speed(powertrain):
    m, R = powertrain.motor, powertrain.r_circuit
    omega = solve_omega(m, R, 20.0, k_torque=0.0)
    # V = Ke w + R I0(w)  ->  w = (V - R I0_const) / (Ke + R dI0/dw)
    assert omega == pytest.approx((20.0 - R * m.i0_const) / (m.ke + R * m.i0_slope))


def test_motor_cannot_overcome_constant_loss():
    m = make_powertrain().motor
    assert solve_omega(m, 0.08, 0.5 * 0.08 * m.i0_const, k_torque=1e-8) == 0.0


@pytest.mark.parametrize("v, kq", [(3.0, 2e-8), (12.0, 2e-8), (25.0, 5e-8), (25.0, 1e-9)])
def test_torque_balance_and_energy_conservation(powertrain, v, kq):
    m, R = powertrain.motor, powertrain.r_circuit
    w = solve_omega(m, R, v, kq)
    i = (v - m.ke * w) / R
    assert m.kt * (i - m.i0(w)) == pytest.approx(kq * w**2, rel=1e-10)
    # electrical input = copper loss + friction/iron loss + shaft power
    assert v * i == pytest.approx(i * i * R + m.kt * m.i0(w) * w + kq * w**3, rel=1e-10)


def test_closed_form_hover_matches_numeric_duty_solve(powertrain):
    op = powertrain.for_thrust(1.4, v_source=25.0, r_source=0.04, rho=RHO)
    check = powertrain.at_duty(op.duty, 25.0, 0.04, RHO)
    assert check.thrust == pytest.approx(1.4, rel=1e-8)
    assert check.v_bus == pytest.approx(op.v_bus, rel=1e-9)


def test_bus_power_and_source_balance(powertrain):
    op = powertrain.at_duty(0.7, 25.0, 0.04, RHO)
    assert op.p_bus == pytest.approx(op.p_motor_in + powertrain.p_aux, rel=1e-9)
    assert op.v_bus == pytest.approx(25.0 - 0.04 * op.i_bus, rel=1e-9)
    assert op.i_motor * op.duty * op.n_rotors < op.i_bus  # aux load adds bus current


def test_hover_scaling_with_mass(powertrain):
    """T = kT w^2 and P = kQ w^3: +10 % thrust -> +4.88 % speed, +15.37 % shaft power."""
    a = powertrain.for_thrust(1.4, 25.0, 0.0, RHO)
    b = powertrain.for_thrust(1.4 * 1.1, 25.0, 0.0, RHO)
    assert b.omega / a.omega == pytest.approx(1.1**0.5, rel=1e-12)
    assert b.p_shaft / a.p_shaft == pytest.approx(1.1**1.5, rel=1e-12)


def test_hover_scaling_with_air_density(powertrain):
    """Thinner air: w ~ rho^-1/2 and hover power ~ rho^-1/2."""
    a = powertrain.for_thrust(1.4, 25.0, 0.0, RHO)
    b = powertrain.for_thrust(1.4, 25.0, 0.0, 0.9 * RHO)
    assert b.omega / a.omega == pytest.approx(0.9**-0.5, rel=1e-12)
    assert b.p_shaft / a.p_shaft == pytest.approx(0.9**-0.5, rel=1e-12)


def test_thrust_increases_with_duty(powertrain):
    thrusts = [powertrain.at_duty(d, 25.0, 0.04, RHO).thrust for d in np.linspace(0.05, 1.0, 20)]
    assert all(np.diff(thrusts) > 0)


def test_infeasible_points_return_none(powertrain):
    assert powertrain.for_thrust(50.0, 25.0, 0.0, RHO) is None  # needs duty > 1
    assert powertrain.at_duty(1.0, 25.0, 5.0, RHO) is None  # source cannot deliver the power
    assert powertrain.for_thrust(1.4, 25.0, 50.0, RHO) is None


def make_battery(**kw):
    args = dict(
        series=6,
        parallel=1,
        capacity=4680.0,
        r0_cell=0.004,
        r1_cell=0.003,
        tau1=20.0,
        ocv_soc=np.array([0.0, 0.5, 1.0]),
        ocv_cell=np.array([3.3, 3.8, 4.2]),
        max_current=130.0,
    )
    args.update(kw)
    return Battery(**args)


def test_battery_steady_state_sag():
    b = make_battery()
    state = BatteryState(soc=0.9)
    for _ in range(400):
        state = state.step(b, 20.0, 1.0)
    terminal = state.source_voltage(b) - 20.0 * b.r0
    assert state.v_rc == pytest.approx(20.0 * b.r1, rel=1e-6)
    assert terminal == pytest.approx(b.ocv(state.soc) - 20.0 * (b.r0 + b.r1), rel=1e-6)


def test_battery_step_is_exact_for_constant_current():
    b = make_battery()
    one = BatteryState().step(b, 15.0, 10.0)
    many = BatteryState()
    for _ in range(10):
        many = many.step(b, 15.0, 1.0)
    assert one.v_rc == pytest.approx(many.v_rc, rel=1e-12)
    assert one.soc == pytest.approx(many.soc, rel=1e-12)
    assert 1.0 - one.soc == pytest.approx(15.0 * 10.0 / 4680.0)


def test_battery_validation_and_energy():
    with pytest.raises(ValueError):
        make_battery(ocv_soc=np.array([0.0, 0.8, 0.5]))
    b = make_battery()
    assert b.ocv(0.5) == pytest.approx(6 * 3.8)
    # piecewise-linear OCV: mean cell voltage = (3.3 + 2*3.8 + 4.2) / 4
    assert b.nominal_energy() == pytest.approx(4680.0 * 6 * 3.775, rel=1e-6)
