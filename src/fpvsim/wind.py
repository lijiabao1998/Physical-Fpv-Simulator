"""Wind near the ground: mean wind with a logarithmic profile, Dryden
turbulence, and the rotors' ground effect.

Mean wind. Neutral atmospheric surface layer (log law):

    U(h) = U_ref ln(h / z0) / ln(h_ref / z0),   h > z0;   0 below z0

U_ref is the wind at h_ref (10 m, the height of a weather-station report)
and z0 the aerodynamic roughness length (0.03 m open flat terrain, 0.1 m
farmland with hedges, 0.5 m suburbs; Davenport classification as revised by
Wieringa 1992). The wind blows horizontally from ``direction_from``
(meteorological convention, clockwise from north).

Turbulence. Dryden model, low-altitude form of MIL-F-8785C (also in
MIL-HDBK-1797), with h in feet, valid for 10 ft < h < 1000 ft (clamped to
10 ft below):

    L_w = h,   L_u = L_v = h / (0.177 + 0.000823 h)^1.2
    sigma_w = 0.1 W20,   sigma_u = sigma_v = sigma_w / (0.177 + 0.000823 h)^0.4

W20 is the mean wind at 20 ft (6.1 m), taken from the profile above; the
handbook calls 15, 30 and 45 knots light, moderate and severe. The
components are along the mean wind (u), horizontal across it (v) and
vertical (w). With Taylor's frozen-turbulence hypothesis the spatial
spectra become time spectra at the airspeed V, realised by the forming
filters

    H_u(s) ~ 1 / (1 + tau_u s),   H_v,w(s) ~ (1 + sqrt(3) tau s) / (1 + tau s)^2,   tau = L / V

driven by white noise and scaled so that each component's variance is
sigma^2 (the Dryden spectra). The filters are discretised exactly (zero-
order-hold noise integral, Van Loan's method) at the turbulence update
rate; tau follows the current height and airspeed.

Assumptions: the same gust acts on the whole aircraft (it is small
against the scale lengths, L_w >= 3 m), so the rotational gust components
of the handbook and gust differences between rotors are not modelled.
Taylor's hypothesis needs the turbulence intensity to be small against the
airspeed, which is not true in hover; there V is held at least V_MIN.

Ground effect. Cheeseman and Bennett (1955), method of images: at constant
induced power a rotor at height z above the ground gives

    T / T_inf = 1 / (1 - (k R / z)^2),   k = 1/4.

It is applied here as a thrust multiplier at the current rotor speed (the
common simplification in multirotor simulation), with z the distance from
the hub to the ground along the rotor axis, held at its value at z = R / 2
below that (the image model diverges at z = k R), and off when the rotor
axis does not point at the ground. Multirotor tests (Sanchez-Cuevas et
al. 2017; He and Leang 2019) find the rotors' interaction makes the ratio
non-monotonic at a few radii; that is not modelled.

References: MIL-F-8785C (1980) and MIL-HDBK-1797 (1997), section on the
Dryden model; Wieringa, "Updating the Davenport roughness classification",
J. Wind Eng. Ind. Aerodyn. 41 (1992); Cheeseman and Bennett, "The effect
of the ground on a helicopter rotor in forward flight", ARC R&M 3021
(1955); Leishman (2006), ch. 13.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm

FT = 0.3048
W20_HEIGHT = 20.0 * FT  # m
H_MIN = 10.0 * FT  # m, lower limit of the low-altitude model
V_MIN = 1.0  # m/s, airspeed floor for the frozen-turbulence time scales
GROUND_EFFECT_K = 0.25
GROUND_EFFECT_MIN_Z = 0.5  # z / R below which the ground effect ratio is held


@dataclass(frozen=True)
class WindSettings:
    speed: float = 0.0  # m/s, mean wind at ref_height
    direction_from: float = 0.0  # rad, where the wind comes from, clockwise from north
    ref_height: float = 10.0  # m
    roughness: float = 0.03  # m, aerodynamic roughness length z0
    turbulence: bool = True  # Dryden turbulence with the intensity of this mean wind
    turbulence_rate: float = 1000.0  # Hz, update rate of the turbulence filters

    @property
    def calm(self) -> bool:
        return self.speed <= 0.0

    def mean_speed(self, height: float) -> float:
        """Mean wind speed (m/s) at ``height`` m above ground (log law)."""
        if self.calm or height <= self.roughness:
            return 0.0
        return self.speed * math.log(height / self.roughness) / math.log(self.ref_height / self.roughness)

    @property
    def to_direction(self) -> tuple[float, float]:
        """Unit vector (north, east) the wind blows towards."""
        return -math.cos(self.direction_from), -math.sin(self.direction_from)

    def mean_ned(self, height: float) -> tuple[float, float, float]:
        u = self.mean_speed(height)
        n, e = self.to_direction
        return u * n, u * e, 0.0

    @property
    def w20(self) -> float:
        return self.mean_speed(W20_HEIGHT)


def dryden_scales(height: float, w20: float) -> tuple[float, float, float, float, float, float]:
    """(L_u, L_v, L_w) in m and (sigma_u, sigma_v, sigma_w) in m/s at ``height`` m (MIL-F-8785C low altitude)."""
    h = max(height, H_MIN) / FT
    a = 0.177 + 0.000823 * min(h, 1000.0)
    L_w = h * FT
    L_uv = h / a**1.2 * FT
    sigma_w = 0.1 * w20
    sigma_uv = sigma_w / a**0.4
    return L_uv, L_uv, L_w, sigma_uv, sigma_uv, sigma_w


def _second_order(tau: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """State space of sqrt(tau) (1 + sqrt(3) tau s) / (1 + tau s)^2, which has unit
    output variance for unit-intensity white noise: (A, B, C)."""
    a0, a1 = 1.0 / tau**2, 2.0 / tau
    b0, b1 = 1.0 / tau**2, math.sqrt(3.0) / tau
    A = np.array([[0.0, 1.0], [-a0, -a1]])
    B = np.array([[0.0], [1.0]])
    C = math.sqrt(tau) * np.array([b0, b1])
    return A, B, C


def _discretise(A: np.ndarray, B: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact discretisation of dx = A x dt + B dW: (Phi, Cholesky factor of the noise covariance)."""
    n = A.shape[0]
    M = np.zeros((2 * n, 2 * n))
    M[:n, :n] = -A
    M[:n, n:] = B @ B.T
    M[n:, n:] = A.T
    E = expm(M * dt)
    phi = E[n:, n:].T
    q = phi @ E[:n, n:]
    q = 0.5 * (q + q.T)
    return phi, np.linalg.cholesky(q + 1e-18 * np.eye(n))


