"""Geometry checks on a placed design."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mass import BoxShape, CylinderShape, MassItem

PROP_MARGIN = 0.010  # m, minimum vertical gap between a part over a prop disk and the prop plane


@dataclass(frozen=True)
class ClearanceProblem:
    part: str
    rotor: int
    gap: float  # m, vertical gap to the prop plane (0 = intersects)


def _corners(item: MassItem) -> np.ndarray | None:
    shape = item.shape
    if isinstance(shape, BoxShape):
        half = np.array([shape.lx, shape.ly, shape.lz]) / 2
        local = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * half
    elif isinstance(shape, CylinderShape):
        a = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.column_stack([shape.radius * np.cos(a), shape.radius * np.sin(a)])
        local = np.vstack([np.column_stack([ring, np.full(24, z)]) for z in (-shape.height / 2, shape.height / 2)])
    else:
        return None
    return (item.rotation @ local.T).T + item.position


def _distance_to_polygon(point: np.ndarray, poly: np.ndarray) -> float:
    """Distance from a 2D point to a convex polygon (0 inside)."""
    from scipy.spatial import ConvexHull

    hull = poly[ConvexHull(poly).vertices]
    inside = True
    best = np.inf
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        edge, rel = b - a, point - a
        if edge[0] * rel[1] - edge[1] * rel[0] < 0:  # hull vertices are counter-clockwise
            inside = False
        t = np.clip(np.dot(rel, edge) / np.dot(edge, edge), 0.0, 1.0)
        best = min(best, float(np.linalg.norm(point - (a + t * edge))))
    return 0.0 if inside else best


def prop_clearance(ac, margin: float = PROP_MARGIN) -> list[ClearanceProblem]:
    """Parts (other than frame and propulsion) that sit over a prop disk
    closer than ``margin`` to the prop plane, or cut through it."""
    props = [i for i in ac.items if i.mass_key == "prop.mass"]
    radius = ac.powertrain.prop.radius
    problems = []
    for item in ac.items:
        if item.group in ("frame", "propulsion"):
            continue
        corners = _corners(item)
        if corners is None:
            continue
        zmin, zmax = corners[:, 2].min(), corners[:, 2].max()
        for k, prop in enumerate(props):
            if _distance_to_polygon(prop.position[:2], corners[:, :2]) >= radius:
                continue
            zp = prop.position[2]
            gap = 0.0 if zmin <= zp <= zmax else float(min(abs(zp - zmax), abs(zmin - zp)))
            if gap < margin:
                problems.append(ClearanceProblem(item.name, k, gap))
    return problems
