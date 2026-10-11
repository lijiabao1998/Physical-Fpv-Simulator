import numpy as np
import pytest

from physical_fpv.fpv.flight import Controller, FlightConfig, FlightModel, rotation


def test_hover_and_freefall_analytical():
    c = FlightConfig(ground_enabled=False, drag_area_m2=(0, 0, 0))
    m = FlightModel(c)
    m.state.position_m[2] = 10
    for _ in range(100):
        m.step([c.mass_kg * c.gravity_m_s2 / 4] * 4, [0] * 4, 0.01)
    assert np.allclose(m.state.position_m, [0, 0, 10], atol=1e-12)
    for _ in range(100):
        m.step([0] * 4, [0] * 4, 0.01)
    assert m.state.position_m[2] == pytest.approx(10 - 0.5 * c.gravity_m_s2, abs=1e-11)
    assert m.state.velocity_m_s[2] == pytest.approx(-c.gravity_m_s2, abs=1e-11)


def test_moment_signs_and_normalization():
    m = FlightModel(FlightConfig(ground_enabled=False))
    m.step([1, 0, 0, 0], [0.02, 0, 0, 0], 0.001)
    w = m.state.angular_velocity_rad_s
    assert w[0] > 0 and w[1] < 0 and w[2] > 0
    assert np.linalg.norm(m.state.quaternion_wxyz) == pytest.approx(1)
    assert np.allclose(
        rotation(m.state.quaternion_wxyz).T @ rotation(m.state.quaternion_wxyz), np.eye(3)
    )


def test_conservative_freefall_energy():
    m = FlightModel(FlightConfig(ground_enabled=False, drag_area_m2=(0, 0, 0)))
    m.state.position_m[2] = 100
    c = m.config
    initial = c.mass_kg * c.gravity_m_s2 * 100
    for _ in range(100):
        m.step([0] * 4, [0] * 4, 0.01)
    energy = (
        0.5 * c.mass_kg * np.dot(m.state.velocity_m_s, m.state.velocity_m_s)
        + c.mass_kg * c.gravity_m_s2 * m.state.position_m[2]
    )
    assert energy == pytest.approx(initial, rel=1e-12)


def test_dt_refinement():
    def run(dt):
        m = FlightModel(FlightConfig(ground_enabled=False))
        m.state.position_m[2] = 10
        for _ in range(round(0.4 / dt)):
            m.step([1.9, 1.8, 1.7, 1.8], [0.02, 0.018, 0.017, 0.018], dt)
        return np.r_[m.state.position_m, m.state.quaternion_wxyz, m.state.velocity_m_s]

    a, b, c = run(0.02), run(0.01), run(0.005)
    assert np.linalg.norm(b - c) < np.linalg.norm(a - b) / 8
    assert np.max(abs(b - c)) < 1e-5


def test_contact_and_input_rejection():
    m = FlightModel(FlightConfig(obstacles=(((1, -1, 0), (2, 1, 2)),)))
    m.state.position_m = np.array([0.9, 0, 1.0])
    m.state.velocity_m_s = np.array([2.0, 0, 0])
    m.step([0] * 4, [0] * 4, 0.01)
    assert m.state.position_m[0] <= 0.85 + 1e-10
    assert m.state.velocity_m_s[0] == 0
    assert m.state.collision_count == 1
    assert m.state.contact_energy_lost_j > 0
    before = m.telemetry()
    with pytest.raises(ValueError):
        m.step([float("nan")] * 4, [0] * 4, 0.01)
    assert m.telemetry() == before
    with pytest.raises(ValueError):
        m.step([1] * 4, [0] * 4, 0.1)
    with pytest.raises(ValueError):
        FlightModel(FlightConfig(inertia_kg_m2=(1, 0.1, 0.1)))


def test_controller_direction_and_bounds():
    m = FlightModel()
    c = Controller()
    duties = c.duties(m.state, 0.5, 1, 0, 0, 0.01)
    assert duties[0] > duties[2] and duties[1] > duties[3]
    assert np.min(duties) >= 0 and np.max(duties) <= 1
    with pytest.raises(ValueError):
        c.duties(m.state, 1.1, 0, 0, 0, 0.01)


def test_torque_free_angular_momentum_and_energy():
    c = FlightConfig(
        ground_enabled=False, gravity_m_s2=0, drag_area_m2=(0, 0, 0), angular_drag_nm_s=0
    )
    m = FlightModel(c)
    m.state.angular_velocity_rad_s = np.array([0.8, 0.5, 0.3])
    inertia = np.array(c.inertia_kg_m2)
    initial_h = rotation(m.state.quaternion_wxyz) @ (inertia * m.state.angular_velocity_rad_s)
    initial_e = 0.5 * np.dot(
        inertia * m.state.angular_velocity_rad_s, m.state.angular_velocity_rad_s
    )
    for _ in range(1000):
        m.step([0] * 4, [0] * 4, 0.002)
    final_h = rotation(m.state.quaternion_wxyz) @ (inertia * m.state.angular_velocity_rad_s)
    final_e = 0.5 * np.dot(inertia * m.state.angular_velocity_rad_s, m.state.angular_velocity_rad_s)
    assert np.max(abs(final_h - initial_h)) < 1e-12
    assert abs(final_e - initial_e) < 1e-12