class Dryden:
    """Turbulence generator: call ``step`` at the turbulence rate with the
    current height and airspeed; returns the gust in NED (m/s)."""

    def __init__(self, wind: WindSettings, rng: np.random.Generator):
        self.wind = wind
        self.rng = rng
        self.dt = 1.0 / wind.turbulence_rate
        self.x_u = 0.0
        self.x_v = np.zeros(2)
        self.x_w = np.zeros(2)
        self._cache: dict[int, tuple] = {}
        self.w20 = wind.w20
        n, e = wind.to_direction
        self.axes = ((n, e, 0.0), (-e, n, 0.0), (0.0, 0.0, 1.0))  # u along the wind, v across, w down
        self._started = False

    def _filter(self, tau: float):
        key = int(round(math.log(tau) * 200.0))  # 0.5 % bins in tau
        hit = self._cache.get(key)
        if hit is None:
            t = math.exp(key / 200.0)
            A, B, C = _second_order(t)
            phi, chol = _discretise(A, B, self.dt)
            hit = (phi, chol, C)
            self._cache[key] = hit
        return hit

    def step(self, height: float, airspeed: float) -> tuple[float, float, float]:
        if self.w20 <= 0.0 or not self.wind.turbulence:
            return 0.0, 0.0, 0.0
        L_u, L_v, L_w, s_u, s_v, s_w = dryden_scales(height, self.w20)
        V = max(airspeed, V_MIN)
        tau_u, tau_v, tau_w = L_u / V, L_v / V, L_w / V
        if not self._started:  # start in the stationary distribution
            self.x_u = float(self.rng.normal())
            for name, tau in (("x_v", tau_v), ("x_w", tau_w)):
                A, B, _ = _second_order(tau)
                P = _stationary(A, B)
                setattr(self, name, np.linalg.cholesky(P) @ self.rng.normal(size=2))
            self._started = True
        d = math.exp(-self.dt / tau_u)
        self.x_u = d * self.x_u + math.sqrt(1.0 - d * d) * float(self.rng.normal())
        phi_v, chol_v, C_v = self._filter(tau_v)
        phi_w, chol_w, C_w = self._filter(tau_w)
        self.x_v = phi_v @ self.x_v + chol_v @ self.rng.normal(size=2)
        self.x_w = phi_w @ self.x_w + chol_w @ self.rng.normal(size=2)
        u, v, w = s_u * self.x_u, s_v * float(C_v @ self.x_v), s_w * float(C_w @ self.x_w)
        (a0, a1, a2), (b0, b1, b2), (c0, c1, c2) = self.axes
        return u * a0 + v * b0 + w * c0, u * a1 + v * b1 + w * c1, u * a2 + v * b2 + w * c2


def _stationary(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    from scipy.linalg import solve_continuous_lyapunov

    return solve_continuous_lyapunov(A, -B @ B.T)


def ground_effect(z_over_r: float) -> float:
    """Thrust ratio in ground effect (Cheeseman-Bennett), z = hub-to-ground distance along the rotor axis."""
    z = max(z_over_r, GROUND_EFFECT_MIN_Z)
    return 1.0 / (1.0 - (GROUND_EFFECT_K / z) ** 2)
