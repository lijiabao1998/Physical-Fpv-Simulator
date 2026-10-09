"""Fixed-trajectory voltage-term feasibility; never identifies physical resistance."""

from __future__ import annotations

import math

import numpy as np


def restrict(time, error, current, start=None, stop=None):
    t, e, i = (np.asarray(x, dtype=float) for x in (time, error, current))
    if (
        t.ndim != 1
        or e.shape != t.shape
        or i.shape != t.shape
        or len(t) < 2
        or not all(np.isfinite(x).all() for x in (t, e, i))
        or np.any(np.diff(t) <= 0)
        or np.any(i < 0)
    ):
        raise ValueError("Expected finite increasing trace and nonnegative discharge current")
    start, stop = t[0] if start is None else start, t[-1] if stop is None else stop
    if not np.isfinite([start, stop]).all() or not t[0] <= start < stop <= t[-1]:
        raise ValueError("No extrapolation or changed comparison coverage")
    q = np.unique(np.r_[start, t[(t > start) & (t < stop)], stop])
    return q, np.interp(q, t, e), np.interp(q, t, i)


def coefficients(time, error, current, start=None, stop=None):
    t, e, i = restrict(time, error, current, start, stop)
    h = np.diff(t)
    duration = t[-1] - t[0]
    a = float(np.sum(h * (i[:-1] ** 2 + i[:-1] * i[1:] + i[1:] ** 2) / 3) / duration)
    b = float(
        np.sum(h * (2 * e[:-1] * i[:-1] + e[:-1] * i[1:] + e[1:] * i[:-1] + 2 * e[1:] * i[1:]) / 6)
        / duration
    )
    c = float(np.sum(h * (e[:-1] ** 2 + e[:-1] * e[1:] + e[1:] ** 2) / 3) / duration)
    # Independent quadrature of interpolated factors, not products at endpoints.
    nodes, weights = np.polynomial.legendre.leggauss(3)
    eq = e[:-1, None] + np.diff(e)[:, None] * (nodes + 1) / 2
    iq = i[:-1, None] + np.diff(i)[:, None] * (nodes + 1) / 2
    checks = [
        float(np.sum(h[:, None] * weights * x / 2) / duration) for x in (iq**2, eq * iq, eq**2)
    ]
    delta = max(abs(v - w) for v, w in zip((a, b, c), checks, strict=True))
    if not np.isfinite([a, b, c, delta]).all() or delta > 1e-12:
        raise ValueError("Exact-product versus Gauss integration check failed")
    return {
        "A_a2": a,
        "B_v_a": b,
        "C_v2": c,
        "interval_s": [float(t[0]), float(t[-1])],
        "duration_s": float(duration),
        "baseline_rmse_v": math.sqrt(c),
        "quadrature_max_difference": delta,
    }


def feasible_set(coef, gate_v=0.05):
    a, b, c = (float(coef[k]) for k in ("A_a2", "B_v_a", "C_v2"))
    if not np.isfinite([a, b, c, gate_v]).all() or min(a, c, gate_v) < 0:
        raise ValueError("Invalid coefficient or gate")
    covariance_bound = 64 * np.finfo(float).eps * (b * b + abs(a * c))
    if b * b > a * c + covariance_bound:
        raise ValueError("Coefficients violate the current/residual product bound")
    if a == 0:
        if b != 0:
            raise ValueError("Zero current energy requires zero cross term")
        return {
            "status": "all_nonnegative" if c <= gate_v**2 else "empty",
            "interval_ohm": [0.0, None] if c <= gate_v**2 else None,
            "gate_rmse_v": gate_v,
            "resistance_identified": False,
            "reason": "No current excitation: term cannot change voltage",
        }
    d = math.fsum([b * b, -a * c, a * gate_v**2])
    bound = 64 * np.finfo(float).eps * (b * b + abs(a * c) + a * gate_v**2)
    result = {
        "gate_rmse_v": gate_v,
        "discriminant_v2_a2": d,
        "roundoff_classification_bound_v2_a2": float(bound),
        "resistance_identified": False,
        "physical_simulation_pass": False,
    }
    if abs(d) <= bound:
        candidate = b / a
        return {
            **result,
            "status": "numerically_unresolved",
            "interval_ohm": None,
            "candidate_singleton_ohm_if_exact_zero": candidate if d == 0 else None,
        }
    if d < 0:
        return {**result, "status": "empty", "interval_ohm": None}
    root = math.sqrt(d)
    q = b + math.copysign(root, b)
    roots = sorted([q / a, (c - gate_v**2) / q])
    lower, upper = max(0.0, roots[0]), roots[1]
    clip_bound = bound / (a * (root + math.sqrt(d - bound))) + 64 * np.finfo(float).eps * (
        abs(b / a) + max(abs(r) for r in roots)
    )
    result["root_roundoff_guard_ohm"] = float(clip_bound)
    if abs(upper) <= clip_bound:
        return {
            **result,
            "status": "numerically_unresolved",
            "interval_ohm": None,
            "nonnegative_clip_roundoff_bound_ohm": float(clip_bound),
        }
    return {
        **result,
        "status": "nonempty" if lower <= upper else "empty",
        "interval_ohm": [lower, upper] if lower <= upper else None,
    }


def intersect_sets(sets):
    if not sets:
        raise ValueError("At least one feasibility set is required")
    if any(s["status"] == "empty" for s in sets):
        return {"status": "empty", "interval_ohm": None}
    if any(s["status"] == "numerically_unresolved" for s in sets):
        return {"status": "numerically_unresolved", "interval_ohm": None}
    if any(s["status"] not in {"all_nonnegative", "nonempty"} for s in sets):
        raise ValueError("Unsupported feasibility status")
    lower_set = max(sets, key=lambda s: s["interval_ohm"][0])
    lo = lower_set["interval_ohm"][0]
    upper_sets = [s for s in sets if s["interval_ohm"][1] is not None]
    upper_set = min(upper_sets, key=lambda s: s["interval_ohm"][1]) if upper_sets else None
    hi = upper_set["interval_ohm"][1] if upper_set is not None else None
    if hi is not None:
        bound = (
            max(s.get("root_roundoff_guard_ohm", 0.0) for s in sets)
            + max(s.get("root_roundoff_guard_ohm", 0.0) for s in upper_sets)
            + 64 * np.finfo(float).eps * (abs(lo) + abs(hi))
        )
        if abs(lo - hi) <= bound:
            return {
                "status": "numerically_unresolved",
                "interval_ohm": None,
                "root_comparison_roundoff_bound_ohm": float(bound),
                "candidate_singleton_ohm_if_exact_contact": lo if lo == hi else None,
            }
    return {
        "status": "nonempty" if hi is None or lo <= hi else "empty",
        "interval_ohm": [lo, hi] if hi is None or lo <= hi else None,
    }
