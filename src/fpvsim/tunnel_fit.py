"""Airframe drag and rotor drag from wind-tunnel balance data.

Input: a balance CSV (tunnel.BALANCE_COLUMNS: props state, speed, alpha,
beta, rpm, air density, body-axis forces and moments about the CG), from a
real tunnel after the usual wall, blockage and tare corrections, or from
``fpvsim tunnel --synthetic``.

Model (the flight model's own, dynamics.py), with k = 1/2 rho |v| and the
body-axis air velocity (u, v, w) from speed, alpha and beta:

* props removed, per axis:  F_x = -k u S_x,  F_y = -k v S_y,  F_z = -k w S_z
  and about the CG  M_y = -k u (S_x z_x) + k w (S_z x_z),
                    M_x = -k w (S_z y_z) + k v (S_y z_y)
  S are the total drag areas (frame plus parts with their own drag) and
  x_z, y_z, z_x, z_y the positions of the drag centres relative to the CG.
  Each line is linear in its unknowns.
* props at fixed rpm, edgewise (alpha = 0): the body-x force adds the rotors'
  in-plane force, which in the oblique-flow model is linear in the flap
  fraction f: F_x = -k u S_x + sum_i [H_rigid,i + f (H_free,i - H_rigid,i)]_x.
  Fitted together with the props-removed rows, so S_x is shared.

Ordinary least squares with HC3 standard errors (sysid.py); positions from
the moment fits are ratios of two estimates, with first-order propagated
uncertainty. Thrust, side force and the moments with props spinning are not
used (they would mix the rotor model's thrust error into the drag).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .design import Aircraft
from .rotor_ff import anchored_rotor
from .sysid import Fit, _ols
from .tunnel import body_velocity


@dataclass(frozen=True)
class Estimate:
    value: float
    u: float


@dataclass
class TunnelFit:
    cda: dict[str, Estimate]  # x, y, z: total drag areas, m^2
    centre: dict[str, Estimate]  # x (from M_y with F_z), y (from M_x with F_z), z (from M_y with F_x), m from the CG
    flap_fraction: Estimate | None
    fits: dict[str, Fit]
    n_off: int
    n_spin: int
    residuals: dict[str, tuple[np.ndarray, np.ndarray]]  # name -> (measured, model)


def _ratio(a: float, sa: float, b: float, sb: float, cov: float = 0.0) -> Estimate:
    r = a / b
    var = (sa / b) ** 2 + (a * sb / b**2) ** 2 - 2.0 * a / b**3 * cov
    return Estimate(r, math.sqrt(max(var, 0.0)))


def fit_tunnel(data: dict[str, np.ndarray], ac: Aircraft) -> TunnelFit:
    """Identify drag areas, drag centres and the flap fraction (if the prop has blade geometry)."""
    props = np.round(data["props"]).astype(int)
    off = props == 0
    spin = props == 2
    if off.sum() < 4:
        raise ValueError("need at least four props-removed rows for the airframe drag")
    V, alpha, beta, rho = data["speed"], data["alpha"], data["beta"], data["rho"]
    uvw = np.array([body_velocity(V[i], alpha[i], beta[i]) for i in range(len(V))])
    u, v, w = uvw[:, 0], uvw[:, 1], uvw[:, 2]
    k = 0.5 * rho * V
    fits: dict[str, Fit] = {}
    residuals = {}

    # x force: props removed and props spinning together (shared S_x)
    rotor = None
    if spin.any():
        if ac.powertrain.prop.blade is None:
            raise ValueError("props-spinning rows need a prop with blade geometry (oblique-flow model)")
        rigid = anchored_rotor(ac.powertrain.prop, 0.0)
        free = anchored_rotor(ac.powertrain.prop, 1.0)
        rotor = (rigid, free)
    rows = np.nonzero(off | spin)[0]
    X1 = -k[rows] * u[rows]
    X2 = np.zeros(len(rows))
    offset = np.zeros(len(rows))
    spins = [1.0 if r.spin == "cw" else -1.0 for r in ac.rotors]
    for j, i in enumerate(rows):
        if props[i] == 2:
            omega = data["rpm"][i]
            hub = (u[i], v[i], w[i])
            h_rigid = sum(rotor[0].loads(hub, omega, s, rho[i])["force"][0] for s in spins)
            h_free = sum(rotor[1].loads(hub, omega, s, rho[i])["force"][0] for s in spins)
            offset[j] = h_rigid
            X2[j] = h_free - h_rigid
    y = data["fx"][rows] - offset
    if spin.any():
        fx = _ols(np.column_stack([X1, X2]), y, ("S_x", "f"))
        flap = Estimate(fx.values["f"], fx.stderr["f"])
    else:
        fx = _ols(X1[:, None], y, ("S_x",))
        flap = None
    fits["fx"] = fx
    model_fx = X1 * fx.values["S_x"] + (X2 * fx.values["f"] if flap else 0.0) + offset
    residuals["fx"] = (data["fx"][rows], model_fx)

    o = np.nonzero(off)[0]
    fz = _ols((-k[o] * w[o])[:, None], data["fz"][o], ("S_z",))
    fits["fz"] = fz
    residuals["fz"] = (data["fz"][o], -k[o] * w[o] * fz.values["S_z"])
    cda = {"x": Estimate(fx.values["S_x"], fx.stderr["S_x"]), "z": Estimate(fz.values["S_z"], fz.stderr["S_z"])}
    has_beta = np.abs(beta[o]).max() > 1e-6
    if has_beta:
        fy = _ols((-k[o] * v[o])[:, None], data["fy"][o], ("S_y",))
        fits["fy"] = fy
        residuals["fy"] = (data["fy"][o], -k[o] * v[o] * fy.values["S_y"])
        cda["y"] = Estimate(fy.values["S_y"], fy.stderr["S_y"])

    # pitching moment: M_y = -k u A + k w B, A = S_x z_x, B = S_z x_z
    my = _ols(np.column_stack([-k[o] * u[o], k[o] * w[o]]), data["my"][o], ("A", "B"))
    fits["my"] = my
    residuals["my"] = (data["my"][o], -k[o] * u[o] * my.values["A"] + k[o] * w[o] * my.values["B"])
    centre = {
        "z": _ratio(my.values["A"], my.stderr["A"], cda["x"].value, cda["x"].u),
        "x": _ratio(my.values["B"], my.stderr["B"], cda["z"].value, cda["z"].u),
    }
    if has_beta:  # rolling moment: M_x = -k w C + k v D, C = S_z y_z, D = S_y z_y
        mx = _ols(np.column_stack([-k[o] * w[o], k[o] * v[o]]), data["mx"][o], ("C", "D"))
        fits["mx"] = mx
        residuals["mx"] = (data["mx"][o], -k[o] * w[o] * mx.values["C"] + k[o] * v[o] * mx.values["D"])
        centre["y"] = _ratio(mx.values["C"], mx.stderr["C"], cda["z"].value, cda["z"].u)
    return TunnelFit(cda, centre, flap, fits, int(off.sum()), int(spin.sum()), residuals)


def frame_values(fit: TunnelFit, ac: Aircraft) -> dict:
    """Values for the frame file: the fitted totals minus the parts' own drag
    (at their nominal values) and the frame's drag centre in the mount-origin
    frame, from the area-weighted centres."""
    cg = ac.mass_props.cg
    parts = ac.extras.drag_points  # positions in the mount-origin frame
    out = {}
    for axis, k in (("x", 0), ("y", 1), ("z", 2)):
        if axis in fit.cda:
            parts_area = sum(a[k] for _, a in parts)
            out[f"cda_{axis}"] = Estimate(fit.cda[axis].value - parts_area, fit.cda[axis].u)
    centre = list(ac.extras.cda_center if ac.extras.cda_center is not None else cg)
    # z of the x-drag centre: S_x z_x = S_frame,x (z_f - z_cg) + sum S_i,x (z_i - z_cg)
    for coord, axis_area, k in (("z", "x", 2), ("x", "z", 0), ("y", "z", 1)):
        if coord not in fit.centre or f"cda_{axis_area}" not in out:
            continue
        idx = {"x": 0, "y": 1, "z": 2}[axis_area]
        total = fit.cda[axis_area].value * fit.centre[coord].value
        parts_moment = sum(a[idx] * (p[k] - cg[k]) for p, a in parts)
        frame_area = out[f"cda_{axis_area}"].value
        if frame_area > 0.0:
            centre[k] = cg[k] + (total - parts_moment) / frame_area
            out[f"centre_{coord}"] = Estimate(float(centre[k]), fit.centre[coord].u * fit.cda[axis_area].value / frame_area)
    out["drag_center"] = tuple(float(c) for c in centre)
    return out
