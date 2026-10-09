"""Rotor in oblique flow: blade element theory over radius and azimuth.

Forward flight, climb, descent, the vortex ring and windmill states, and a
slowly turning or stopped prop, for one rotor of known blade geometry and
airfoil (the same inputs as the axial BEMT in bemt.py).

Normalisation. Rotorcraft use the tip speed Omega R, but a prop at idle in
a fast dive or a punch-out coast has Omega R small against the air speed,
and a stopped prop in a wind tunnel has none. The tables therefore use the
total reference speed

    V_ref = sqrt((Omega R)^2 + V_e^2 + V_c^2)

with coordinates mu = V_e / V_ref (edgewise air speed of the hub, 0..1)
and lambda = V_c / V_ref (climb speed along the thrust axis, -1..1), and
coefficients on q = rho A V_ref^2 (moments on q R):

    C_T  thrust, along the thrust axis
    C_H  in-plane force opposing the edgewise motion (the rotor drag)
    C_Y  in-plane side force, perpendicular to the edgewise motion
    C_Q  shaft torque / R, opposing the rotation
    C_Mx hub moment / R about the direction of edgewise motion (rolling)
    C_My hub moment / R about the in-plane perpendicular (pitching)
    C_Hf extra rotor drag if the blades flapped freely (see below)
    inflow  (V_c + v_0) / V_ref

The usual advance ratio and inflow ratio are mu / s and lambda / s with s
= Omega R / V_ref = sqrt(1 - mu^2 - lambda^2); in hover and normal flight
s is close to 1 and the two normalisations nearly agree. Grid points
outside the unit circle are evaluated on it (a stopped prop).

Tables are computed for a rotor spinning counter-clockwise seen from the
thrust side; a clockwise rotor is its mirror image across the plane of the
thrust axis and the edgewise motion, so C_Y and C_Mx change sign and the
rest stay (AnchoredRotor).

Blade element (per unit span, B blades averaged over azimuth psi, measured
from the direction of travel e1 towards e2 = up x e1):

    U_T = Omega r - V_e sin psi      tangential, CCW rotor
    U_R = V_e cos psi                radial
    U_P = V_c + v_i(r, psi)          through the disk, downwards
    lift  1/2 rho (U_T^2 + U_P^2) c Cl(alpha) F,   alpha = theta(r) - atan2(U_P, U_T)
    drag  1/2 rho c Cd |W| W,  along the full relative air velocity W

with the polar of bemt.py (flat plate beyond stall and in reverse flow, U_T
< 0, on the retreating side). F is the Prandtl tip-loss factor. Induced
velocity: uniform part v_0 from momentum theory plus the Drees linear
distribution v_i = v_0 (1 - k_x (r/R) cos psi) (more inflow at the rear of
the disk). For v_0:

* Glauert's momentum theory, T = 2 rho A v_0 sqrt(V_e^2 + (V_c + v_0)^2),
  in climb, hover and forward flight;
* in axial descent, where momentum theory has no valid solution between
  V_c/v_h = 0 and -2 (vortex ring state), the empirical induced-velocity
  curve compiled by Leishman, Principles of Helicopter Aerodynamics,
  2nd ed., ch. 2, normalised to 1 in hover; momentum theory again below
  V_c/v_h = -2 (windmill brake state);
* with edgewise speed the wake is blown off the disk, so the descent value
  blends into Glauert's as V_e/v_h grows: in full up to vrs_extent(x)
  (0.7 v_h at most, enclosing the region where Glauert's equation folds
  and has no continuous solution), gone by twice that;
* no induced velocity when the blades give no positive thrust (a
  windmilling or stopped prop): the blade elements alone.

v_h = sqrt(T / (2 rho A)) depends on the thrust, so v_0 and the blade
loads are iterated to a fixed point.

Blade flexibility: the blade element loads are for rigid blades, which
carry the advancing-side lift as a hub moment. A freely flapping (hinged)
rotor would instead tilt its disk back by the classical longitudinal
flapping angle a1 = 2 mu (4 theta_75 / 3 - lambda) / (1 - mu^2 / 2)
(Johnson 1980; Leishman 2006, ch. 4, rotorcraft mu and lambda), which turns
part of the thrust into rotor drag, C_Hf = C_T a1, and relieves the hub
moment. The classical solution holds for mu < 0.5; beyond that, and for
|lambda| > 0.5, a1 is held at its value at those limits, and it fades out
as the rotor stops (Omega R < V_ref / 2), since flapping needs the
centrifugal stiffening of a turning blade. Plastic props lie
between rigid and freely flapping; AnchoredRotor blends the two with a
flap fraction (0 = rigid, 1 = fully flapping). Lateral flapping is
neglected.

What is not modelled: the thrust fluctuations in the vortex ring state
(propwash), unsteady and three-dimensional stall (including the stall delay
of rotating blades), and Reynolds and Mach effects. Below a rotorcraft
advance ratio of about 0.5 the model is a standard one; beyond it (low rpm,
high speed) most of the blade is stalled or in reverse flow and the
results rest on the flat-plate polar, so the flight report flags it.

References: Glauert (1926); Drees (1949) as given in Leishman (2006),
ch. 3 and 10; Johnson, "Helicopter Theory" (1980), ch. 5; Hoerner,
"Fluid-Dynamic Drag" (1965) for the flat plate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bemt import FLAT_PLATE_CN, POST_STALL, Airfoil, BladeGeometry, polar

MU_GRID = np.round(np.arange(0.0, 1.0001, 0.02), 4)  # V_e / V_ref
LAMBDA_GRID = np.round(np.arange(-1.0, 1.0001, 0.02), 4)  # V_c / V_ref
INFLOW_TOL = 2e-5  # |v_0 - target| / V_ref for convergence, about 0.002 m/s at a 5-inch prop's hover tip speed
CLASSICAL_LIMIT = 0.5  # rotorcraft mu or |lambda| beyond which the results rest on the flat-plate polar
VRS_COEFFS = (1.15, -1.125, -1.372, -1.718, -0.655)  # v_i/v_h polynomial in V_c/v_h, -2 <= x <= 0


def axial_induced(x: np.ndarray) -> np.ndarray:
    """v_i / v_h against x = V_c / v_h along the axis: momentum theory in climb
    and windmill brake state, the empirical vortex-ring curve between.

    The polynomial gives 1.0226 at x = -2 where momentum theory gives 1; a
    linear correction in x (zero at hover) closes that 2 % gap so the curve is
    continuous, which the fixed-point solve for v_0 needs."""
    x = np.asarray(x, dtype=float)
    kappa, k1, k2, k3, k4 = VRS_COEFFS

    def poly(z):
        return (kappa + k1 * z + k2 * z**2 + k3 * z**3 + k4 * z**4) / kappa

    climb = -x / 2 + np.sqrt(x * x / 4 + 1)
    windmill = -x / 2 - np.sqrt(np.clip(x * x / 4 - 1, 0.0, None))
    vrs = poly(x) + (x / -2.0) * (1.0 - poly(-2.0))
    return np.where(x >= 0, climb, np.where(x <= -2, windmill, vrs))


def vrs_extent(x: np.ndarray) -> np.ndarray:
    """Edgewise speed (in v_h) up to which the vortex-ring value is used in
    full, against x = V_c / v_h; it fades out by twice this value.

    It encloses, with margin, the region where Glauert's equation has three
    roots (a fold, so no continuous momentum solution exists): up to
    V_e/v_h = 0.62 near x = -1.8, falling as about 1/|x| in the windmill
    brake state. Zero in climb and hover, where momentum theory holds."""
    x = np.asarray(x, dtype=float)
    return np.where(x >= 0.0, 0.0, np.where(x >= -2.0, 0.7 * np.sqrt(np.clip(-x, 0.0, None) / 2.0),
                                            1.4 / np.maximum(-x, 1e-9)))


def glauert(x: np.ndarray, y: np.ndarray, iterations: int = 60) -> np.ndarray:
    """Root k = v_0 / v_h of Glauert's k sqrt(y^2 + (x + k)^2) = 1, by
    bisection on [0, 2 + |x|]; unique outside the fold (see vrs_extent)."""
    x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    lo = np.zeros(x.shape)
    hi = 2.0 + np.abs(x)
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        above = mid * np.sqrt(y * y + (x + mid) ** 2) > 1.0
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return 0.5 * (lo + hi)


def induced_velocity(v_c: np.ndarray, v_e: np.ndarray, v_h: np.ndarray) -> np.ndarray:
    """Uniform induced velocity v_0 for given climb speed, edgewise speed and
    hover induced velocity (all in the same units): the axial curve
    (axial_induced) inside the vortex-ring region, Glauert outside it, with
    a smooth (cosine) blend in between."""
    v_h = np.maximum(v_h, 1e-9)
    x, y = v_c / v_h, v_e / v_h
    extent = vrs_extent(x)
    s = y / np.maximum(extent, 1e-12)
    weight = np.where(s <= 1.0, 1.0, np.where(s >= 2.0, 0.0, 0.5 * (1.0 + np.cos(np.pi * (s - 1.0)))))
    weight = np.where(x < 0.0, weight, 0.0)
    return v_h * (weight * axial_induced(x) + (1.0 - weight) * glauert(x, y))


@dataclass(frozen=True)
class RotorTables:
    mu: np.ndarray  # grid of V_e / V_ref, ascending, uniform
    lam: np.ndarray  # grid of V_c / V_ref, ascending, uniform
    ct: np.ndarray  # [mu, lambda], on rho A V_ref^2
    ch: np.ndarray
    cy: np.ndarray
    cq: np.ndarray  # on rho A V_ref^2 R
    cmx: np.ndarray
    cmy: np.ndarray
    chf: np.ndarray  # rotor drag added by free flapping, per unit flap fraction
    inflow: np.ndarray  # (V_c + v_0) / V_ref
    converged: np.ndarray  # bool [mu, lambda]


def compute_tables(geom: BladeGeometry, foil: Airfoil, n_r: int = 24, n_psi: int = 36,
                   mu_grid: np.ndarray = MU_GRID, lam_grid: np.ndarray = LAMBDA_GRID,
                   iterations: int = 400, chunk: int = 6) -> RotorTables:
    """All coefficients on the (mu, lambda) grid, normalised with R = 1, V_ref = 1, rho = 1
    (computed a few mu rows at a time to keep the work arrays small)."""
    mu_grid = np.asarray(mu_grid, dtype=float)
    parts = [_compute_rows(geom, foil, n_r, n_psi, mu_grid[k:k + chunk], np.asarray(lam_grid, dtype=float), iterations)
             for k in range(0, len(mu_grid), chunk)]
    fields = {name: np.concatenate([getattr(p, name) for p in parts]) for name in RotorTables.__dataclass_fields__
              if name not in ("mu", "lam")}
    return RotorTables(mu=mu_grid, lam=np.asarray(lam_grid, dtype=float), **fields)


def _compute_rows(geom: BladeGeometry, foil: Airfoil, n_r: int, n_psi: int, mu_grid: np.ndarray,
                  lam_grid: np.ndarray, iterations: int) -> RotorTables:
    R = geom.radius
    edges = np.linspace(geom.r_start / R, 1.0, n_r + 1)
    r = 0.5 * (edges[1:] + edges[:-1])  # r / R
    dr = np.diff(edges)
    chord = np.array([geom.chord_at(x * R) for x in r]) / R
    theta = np.array([geom.theta_at(x * R) for x in r])
    psi = (np.arange(n_psi) + 0.5) * 2 * np.pi / n_psi
    B = geom.blades
    area = math.pi  # A / R^2

    MU, LAM = np.meshgrid(np.asarray(mu_grid, dtype=float), np.asarray(lam_grid, dtype=float), indexing="ij")
    radius = np.hypot(MU, LAM)
    shrink = np.where(radius > 1.0, 1.0 / np.maximum(radius, 1e-12), 1.0)  # outside the unit circle: on it
    MUe, LAMe = MU * shrink, LAM * shrink
    S = np.sqrt(np.clip(1.0 - MUe**2 - LAMe**2, 0.0, None))  # Omega R / V_ref
    mu = MUe[..., None, None]
    lam_c = LAMe[..., None, None]
    s_tip = S[..., None, None]
    mu_rot = np.where(S > 1e-9, MUe / np.maximum(S, 1e-9), np.inf)[..., None, None]  # rotorcraft advance ratio
    rr = r[None, None, :, None]
    sp, cp = np.sin(psi)[None, None, None, :], np.cos(psi)[None, None, None, :]
    c = chord[None, None, :, None]
    th = theta[None, None, :, None]
    weight = (dr[None, None, :, None] * B / n_psi)  # sum over psi of B blades / n_psi

    u_t = s_tip * rr - mu * sp
    u_r = mu * cp

    def loads(v0_now):
        v0 = v0_now[..., None, None]
        lam_total = lam_c + v0
        chi = np.arctan2(mu, np.maximum(lam_total, 1e-6))  # wake skew angle
        with np.errstate(invalid="ignore"):
            kx = (4.0 / 3.0) * (1.0 - np.cos(chi) - 1.8 * np.minimum(mu_rot, 10.0) ** 2) / np.maximum(np.sin(chi), 1e-6)
        kx = np.clip(np.where(chi > 1e-6, kx, 0.0), 0.0, 2.0)
        u_p = lam_c + v0 * (1.0 - kx * rr * cp)
        phi = np.arctan2(u_p, u_t)
        cl, cd = polar(foil, th - phi)
        # Prandtl tip loss with the mean inflow angle at each radius
        phi_mean = np.arctan2(np.abs(lam_total), s_tip * rr)
        f = 0.5 * B * (1.0 - rr) / (rr * np.maximum(np.sin(phi_mean), 1e-6))
        tip = 2.0 / np.pi * np.arccos(np.clip(np.exp(-f), 0.0, 1.0))
        wn2 = u_t * u_t + u_p * u_p
        wn = np.sqrt(wn2)
        w = np.sqrt(wn2 + u_r * u_r)
        lift = 0.5 * wn2 * c * cl * tip
        drag_k = 0.5 * c * cd * w
        # force on the blade per unit span, in (t, r, up) components; lift is perpendicular to (U_T, U_P)
        f_up = lift * u_t / np.maximum(wn, 1e-9) - drag_k * u_p
        f_t = -lift * u_p / np.maximum(wn, 1e-9) - drag_k * u_t
        f_r = -drag_k * u_r
        return f_up, f_t, f_r

    # damped fixed point on v_0; a cell whose update changes sign (oscillates) gets stronger damping
    v0 = 0.05 * S
    relax = np.full(MU.shape, 0.3)
    last = np.zeros(MU.shape)
    done = np.zeros(MU.shape, dtype=bool)
    for _ in range(iterations):
        f_up, _, _ = loads(v0)
        ct = np.sum(f_up * weight, axis=(2, 3)) / area
        v_h = np.sqrt(np.maximum(ct, 0.0) / 2.0)
        target = np.where(ct > 0.0, induced_velocity(LAMe, MUe, v_h), 0.0)
        step = relax * (target - v0)
        relax = np.where(step * last < 0.0, np.maximum(0.5 * relax, 0.01), relax)
        last = step
        done = np.abs(target - v0) < INFLOW_TOL
        v0 = v0 + step
        if done.all():
            break

    f_up, f_t, f_r = loads(v0)
    # tangential and radial unit vectors for the CCW rotor, in (e1, e2)
    t1, t2 = -sp, cp
    r1, r2 = cp, sp
    fx = f_t * t1 + f_r * r1  # along e1
    fy = f_t * t2 + f_r * r2  # along e2
    thrust = np.sum(f_up * weight, axis=(2, 3))
    force_e1 = np.sum(fx * weight, axis=(2, 3))
    force_e2 = np.sum(fy * weight, axis=(2, 3))
    torque = -np.sum(f_t * rr * weight, axis=(2, 3))
    # hub moments of the thrust distribution: M = sum r x F_up, with r = rr (cos psi, sin psi, 0), F along up
    m_e1 = np.sum(f_up * rr * sp * weight, axis=(2, 3))
    m_e2 = -np.sum(f_up * rr * cp * weight, axis=(2, 3))
    inflow = LAMe + v0
    # classical longitudinal flapping in rotorcraft ratios, held at the limit of its validity
    theta75 = geom.theta_at(0.75 * R)
    with np.errstate(divide="ignore", invalid="ignore"):
        mu_c = np.where(S > 1e-9, MUe / S, np.where(MUe > 0.0, np.inf, 0.0))
        lam_tot_c = np.where(S > 1e-9, inflow / S, np.sign(inflow) * np.inf)
    mu_c = np.minimum(mu_c, CLASSICAL_LIMIT)
    lam_tot_c = np.clip(np.nan_to_num(lam_tot_c), -CLASSICAL_LIMIT, CLASSICAL_LIMIT)
    # flapping needs the centrifugal stiffening of a turning blade: fade it out as the rotor stops
    # (Omega R below half of V_ref, i.e. rotorcraft mu above about 1.7)
    a1 = 2.0 * mu_c * (4.0 * theta75 / 3.0 - lam_tot_c) / (1.0 - 0.5 * mu_c**2) * np.clip(S / 0.5, 0.0, 1.0)
    ct = thrust / area
    return RotorTables(
        mu=np.asarray(mu_grid, dtype=float), lam=np.asarray(lam_grid, dtype=float),
        ct=ct, ch=-force_e1 / area, cy=force_e2 / area, cq=torque / area,
        cmx=m_e1 / area, cmy=m_e2 / area, chf=np.maximum(ct, 0.0) * a1, inflow=inflow, converged=done,
    )


def _cache_key(geom: BladeGeometry, foil: Airfoil) -> str:
    payload = {
        "R": geom.radius, "hub": geom.hub_radius, "r": list(map(float, geom.r_over_R)), "c": list(map(float, geom.chord)),
        "pitch": geom.pitch, "B": geom.blades, "foil": [foil.cl_alpha, foil.alpha0, foil.cl_max, foil.cl_min,
                                                         foil.cd_min, foil.cl_cd_min, foil.k_cd],
        "post_stall": [*POST_STALL, FLAT_PLATE_CN],
        "mu": list(map(float, MU_GRID)), "lam": list(map(float, LAMBDA_GRID)), "version": 7,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


_MEMORY: dict[str, RotorTables] = {}


def rotor_tables(geom: BladeGeometry, foil: Airfoil) -> RotorTables:
    """Tables for this blade, cached in memory and on disk (FPVSIM_CACHE, default ~/.cache/fpvsim)."""
    key = _cache_key(geom, foil)
    if key in _MEMORY:
        return _MEMORY[key]
    cache_dir = Path(os.environ.get("FPVSIM_CACHE", Path.home() / ".cache" / "fpvsim"))
    path = cache_dir / f"rotor_ff_{key}.npz"
    tables = None
    if path.exists():
        try:
            with np.load(path) as data:
                tables = RotorTables(**{k: data[k] for k in RotorTables.__dataclass_fields__})
        except (OSError, ValueError, KeyError):
            tables = None
    if tables is None:
        tables = compute_tables(geom, foil)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp.npz")
            np.savez(tmp, **{k: getattr(tables, k) for k in RotorTables.__dataclass_fields__})
            os.replace(tmp, path)
        except OSError:
            pass
    _MEMORY[key] = tables
    return tables


# ----------------------------------------------------------------- run time

AXIAL_ANCHOR_MAX = 0.2  # rotorcraft lambda (J / pi) up to which the tables are anchored to the axial curves


def anchor_factors(tables: RotorTables, J: np.ndarray, ct_axial: np.ndarray, cp_axial: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Per-lambda factors that make the tables reproduce the axial curves at mu = 0.

    The axial curves (test stand or BEMT, with ct_scale and cp_scale applied)
    stay the reference for thrust and torque; the oblique-flow model supplies
    how they change with edgewise and off-design flow. In axial flow lambda =
    V_c / sqrt((Omega R)^2 + V_c^2), so J = pi lambda / sqrt(1 - lambda^2),
    C_T = Ct (4 / pi^3) (1 - lambda^2) and C_Q = Cp (4 / pi^4) (1 - lambda^2).
    Matched for 0 <= J / pi <= min(0.2, J_max / pi) wherever the rotor still
    produces at least 20 % of its static thrust; held constant outside
    (descent has no axial data)."""
    lam = tables.lam
    i0 = int(np.argmin(np.abs(lam)))
    ct_ff, cq_ff = tables.ct[0], tables.cq[0]
    s2 = np.clip(1.0 - lam**2, 0.0, None)
    lam_rot = np.where(s2 > 0.0, lam / np.sqrt(np.maximum(s2, 1e-12)), np.inf)
    J_here = np.pi * lam_rot
    with np.errstate(invalid="ignore"):
        target_t = np.interp(J_here, J, ct_axial) * 4.0 / np.pi**3 * s2
        target_q = np.interp(J_here, J, cp_axial) * 4.0 / np.pi**4 * s2
    usable = (lam_rot >= -1e-9) & (lam_rot <= min(AXIAL_ANCHOR_MAX, float(J[-1]) / np.pi) + 1e-9)
    usable &= (ct_ff > 0.2 * ct_ff[i0]) & (target_t > 0.2 * target_t[i0]) & (cq_ff > 0.0) & (target_q > 0.0)
    if not usable[i0]:
        raise ValueError("oblique-flow tables have no static thrust to anchor to")
    k_t = np.interp(lam, lam[usable], target_t[usable] / ct_ff[usable])
    k_q = np.interp(lam, lam[usable], target_q[usable] / cq_ff[usable])
    return k_t, k_q


