"""Steady-state operating points of the battery -> ESC -> motor -> prop chain.

The source (battery or bench supply) is a Thevenin source V_s behind R_s.
Auxiliary electronics are a constant-power load on the bus. All rotors run at
the same duty (symmetric hover or a full-throttle punch), so with total bus
power P the bus voltage satisfies

    V_bus * (V_s - V_bus) / R_s = P(V_bus)

Of the two roots the higher one is the stable operating point; when the
demand exceeds V_s^2 / (4 R_s) the bus voltage collapses and no operating
point exists.

Only static thrust (zero axial inflow) is used at this stage, so
T = kT omega^2 and Q = kQ omega^2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

from .motor import ESC, Motor, solve_omega
from .prop import Prop
from .units import RADS_TO_RPM


@dataclass(frozen=True)
class OperatingPoint:
    duty: float
    omega: float  # rad/s
    thrust: float  # N per rotor, isolated rotor
    torque: float  # N m per rotor, shaft
    i_motor: float  # A per motor
    v_motor: float  # V per motor, averaged
    v_bus: float  # V at the ESC
    i_bus: float  # A total from the source
    n_rotors: int
    p_aux: float  # W, auxiliary load

    @property
    def rpm(self) -> float:
        return self.omega * RADS_TO_RPM

    @property
    def p_bus(self) -> float:
        return self.v_bus * self.i_bus

    @property
    def p_shaft(self) -> float:
        """Total shaft power, all rotors."""
        return self.n_rotors * self.torque * self.omega

    @property
    def p_motor_in(self) -> float:
        """Total electrical power into the motors (after the ESCs)."""
        return self.n_rotors * self.v_motor * self.i_motor

    @property
    def drive_efficiency(self) -> float:
        """Shaft power / bus power going to the motors (ESC + motor)."""
        p = self.p_bus - self.p_aux
        return self.p_shaft / p if p > 0 else 0.0


@dataclass(frozen=True)
class Powertrain:
    motor: Motor
    prop: Prop
    esc: ESC
    n_rotors: int
    p_aux: float = 0.0  # W on the bus (BEC loads, ESC logic)

    @property
    def r_circuit(self) -> float:
        return self.motor.rm + self.esc.r_on

    def _rotor(self, v_motor: float, rho: float) -> tuple[float, float]:
        omega = solve_omega(self.motor, self.r_circuit, v_motor, self.prop.k_torque(rho))
        i_motor = (v_motor - self.motor.ke * omega) / self.r_circuit
        return omega, i_motor

    def _point(self, duty: float, v_bus: float, rho: float) -> OperatingPoint:
        v_motor = duty * v_bus
        omega, i_motor = self._rotor(v_motor, rho)
        p_total = self.n_rotors * v_motor * i_motor + self.p_aux
        return OperatingPoint(
            duty=duty,
            omega=omega,
            thrust=self.prop.k_thrust(rho) * omega**2,
            torque=self.prop.k_torque(rho) * omega**2,
            i_motor=i_motor,
            v_motor=v_motor,
            v_bus=v_bus,
            i_bus=p_total / v_bus if v_bus > 0 else 0.0,
            n_rotors=self.n_rotors,
            p_aux=self.p_aux,
        )

    def at_duty(self, duty: float, v_source: float, r_source: float, rho: float) -> OperatingPoint | None:
        """Operating point for a commanded duty. None if the bus voltage collapses."""
        if not 0.0 <= duty <= 1.0:
            raise ValueError("duty must be within [0, 1]")
        if r_source == 0.0:
            return self._point(duty, v_source, rho)

        def surplus(v_bus: float) -> float:
            p = self._point(duty, v_bus, rho)
            return v_bus * (v_source - v_bus) / r_source - (p.n_rotors * p.v_motor * p.i_motor + self.p_aux)

        lo = 0.5 * v_source  # maximum-power-transfer point; stable branch lies above it
        if surplus(lo) < 0.0:
            return None
        v_bus = brentq(surplus, lo, v_source, xtol=1e-9, rtol=1e-12)
        return self._point(duty, v_bus, rho)

    def for_thrust(self, thrust: float, v_source: float, r_source: float, rho: float) -> OperatingPoint | None:
        """Operating point giving ``thrust`` per rotor, solved in closed form.
        None if it needs more than full duty or the bus voltage would collapse."""
        omega = math.sqrt(thrust / self.prop.k_thrust(rho))
        torque = self.prop.k_torque(rho) * omega**2
        i_motor = self.motor.i0(omega) + torque / self.motor.kt
        v_motor = self.motor.ke * omega + i_motor * self.r_circuit
        p_total = self.n_rotors * v_motor * i_motor + self.p_aux
        if r_source == 0.0:
            v_bus = v_source
        else:
            disc = v_source**2 - 4.0 * r_source * p_total
            if disc < 0.0:
                return None
            v_bus = 0.5 * (v_source + math.sqrt(disc))
        duty = v_motor / v_bus
        if duty > 1.0:
            return None
        return OperatingPoint(
            duty=duty,
            omega=omega,
            thrust=thrust,
            torque=torque,
            i_motor=i_motor,
            v_motor=v_motor,
            v_bus=v_bus,
            i_bus=p_total / v_bus,
            n_rotors=self.n_rotors,
            p_aux=self.p_aux,
        )
