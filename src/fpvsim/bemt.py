"""Blade element momentum theory (BEMT) for a propeller in axial flow.

Used to estimate Ct(J) and Cp(J) from blade geometry when no test-stand data
exists, the same way propellers are sized before the first prototype.

For each annulus of radius r and width dr the induced axial velocity v is
found such that blade-element thrust equals momentum-theory thrust:

    phi    = atan((V + v) / (Omega r))           (swirl neglected)
    alpha  = theta(r) - phi
    dT_be  = B * 0.5 rho W^2 c (Cl cos phi - Cd sin phi) dr
    dT_mom = 4 pi r rho (V + v) v F dr
    dQ     = B * 0.5 rho W^2 c (Cl sin phi + Cd cos phi) r dr

F is the Prandtl tip-loss factor. The root is bracketed between v = 0 and the
inflow where the section reaches zero lift, so the solve always converges.

Assumptions and limits (also in docs/models.md):
* axial flow only, V >= 0; momentum theory is invalid in descent (vortex ring);
* swirl (tangential induction) neglected, typically a 1-3 % effect on props;
* one airfoil polar for the whole blade, no Reynolds or Mach dependence;
* post-stall behaviour is crude (lift saturates, drag keeps growing).

References: Glauert, "Airplane Propellers" (1935); Leishman, "Principles of
Helicopter Aerodynamics", 2nd ed. (2006), ch. 3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from .prop import PropCurves


@dataclass(frozen=True)
class Airfoil:
    cl_alpha: float  # 1/rad
    alpha0: float  # rad, zero-lift angle of attack
    cl_max: float
    cl_min: float
    cd_min: float
    cl_cd_min: float  # lift coefficient at minimum drag
    k_cd: float  # drag polar curvature

    def coefficients(self, alpha: float) -> tuple[float, float]:
        cl_linear = self.cl_alpha * (alpha - self.alpha0)
        cl = min(max(cl_linear, self.cl_min), self.cl_max)
        cd = self.cd_min + self.k_cd * (cl_linear - self.cl_cd_min) ** 2
        return cl, cd


@dataclass(frozen=True)
class BladeGeometry:
    radius: float  # m, tip radius
    hub_radius: float  # m
    r_over_R: np.ndarray  # stations, ascending
    chord: np.ndarray  # m, chord at each station
    pitch: float  # m, constant geometric pitch (helical blade)
    blades: int

    def chord_at(self, r: float) -> float:
        return float(np.interp(r / self.radius, self.r_over_R, self.chord))

    def theta_at(self, r: float) -> float:
        return math.atan(self.pitch / (2.0 * math.pi * r))

    @property
    def r_start(self) -> float:
        return max(self.hub_radius, float(self.r_over_R[0]) * self.radius)


def _tip_loss(blades: int, r: float, radius: float, phi: float) -> float:
    s = math.sin(phi)
    if s < 1e-9:
        return 1.0
    f = 0.5 * blades * (radius - r) / (r * s)
    return 2.0 / math.pi * math.acos(min(1.0, math.exp(-f)))


def _element(geom: BladeGeometry, foil: Airfoil, r: float, omega: float, v_axial: float, rho: float):
    """Thrust and torque per unit span at radius r. Returns (dT/dr, dQ/dr, v)."""
    c = geom.chord_at(r)
    theta = geom.theta_at(r)
    ut = omega * r
    B = geom.blades

    def blade_loads(v: float) -> tuple[float, float, float]:
        up = v_axial + v
        phi = math.atan2(up, ut)
        cl, cd = foil.coefficients(theta - phi)
        q = 0.5 * rho * (up * up + ut * ut) * c * B
        cphi, sphi = math.cos(phi), math.sin(phi)
        return q * (cl * cphi - cd * sphi), q * (cl * sphi + cd * cphi) * r, phi

    def residual(v: float) -> float:
        dt_be, _, phi = blade_loads(v)
        dt_mom = 4.0 * math.pi * r * rho * (v_axial + v) * v * _tip_loss(B, r, geom.radius, phi)
        return dt_be - dt_mom

    v_max = ut * math.tan(min(theta - foil.alpha0, 0.5 * math.pi - 1e-6)) - v_axial
    if v_max <= 0.0 or residual(0.0) <= 0.0:
        v = 0.0  # no positive induced flow: momentum balance not applicable
    else:
        v = brentq(residual, 0.0, v_max, xtol=1e-10, rtol=1e-12)
    dt, dq, _ = blade_loads(v)
    return dt, dq, v


def rotor_loads(
    geom: BladeGeometry,
    foil: Airfoil,
    omega: float,
    v_axial: float,
    rho: float,
    n_elements: int = 60,
) -> tuple[float, float]:
    """Total thrust (N) and shaft torque (N m) by midpoint integration."""
    if v_axial < 0.0:
        raise ValueError("BEMT is not valid in descent (v_axial < 0)")
    edges = np.linspace(geom.r_start, geom.radius, n_elements + 1)
    thrust = torque = 0.0
    for r0, r1 in zip(edges[:-1], edges[1:]):
        dt, dq, _ = _element(geom, foil, 0.5 * (r0 + r1), omega, v_axial, rho)
        thrust += dt * (r1 - r0)
        torque += dq * (r1 - r0)
    return thrust, torque


def coefficient_curves(
    geom: BladeGeometry,
    foil: Airfoil,
    J_values: np.ndarray,
    rpm_ref: float = 20000.0,
    rho: float = 1.225,
    n_elements: int = 60,
) -> PropCurves:
    """Ct(J) and Cp(J). Without Reynolds or Mach effects the result does not
    depend on rpm_ref or rho; they only set the evaluation point."""
    n = rpm_ref / 60.0
    omega = 2.0 * math.pi * n
    D = 2.0 * geom.radius
    ct = np.empty(len(J_values))
    cp = np.empty(len(J_values))
    for i, J in enumerate(J_values):
        thrust, torque = rotor_loads(geom, foil, omega, J * n * D, rho, n_elements)
        ct[i] = thrust / (rho * n**2 * D**4)
        cp[i] = 2.0 * math.pi * torque / (rho * n**2 * D**5)
    return PropCurves(np.asarray(J_values, dtype=float), ct, cp)
