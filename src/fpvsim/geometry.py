"""Geometry checks on a placed design."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mass import BoxShape, CylinderShape, MassItem

PROP_MARGIN = 0.010  # m, minimum vertical gap between a part over (or next to) a prop disk and the prop plane
PROP_TIP_MARGIN = 0.003  # m, minimum plan-view distance from the disk edge: prop radius tolerance and shaft runout (blade flex is vertical, covered by PROP_MARGIN)


@dataclass(frozen=True)
class Clearance:
    """Clearance of one part to one prop.

    A part is clear if it stays PROP_TIP_MARGIN outside the prop disk in
    plan view, or PROP_MARGIN away from the prop plane. ``margin`` is the
    larger of the two surpluses, so it is negative only when both rules are
    broken, and its size is how far the part can move (in the easier
    direction) before it is."""

    part: str
    rotor: int
    horizontal: float  # m, plan-view distance of the footprint from the disk edge (< 0 = over the disk)
    vertical: float  # m, vertical gap to the prop plane (0 = cuts through it)

    @property
    def margin(self) -> float:
        return max(self.horizontal - PROP_TIP_MARGIN, self.vertical - PROP_MARGIN)


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


def clearances(ac) -> list[Clearance]:
    """Every (part, prop) pair, for parts other than frame and propulsion."""
    props = [i for i in ac.items if i.mass_key == "prop.mass"]
    radius = ac.powertrain.prop.radius
    out = []
    for item in ac.items:
        if item.group in ("frame", "propulsion"):
            continue
        corners = _corners(item)
        if corners is None:
            continue
        zmin, zmax = corners[:, 2].min(), corners[:, 2].max()
        for k, prop in enumerate(props):
            horizontal = _distance_to_polygon(prop.position[:2], corners[:, :2]) - radius
            zp = prop.position[2]
            vertical = 0.0 if zmin <= zp <= zmax else float(min(abs(zp - zmax), abs(zmin - zp)))
            out.append(Clearance(item.name, k, horizontal, vertical))
    return out


def clearance_margin(ac) -> Clearance | None:
    """The worst (part, prop) pair."""
    pairs = clearances(ac)
    return min(pairs, key=lambda c: c.margin) if pairs else None


def prop_clearance(ac) -> list[ClearanceProblem]:
    """Parts that break both clearance rules: within PROP_TIP_MARGIN of a
    prop disk in plan view and closer than PROP_MARGIN to the prop plane."""
    return [ClearanceProblem(c.part, c.rotor, c.vertical) for c in clearances(ac) if c.margin < 0.0]
