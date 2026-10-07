"""System identification: model parameters from test data.

Each fit is ordinary least squares on a model that is linear in its
parameters. Standard errors use the HC3 heteroscedasticity-consistent
covariance (MacKinnon & White, 1985), because test-stand noise usually grows
with the reading (load cells, current shunts) and the classic s^2 (A^T A)^-1
would then understate the uncertainty. Measured parameters thus enter the
design with an honest uncertainty.

Test data is CSV with "name [unit]" headers, e.g. "thrust [gf]"; units are
converted to SI on read.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import units

_HEADER = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\]\s*$")


def read_csv(path: str | Path) -> dict[str, np.ndarray]:
    """Read a test-data CSV into SI arrays keyed by column name."""
    with Path(path).open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        columns = []
        for cell in header:
            match = _HEADER.match(cell)
            if not match:
                raise ValueError(f"{path}: column {cell!r} must look like 'name [unit]'")
            columns.append((match.group(1), match.group(2)))
        rows = [[float(x) for x in row] for row in reader if row]
    data = np.array(rows, dtype=float)
    return {name: np.array([units.to_si(v, unit) for v in data[:, i]]) for i, (name, unit) in enumerate(columns)}


@dataclass(frozen=True)
class Fit:
    values: dict[str, float]
    stderr: dict[str, float]
    n: int
    residual_rms: float
    r2: float

    def u_rel(self, key: str) -> float:
        return self.stderr[key] / abs(self.values[key])


def _ols(A: np.ndarray, y: np.ndarray, names: tuple[str, ...]) -> Fit:
    n, k = A.shape
    if n <= k:
        raise ValueError(f"need more than {k} data points, got {n}")
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    bread = np.linalg.inv(A.T @ A)
    leverage = np.einsum("ij,jk,ik->i", A, bread, A)
    meat = (A * (resid / (1.0 - leverage))[:, None] ** 2).T @ A
    cov = bread @ meat @ bread  # HC3 sandwich estimator
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else 1.0
    return Fit(
        values=dict(zip(names, map(float, beta))),
        stderr=dict(zip(names, map(float, np.sqrt(np.diag(cov))))),
        n=n,
        residual_rms=math.sqrt(float(resid @ resid) / n),
        r2=r2,
    )


def fit_prop_static(omega: np.ndarray, thrust: np.ndarray, torque: np.ndarray, rho: float, diameter: float) -> dict[str, Fit]:
    """Static Ct and Cp from rpm, thrust and torque (T = kT w^2, Q = kQ w^2)."""
    mask = omega > 0
    w2 = omega[mask] ** 2
    fits = {"thrust": _ols(w2[:, None], thrust[mask], ("k",)), "torque": _ols(w2[:, None], torque[mask], ("k",))}
    to_ct = (2.0 * math.pi) ** 2 / (rho * diameter**4)
    to_cp = (2.0 * math.pi) ** 3 / (rho * diameter**5)  # Cp = 2 pi Cq
    out = {}
    for name, fit, factor in (("ct0", fits["thrust"], to_ct), ("cp0", fits["torque"], to_cp)):
        out[name] = Fit(
            values={name: fit.values["k"] * factor},
            stderr={name: fit.stderr["k"] * factor},
            n=fit.n,
            residual_rms=fit.residual_rms,
            r2=fit.r2,
        )
    return out


def fit_motor_no_load(voltage: np.ndarray, current: np.ndarray, omega: np.ndarray, rm: float) -> dict[str, Fit]:
    """Kv and the affine no-load current model from a no-load (no prop) sweep.

    Back-EMF: V - I Rm = Ke w  (through the origin)  ->  Kv = 1 / Ke
    Losses:   I0 = a + b w
    Rm must be measured separately (four-wire resistance measurement).
    """
    emf = _ols(omega[:, None], voltage - current * rm, ("ke",))
    ke = emf.values["ke"]
    kv = Fit({"kv": 1.0 / ke}, {"kv": emf.stderr["ke"] / ke**2}, emf.n, emf.residual_rms, emf.r2)
    losses = _ols(np.column_stack([np.ones_like(omega), omega]), current, ("i0_const", "i0_slope"))
    return {"kv": kv, "i0": losses}


def fit_motor_loaded(v_motor: np.ndarray, i_motor: np.ndarray, omega: np.ndarray) -> Fit:
    """Ke and circuit resistance from loaded points: V = Ke w + R I."""
    return _ols(np.column_stack([omega, i_motor]), v_motor, ("ke", "r_circuit"))