class AnchoredRotor:
    """One prop in oblique flow, ready for the flight model: tables anchored to
    the axial curves, the flap fraction applied, and both spin directions.

    Each cell of the lookup holds (C_T, C_H + f C_Hf, C_Y, C_Q, (1 - f) C_Mx,
    (1 - f) C_My) with the sign convention of the spin direction. Free
    flapping relieves both hub moments: the rolling moment by the
    longitudinal tilt a1 (whose rotor drag is C_Hf), the pitching moment by a
    lateral tilt whose side force is not modelled (it is opposite for the two
    spin directions and cancels across a quad)."""

    def __init__(self, tables: RotorTables, radius: float, J: np.ndarray, ct_axial: np.ndarray,
                 cp_axial: np.ndarray, flap_fraction: float):
        self.tables = tables
        self.radius = radius
        self.flap_fraction = f = float(flap_fraction)
        k_t, k_q = anchor_factors(tables, J, ct_axial, cp_axial)
        self.k_t, self.k_q = k_t, k_q
        kt = k_t[None, :]
        base = {
            "ct": tables.ct * kt,
            "ch": (tables.ch + f * tables.chf) * kt,
            "cy": tables.cy * kt,
            "cq": tables.cq * k_q[None, :],
            "cmx": (1.0 - f) * tables.cmx * kt,
            "cmy": (1.0 - f) * tables.cmy * kt,
        }
        self.coefficients = base
        self.mu0, self.dmu, self.n_mu = float(tables.mu[0]), float(tables.mu[1] - tables.mu[0]), len(tables.mu)
        self.lam0, self.dlam, self.n_lam = float(tables.lam[0]), float(tables.lam[1] - tables.lam[0]), len(tables.lam)
        # nested Python tuples for the inner loop; index 0: CCW (spin -1 in QuadModel), 1: CW (mirror)
        self.cells = []
        for h in (1.0, -1.0):
            grid = []
            for i in range(self.n_mu):
                grid.append([
                    (float(base["ct"][i, j]), float(base["ch"][i, j]), h * float(base["cy"][i, j]),
                     float(base["cq"][i, j]), h * float(base["cmx"][i, j]), float(base["cmy"][i, j]))
                    for j in range(self.n_lam)
                ])
            self.cells.append(grid)

    def lookup(self, cells: list, mu: float, lam: float) -> tuple:
        """Bilinear interpolation at (mu, lambda) = (V_e, V_c) / V_ref."""
        fm = (mu - self.mu0) / self.dmu
        if fm >= self.n_mu - 1:
            im, tm = self.n_mu - 2, 1.0
        elif fm <= 0.0:
            im, tm = 0, 0.0
        else:
            im = int(fm)
            tm = fm - im
        fl = (lam - self.lam0) / self.dlam
        if fl >= self.n_lam - 1:
            il, tl = self.n_lam - 2, 1.0
        elif fl <= 0.0:
            il, tl = 0, 0.0
        else:
            il = int(fl)
            tl = fl - il
        a, b = cells[im][il], cells[im][il + 1]
        c, d = cells[im + 1][il], cells[im + 1][il + 1]
        w00, w01, w10, w11 = (1 - tm) * (1 - tl), (1 - tm) * tl, tm * (1 - tl), tm * tl
        return tuple(w00 * p + w01 * q + w10 * r + w11 * s for p, q, r, s in zip(a, b, c, d))

    def loads(self, v_hub: tuple[float, float, float], omega: float, spin: float, rho: float) -> dict:
        """Loads of one rotor in body axes (FRD, thrust along -z) for the hub's
        air-relative velocity ``v_hub`` (body axes, m/s), rotor speed ``omega``
        (rad/s) and spin sign (+1 CW seen from above, as in QuadModel)."""
        vhx, vhy, vhz = v_hub
        omega_r = omega * self.radius
        v_e = math.hypot(vhx, vhy)
        v_c = -vhz
        v_ref2 = omega_r * omega_r + v_e * v_e + v_c * v_c
        v_ref = math.sqrt(v_ref2)
        mu, lam = (v_e / v_ref, v_c / v_ref) if v_ref > 1e-9 else (0.0, 0.0)
        ct, ch, cy, cq, cmx, cmy = self.lookup(self.cells[0 if spin < 0 else 1], mu, lam)
        q = rho * math.pi * self.radius**2 * v_ref2
        e1 = (vhx / v_e, vhy / v_e) if v_e > 1e-9 else (1.0, 0.0)
        e2 = (e1[1], -e1[0])
        return {
            "mu": mu, "lambda": lam,
            "mu_rotor": v_e / omega_r if omega_r > 0.0 else math.inf,
            "lambda_rotor": v_c / omega_r if omega_r > 0.0 else math.copysign(math.inf, v_c),
            "thrust": ct * q,
            "force": ((-ch * e1[0] + cy * e2[0]) * q, (-ch * e1[1] + cy * e2[1]) * q, -ct * q),
            "h_force": ch * q, "side_force": cy * q,
            "moment": ((cmx * e1[0] + cmy * e2[0]) * q * self.radius, (cmx * e1[1] + cmy * e2[1]) * q * self.radius, 0.0),
            "torque": cq * q * self.radius,
        }


def anchored_rotor(prop, flap_fraction: float) -> AnchoredRotor:
    """AnchoredRotor for a ``prop.Prop`` that carries its blade geometry."""
    geom, foil = prop.blade
    tables = rotor_tables(geom, foil)
    return AnchoredRotor(tables, prop.radius, np.asarray(prop.curves.J, dtype=float),
                         prop.ct_scale * np.asarray(prop.curves.ct, dtype=float),
                         prop.cp_scale * np.asarray(prop.curves.cp, dtype=float), flap_fraction)
