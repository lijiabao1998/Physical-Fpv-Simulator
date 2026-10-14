"""Propeller performance in non-dimensional coefficients.

Standard propeller convention with n in revolutions per second:

    T = Ct(J) * rho * n^2 * D^4
    P = Cp(J) * rho * n^3 * D^5,  Q = P / (2 pi n) = Cq * rho * n^2 * D^5
    J = V / (n D)                  (advance ratio, V = axial inflow speed)

Coefficient curves come either from test-stand data (system identification,
see sysid.py) or, when no measurement exists, from blade element momentum
theory (bemt.py). ``ct_scale`` and ``cp_scale`` carry the model-form
uncertainty of whichever source produced the curves; they are 1.0 nominally
and get sampled in uncertainty analysis.

Small props run at blade Reynolds numbers of 2e4 to 1e5, where laminar
separation makes the sections lose lift and gain drag as the rotor slows:
Ct and the figure of merit fall noticeably from full throttle to hover. An
optional ``ReynoldsCorrection`` scales the static coefficients with the
blade Reynolds number (an empirical power law fitted to test data, see
docs/models.md); without it Ct and Cp do not change with rpm.
Compressibility is not modelled; tip Mach number is reported as a validity
check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PropCurves:
    J: np.ndarray
    ct: np.ndarray
    cp: np.ndarray

    def __post_init__(self) -> None:
        if self.J[0] != 0.0 or np.any(np.diff(self.J) <= 0):
            raise ValueError("advance-ratio grid must start at 0 and be strictly ascending")
        if not (len(self.J) == len(self.ct) == len(self.cp)):
            raise ValueError("J, ct and cp must have the same length")

    def ct_at(self, J: float) -> float:
        return float(np.interp(J, self.J, self.ct))

    def cp_at(self, J: float) -> float:
        return float(np.interp(J, self.J, self.cp))


@dataclass(frozen=True)
class ReynoldsCorrection:
    """Coefficients as power laws of the blade Reynolds number at 75 % radius,
    from the rotational speed only, Re = Omega (0.75 R) c75 / nu:

        Ct = Ct(J) (Re / Re_ref)^ct_exponent
        FM ~ (Re / Re_ref)^fm_exponent, so Cp = Cp(J) (Re / Re_ref)^(1.5 ct_exponent - fm_exponent)

    The curves Ct(J), Cp(J) hold at Re_ref; the same factor applies at every J.
    Outside [re_min, re_max], the range of the data the exponents come from,
    the factors are held at their boundary values."""

    chord75: float  # m, blade chord at 75 % radius (defines Re)
    re_ref: float
    re_min: float
    re_max: float
    ct_exponent: float
    fm_exponent: float

    def __post_init__(self) -> None:
        if not 0.0 < self.re_min <= self.re_ref <= self.re_max:
            raise ValueError("Reynolds correction needs 0 < re_min <= re_ref <= re_max")
        if self.chord75 <= 0.0:
            raise ValueError("Reynolds correction needs a positive chord")

    @property
    def cp_exponent(self) -> float:
        return 1.5 * self.ct_exponent - self.fm_exponent

    def factors(self, re: float) -> tuple[float, float]:
        """(Ct factor, Cp factor) at Reynolds number ``re``."""
        x = math.log(min(max(re, self.re_min), self.re_max) / self.re_ref)
        return math.exp(self.ct_exponent * x), math.exp(self.cp_exponent * x)


@dataclass(frozen=True)
class Prop:
    diameter: float  # m
    blades: int
    pitch: float  # m, nominal geometric pitch
    mass: float  # kg
    spin_inertia: float  # kg m^2 about the shaft
    curves: PropCurves
    ct_scale: float = 1.0
    cp_scale: float = 1.0
    # (BladeGeometry, Airfoil) when the blade geometry is known: enables the
    # oblique-flow rotor model (rotor_ff.py), anchored to the curves above
    blade: tuple | None = None
    reynolds: ReynoldsCorrection | None = None  # None: coefficients independent of rpm

    @property
    def radius(self) -> float:
        return 0.5 * self.diameter

    @property
    def disk_area(self) -> float:
        return math.pi * self.radius**2

    @property
    def ct0(self) -> float:
        return self.ct_scale * float(self.curves.ct[0])

    @property
    def cp0(self) -> float:
        return self.cp_scale * float(self.curves.cp[0])

    @property
    def cq0(self) -> float:
        return self.cp0 / (2.0 * math.pi)

    def k_thrust(self, rho: float) -> float:
        """Static thrust per omega^2 at the reference Reynolds number:
        T = k_thrust * omega^2 * (Ct factor) (omega in rad/s)."""
        return self.ct0 * rho * self.diameter**4 / (2.0 * math.pi) ** 2

    def k_torque(self, rho: float) -> float:
        """Static shaft torque per omega^2 at the reference Reynolds number."""
        return self.cq0 * rho * self.diameter**5 / (2.0 * math.pi) ** 2

    def reynolds_number(self, omega: float, nu: float) -> float:
        """Blade Reynolds number at 75 % radius from the rotational speed (needs the correction's chord)."""
        if self.reynolds is None:
            raise ValueError("prop has no Reynolds correction (no chord to define Re)")
        return abs(omega) * 0.75 * self.radius * self.reynolds.chord75 / nu

    def re_factors(self, omega: float, nu: float) -> tuple[float, float]:
        """(Ct factor, Cp factor) at rotor speed ``omega`` in air of kinematic viscosity ``nu``."""
        if self.reynolds is None:
            return 1.0, 1.0
        return self.reynolds.factors(self.reynolds_number(omega, nu))

    def thrust_static(self, omega: float, rho: float, nu: float) -> float:
        return self.k_thrust(rho) * omega**2 * self.re_factors(omega, nu)[0]

    def torque_static(self, omega: float, rho: float, nu: float) -> float:
        return self.k_torque(rho) * omega**2 * self.re_factors(omega, nu)[1]

    def omega_for_thrust(self, thrust: float, rho: float, nu: float) -> float:
        """Rotor speed giving static ``thrust``. Exact: thrust grows monotonically
        with speed, as omega^(2 + ct_exponent) between the Reynolds limits and as
        omega^2 outside them."""
        k = self.k_thrust(rho)
        rc = self.reynolds
        if rc is None:
            return math.sqrt(thrust / k)
        per_omega = 0.75 * self.radius * rc.chord75 / nu
        w_lo, w_hi, w_ref = rc.re_min / per_omega, rc.re_max / per_omega, rc.re_ref / per_omega
        a = rc.ct_exponent
        f_lo, f_hi = (w_lo / w_ref) ** a, (w_hi / w_ref) ** a
        if thrust <= k * w_lo**2 * f_lo:
            return math.sqrt(thrust / (k * f_lo))
        if thrust >= k * w_hi**2 * f_hi:
            return math.sqrt(thrust / (k * f_hi))
        return (thrust * w_ref**a / k) ** (1.0 / (2.0 + a))

    def figure_of_merit(self, omega: float | None = None, nu: float | None = None) -> float:
        """Static figure of merit (ideal momentum-theory power / actual power),
        at rotor speed ``omega`` or, if not given, at the reference Reynolds number."""
        f_t, f_p = (1.0, 1.0) if omega is None else self.re_factors(omega, nu)
        return (self.ct0 * f_t) ** 1.5 * math.sqrt(2.0 / math.pi) / (self.cp0 * f_p)

    def tip_mach(self, omega: float, speed_of_sound: float) -> float:
        return omega * self.radius / speed_of_sound
