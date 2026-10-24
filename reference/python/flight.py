"""Newton–Euler quadrotor baseline in SI units; synthetic parameters, no hardware fit.

World and body frames: right-handed z-up, body x forward/y left. Quaternion wxyz
rotates body into world. Rotors: (+x,+y), (-x,+y), (-x,-y), (+x,-y); yaw signs +-+-.
Equations follow MIT VNAV Lecture 6, https://vnav.mit.edu/material/06-Control1-notes.pdf.
Contact is a declared inelastic sphere/AABB approximation, not crash mechanics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np


def _vector(value, n, name):
    a = np.asarray(value, dtype=float)
    if a.shape != (n,) or not np.isfinite(a).all():
        raise ValueError(f"{name} must have {n} finite values")
    return a


def rotation(q):
    q = _vector(q, 4, "quaternion")
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        raise ValueError("Quaternion must be nonzero")
    w, x, y, z = q / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def euler_angles(q):
    r = rotation(q)
    return np.array(
        [
            np.arctan2(r[2, 1], r[2, 2]),
            np.arcsin(np.clip(-r[2, 0], -1, 1)),
            np.arctan2(r[1, 0], r[0, 0]),
        ]
    )


@dataclass(frozen=True)
class FlightConfig:
    mass_kg: float = 0.72
    inertia_kg_m2: tuple[float, float, float] = (0.005, 0.005, 0.009)
    arm_m: float = 0.12
    gravity_m_s2: float = 9.80665
    air_density_kg_m3: float = 1.225
    drag_area_m2: tuple[float, float, float] = (0.025, 0.025, 0.04)
    angular_drag_nm_s: float = 0.001
    collision_radius_m: float = 0.15
    ground_enabled: bool = True
    obstacles: tuple = ()  # world-coordinate lower/upper corners, metres

    def validate(self):
        if not 0.05 <= self.mass_kg <= 10 or not 0.02 <= self.arm_m <= 1:
            raise ValueError("Mass or arm outside baseline domain")
        inertia = _vector(self.inertia_kg_m2, 3, "inertia")
        if np.any(inertia <= 0) or np.any(inertia > 1):
            raise ValueError("Positive bounded principal moments required")
        if np.max(inertia) > np.sum(inertia) - np.max(inertia) + 1e-12:
            raise ValueError("Principal moments must satisfy triangle inequality")
        vals = [
            self.gravity_m_s2,
            self.air_density_kg_m3,
            self.angular_drag_nm_s,
            self.collision_radius_m,
            *self.drag_area_m2,
        ]
        if not np.isfinite(vals).all() or min(vals) < 0:
            raise ValueError("Nonnegative finite physical coefficients required")
        for low, high in self.obstacles:
            if np.any(_vector(low, 3, "obstacle low") >= _vector(high, 3, "obstacle high")):
                raise ValueError("Obstacle corners must be increasing")


@dataclass
class FlightState:
    position_m: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.15]))
    velocity_m_s: np.ndarray = field(default_factory=lambda: np.zeros(3))
    quaternion_wxyz: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    angular_velocity_rad_s: np.ndarray = field(default_factory=lambda: np.zeros(3))
    time_s: float = 0.0
    collision_count: int = 0
    contact_energy_lost_j: float = 0.0


class FlightModel:
    def __init__(self, config=None):
        self.config = config or FlightConfig()
        self.config.validate()
        self.state = FlightState()
        self.state.position_m[2] = self.config.collision_radius_m
        self._contact = False

    def _rhs(self, y, thrust, torque, wind):
        c = self.config
        q, omega = y[6:10], y[10:13]
        r = rotation(q)
        relative_body = r.T @ (y[3:6] - wind)
        drag_body = (
            -0.5
            * c.air_density_kg_m3
            * np.asarray(c.drag_area_m2)
            * relative_body
            * abs(relative_body)
        )
        acceleration = r @ (drag_body + [0, 0, np.sum(thrust)]) / c.mass_kg
        acceleration[2] -= c.gravity_m_s2
        arm = c.arm_m / np.sqrt(2)
        moment = np.array(
            [
                arm * np.dot([1, 1, -1, -1], thrust),
                arm * np.dot([-1, 1, 1, -1], thrust),
                np.dot([1, -1, 1, -1], torque),
            ]
        )
        inertia = np.asarray(c.inertia_kg_m2)
        domega = (moment - np.cross(omega, inertia * omega) - c.angular_drag_nm_s * omega) / inertia
        w, x, yy, z = q
        wx, wy, wz = omega
        dq = 0.5 * np.array(
            [
                -x * wx - yy * wy - z * wz,
                w * wx + yy * wz - z * wy,
                w * wy + z * wx - x * wz,
                w * wz + x * wy - yy * wx,
            ]
        )
        return np.r_[y[3:6], acceleration, dq, domega]

    def step(self, thrust_n, rotor_torque_nm, dt_s, wind_m_s=(0, 0, 0)):
        thrust = _vector(thrust_n, 4, "thrust")
        torque = _vector(rotor_torque_nm, 4, "rotor torque")
        wind = _vector(wind_m_s, 3, "wind")
        if np.any(thrust < 0) or np.any(thrust > 100) or np.any(torque < 0):
            raise ValueError("Rotor loads outside nonnegative baseline range")
        if not np.isfinite(dt_s) or not 0 < dt_s <= 0.02:
            raise ValueError("Flight step must be in (0, 0.02] s")
        s = self.state
        y = np.r_[
            _vector(s.position_m, 3, "position"),
            _vector(s.velocity_m_s, 3, "velocity"),
            _vector(s.quaternion_wxyz, 4, "quaternion"),
            _vector(s.angular_velocity_rad_s, 3, "angular velocity"),
        ]

        def rhs(state):
            return self._rhs(state, thrust, torque, wind)

        k1 = rhs(y)
        k2 = rhs(y + dt_s * k1 / 2)
        k3 = rhs(y + dt_s * k2 / 2)
        k4 = rhs(y + dt_s * k3)
        ynew = y + dt_s * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if not np.isfinite(ynew).all() or np.linalg.norm(ynew[10:]) > 100:
            raise ValueError("Flight state left numerical envelope")
        ynew[6:10] /= np.linalg.norm(ynew[6:10])
        position, velocity = ynew[:3], ynew[3:6]
        energy_before = 0.5 * self.config.mass_kg * np.dot(velocity, velocity)
        contact = False
        radius = self.config.collision_radius_m
        if self.config.ground_enabled and position[2] < radius:
            position[2] = radius
            if velocity[2] < 0:
                velocity[2] = 0
            contact = True
        for low, high in self.config.obstacles:
            low, high = np.asarray(low), np.asarray(high)
            nearest = np.clip(position, low, high)
            delta = position - nearest
            distance = np.linalg.norm(delta)
            if distance < radius:
                if distance < 1e-12:
                    distances = np.r_[position - low, high - position]
                    face = int(np.argmin(distances))
                    axis = face % 3
                    normal = np.zeros(3)
                    normal[axis] = -1 if face < 3 else 1
                    position[axis] = low[axis] - radius if face < 3 else high[axis] + radius
                else:
                    normal = delta / distance
                    position[:] = nearest + radius * normal
                closing = np.dot(velocity, normal)
                if closing < 0:
                    velocity[:] -= closing * normal
                contact = True
        s.position_m, s.velocity_m_s = position.copy(), velocity.copy()
        s.quaternion_wxyz, s.angular_velocity_rad_s = ynew[6:10].copy(), ynew[10:13].copy()
        s.time_s += dt_s
        s.collision_count += int(contact and not self._contact)
        s.contact_energy_lost_j += max(
            0.0, energy_before - 0.5 * self.config.mass_kg * np.dot(velocity, velocity)
        )
        self._contact = contact
        return s

    def telemetry(self):
        result = asdict(self.state)
        for key, value in result.items():
            if isinstance(value, np.ndarray):
                result[key] = value.tolist()
        result["euler_rad"] = euler_angles(self.state.quaternion_wxyz).tolist()
        result["mass_kg"] = self.config.mass_kg
        return result


class Controller:
    """Synthetic angle-mode PD/rate controller and duty mixer; no flight firmware claim."""

    def duties(self, state, throttle, roll, pitch, yaw, dt_s):
        inputs = np.array([throttle, roll, pitch, yaw, dt_s], dtype=float)
        if not np.isfinite(inputs).all() or not 0 <= throttle <= 1 or max(abs(inputs[1:4])) > 1:
            raise ValueError("Normalized controls outside domain")
        if not 0 < dt_s <= 0.02:
            raise ValueError("Controller dt outside domain")
        angles = euler_angles(state.quaternion_wxyz)
        target_rates = np.array([roll * 0.5 - angles[0], pitch * 0.5 - angles[1], 0.0]) * 5
        target_rates[2] = yaw * 2
        error = target_rates - state.angular_velocity_rad_s
        correction = np.clip(error * np.array([0.05, 0.05, 0.025]), -0.2, 0.2)
        # signs mirror r cross F and rotor reaction torque, not a game boost.
        mixing = np.array([[1, -1, 1], [1, 1, -1], [-1, 1, 1], [-1, -1, -1]])
        return np.clip(throttle + mixing @ correction, 0, 1)
