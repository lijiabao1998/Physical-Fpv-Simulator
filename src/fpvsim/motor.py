"""Brushless motor and ESC, as an averaged DC-motor model.

For a BLDC motor driven by an ESC, averaged over a PWM period and electrical
revolution:

    V_m   = duty * V_bus                       (ESC as ideal buck converter)
    I_bus = duty * I_m                         (power balance)
    I_m   = (V_m - Ke * omega) / (Rm + R_esc)  (winding inductance neglected)
    tau   = Kt * (I_m - I0(omega))             (I0 lumps friction and iron loss)

In SI units Kt = Ke = 1 / Kv for an ideal BLDC motor. Winding inductance is
neglected because the electrical time constant (tens of microseconds) is far
below the mechanical one (tens of milliseconds).

No-load current is modelled as affine in speed:

    I0(omega) = I0_ref * ((1 - f) + f * omega / omega_ref)

The constant part represents bearing friction and hysteresis loss (constant
torque); the speed-proportional part eddy-current and viscous loss. omega_ref
is the no-load speed at the voltage where I0_ref was measured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Motor:
    kv: float  # rad/s/V
    rm: float  # ohm, line-to-line winding resistance
    i0_ref: float  # A, no-load current at v_i0_ref
    v_i0_ref: float  # V
    i0_speed_fraction: float  # f in [0, 1]
    rotor_inertia: float  # kg m^2, bell and magnets
    max_current: float  # A, rated peak current

    @property
    def ke(self) -> float:
        return 1.0 / self.kv

    @property
    def kt(self) -> float:
        return 1.0 / self.kv

    @property
    def omega_ref(self) -> float:
        return self.kv * (self.v_i0_ref - self.i0_ref * self.rm)

    @property
    def i0_const(self) -> float:
        return self.i0_ref * (1.0 - self.i0_speed_fraction)

    @property
    def i0_slope(self) -> float:
        """dI0/domega, A per rad/s."""
        return self.i0_ref * self.i0_speed_fraction / self.omega_ref

    def i0(self, omega: float) -> float:
        return self.i0_const + self.i0_slope * omega


@dataclass(frozen=True)
class ESC:
    r_on: float  # ohm, series resistance in the motor current path
    quiescent_power: float  # W, logic and gate drive per ESC board
    max_current: float  # A, rated continuous current per channel


def solve_omega(motor: Motor, r_circuit: float, v_motor: float, k_torque: float) -> float:
    """Steady speed where motor torque equals a quadratic load k_torque * omega^2.

    Kt * ((V - Ke w) / R - I0(w)) = kQ w^2 is quadratic in w:
        kQ w^2 + (Kt Ke / R + Kt dI0/dw) w - Kt (V / R - I0_const) = 0
    The positive root is unique. If the drive cannot overcome the constant
    loss torque, the rotor stays at rest.
    """
    kt = motor.kt
    a = k_torque
    b = kt * motor.ke / r_circuit + kt * motor.i0_slope
    c = kt * (v_motor / r_circuit - motor.i0_const)
    if c <= 0.0:
        return 0.0
    if a == 0.0:
        return c / b
    return 2.0 * c / (b + math.sqrt(b * b + 4.0 * a * c))  # stable form of the root
