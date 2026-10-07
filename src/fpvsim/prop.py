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

Reynolds-number and compressibility effects are not modelled, so Ct and Cp do
not change with rpm. Tip Mach number is reported as a validity check.
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
class Prop:
    diameter: float  # m
    blades: int
    pitch: float  # m, nominal geometric pitch
    mass: float  # kg
    spin_inertia: float  # kg m^2 about the shaft
    curves: PropCurves
    ct_scale: float = 1.0
    cp_scale: float = 1.0

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
        """Static thrust per omega^2: T = k_thrust * omega^2 (omega in rad/s)."""
        return self.ct0 * rho * self.diameter**4 / (2.0 * math.pi) ** 2

    def k_torque(self, rho: float) -> float:
        """Static shaft torque per omega^2: Q = k_torque * omega^2."""
        return self.cq0 * rho * self.diameter**5 / (2.0 * math.pi) ** 2

    def figure_of_merit(self) -> float:
        """Static figure of merit: ideal momentum-theory power / actual power."""
        return self.ct0**1.5 * math.sqrt(2.0 / math.pi) / self.cp0

    def tip_mach(self, omega: float, speed_of_sound: float) -> float:
        return omega * self.radius / speed_of_sound
