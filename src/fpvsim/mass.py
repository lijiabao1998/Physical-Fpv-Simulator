"""Mass properties: total mass, centre of gravity and inertia tensor.

Body frame is FRD (x forward, y right, z down), the aerospace convention also
used by flight-controller firmware. The origin is the centre of the motor
mounting pattern, on the motor mounting plane. Every part is a primitive
solid with uniform density, placed and rotated in that frame.

Inertia tensors use the tensor form I = integral (|r|^2 E - r r^T) dm, so
off-diagonal terms are the negative products of inertia (-integral xy dm).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


class Shape:
    def inertia(self, mass: float) -> np.ndarray:
        """Inertia about the shape's own centroid, in its own axes."""
        raise NotImplementedError


@dataclass(frozen=True)
class PointShape(Shape):
    def inertia(self, mass: float) -> np.ndarray:
        return np.zeros((3, 3))


@dataclass(frozen=True)
class BoxShape(Shape):
    lx: float
    ly: float
    lz: float

    def inertia(self, mass: float) -> np.ndarray:
        return (mass / 12.0) * np.diag(
            [self.ly**2 + self.lz**2, self.lx**2 + self.lz**2, self.lx**2 + self.ly**2]
        )


@dataclass(frozen=True)
class CylinderShape(Shape):
    """Solid or hollow cylinder with its axis along the shape's z axis."""

    radius: float
    height: float
    inner_radius: float = 0.0

    def inertia(self, mass: float) -> np.ndarray:
        r2 = self.radius**2 + self.inner_radius**2
        transverse = mass * (3.0 * r2 + self.height**2) / 12.0
        return np.diag([transverse, transverse, 0.5 * mass * r2])


def rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Rotation from part axes to body axes, ZYX (yaw-pitch-roll) order."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return rz @ ry @ rx


@dataclass(frozen=True)
class MassItem:
    name: str
    group: str
    mass_key: str
    mass: float
    position: np.ndarray  # centroid in body frame, m
    shape: Shape
    rotation: np.ndarray  # part axes -> body axes

    def inertia_body_axes(self) -> np.ndarray:
        """Own inertia about the part centroid, expressed in body axes."""
        return self.rotation @ self.shape.inertia(self.mass) @ self.rotation.T


@dataclass(frozen=True)
class MassProperties:
    mass: float
    cg: np.ndarray
    inertia: np.ndarray  # about the CG, body axes

    def principal(self) -> tuple[np.ndarray, np.ndarray]:
        """Principal moments (ascending) and axes (columns)."""
        moments, axes = np.linalg.eigh(self.inertia)
        return moments, axes


def parallel_axis(mass: float, offset: np.ndarray) -> np.ndarray:
    """Inertia of a point mass at ``offset`` about the origin (tensor form)."""
    d = np.asarray(offset, dtype=float)
    return mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


def combine(items: list[MassItem]) -> MassProperties:
    if not items:
        raise ValueError("no mass items")
    total = sum(item.mass for item in items)
    if total <= 0.0:
        raise ValueError("total mass must be positive")
    cg = sum(item.mass * item.position for item in items) / total
    inertia = np.zeros((3, 3))
    for item in items:
        inertia += item.inertia_body_axes() + parallel_axis(item.mass, item.position - cg)
    return MassProperties(total, cg, inertia)
