import math

import numpy as np
import pytest

from fpvsim.atmosphere import Environment, isa_pressure
from fpvsim.mass import BoxShape, CylinderShape, MassItem, PointShape, combine, rotation_matrix


# ISO 2533 standard atmosphere table values
@pytest.mark.parametrize(
    "altitude, pressure, density",
    [(0.0, 101325.0, 1.2250), (1000.0, 89874.6, 1.1117), (3000.0, 70108.5, 0.90925), (11000.0, 22632.1, 0.36392)],
)
def test_isa_against_standard_table(altitude, pressure, density):
    env = Environment.isa(altitude)
    assert isa_pressure(altitude) == pytest.approx(pressure, rel=2e-5)
    assert env.rho == pytest.approx(density, rel=2e-4)


def test_hot_day_lowers_density_at_constant_pressure():
    std, hot = Environment.isa(0.0), Environment.isa(0.0, temperature_offset=20.0)
    assert hot.rho / std.rho == pytest.approx(288.15 / 308.15)
    assert std.speed_of_sound == pytest.approx(340.29, abs=0.01)


def test_altitude_outside_troposphere_is_rejected():
    with pytest.raises(ValueError):
        Environment.isa(12000.0).rho


def item(mass, position, shape=PointShape(), rotation=np.eye(3)):
    return MassItem("p", "g", "k", mass, np.asarray(position, dtype=float), shape, rotation)


def test_dumbbell():
    mp = combine([item(1.0, [1, 0, 0]), item(1.0, [-1, 0, 0])])
    assert np.allclose(mp.cg, 0)
    assert np.allclose(mp.inertia, np.diag([0.0, 2.0, 2.0]))


def _numeric_inertia(points: np.ndarray, mass: float) -> np.ndarray:
    """Inertia of uniformly weighted sample points about their centroid."""
    r = points - points.mean(axis=0)
    m = mass / len(points)
    return m * (np.sum(r * r) * np.eye(3) - r.T @ r)


def test_box_against_numerical_integration():
    shape = BoxShape(0.10, 0.04, 0.02)
    n = 60
    axes = [(np.arange(n) + 0.5) / n * L - L / 2 for L in (shape.lx, shape.ly, shape.lz)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    assert np.allclose(shape.inertia(0.5), _numeric_inertia(pts, 0.5), rtol=2e-3, atol=1e-12)


@pytest.mark.parametrize("inner", [0.0, 0.006])
def test_cylinder_against_numerical_integration(inner):
    shape = CylinderShape(radius=0.014, height=0.018, inner_radius=inner)
    rng = np.random.default_rng(1)
    pts = rng.uniform([-0.014, -0.014, -0.009], [0.014, 0.014, 0.009], (2_000_000, 3))
    rr = np.hypot(pts[:, 0], pts[:, 1])
    pts = pts[(rr <= 0.014) & (rr >= inner)]
    assert np.allclose(np.diag(shape.inertia(0.03)), np.diag(_numeric_inertia(pts, 0.03)), rtol=5e-3)


def test_rotation_preserves_principal_moments_and_swaps_axes():
    shape = BoxShape(0.10, 0.02, 0.01)
    base = combine([item(1.0, [0, 0, 0], shape)]).inertia
    yawed = combine([item(1.0, [0, 0, 0], shape, rotation_matrix(0, 0, math.pi / 2))]).inertia
    assert np.allclose(np.linalg.eigvalsh(base), np.linalg.eigvalsh(yawed))
    assert yawed[0, 0] == pytest.approx(base[1, 1]) and yawed[1, 1] == pytest.approx(base[0, 0])
    tilted = combine([item(1.0, [0, 0, 0], shape, rotation_matrix(0.3, -0.7, 1.1))]).inertia
    assert np.allclose(np.linalg.eigvalsh(base), np.linalg.eigvalsh(tilted))


def test_parallel_axis_theorem():
    shape = CylinderShape(0.01, 0.02)
    own = shape.inertia(2.0)
    mp = combine([item(2.0, [0.3, 0, 0], shape), item(1e-12, [0, 0, 0])])  # CG stays at the cylinder
    assert np.allclose(mp.inertia, own, atol=1e-12)
    # about the origin: Iyy and Izz gain m d^2
    mp2 = combine([item(2.0, [0.3, 0, 0], shape), item(2.0, [-0.3, 0, 0], shape)])
    assert mp2.inertia[1, 1] == pytest.approx(2 * (own[1, 1] + 2.0 * 0.09))
    assert mp2.inertia[0, 0] == pytest.approx(2 * own[0, 0])


def test_reference_build_inertia_is_physical(reference_build):
    mp = reference_build.realize().mass_props
    moments, _ = mp.principal()
    assert (moments > 0).all()
    # triangle inequality holds for every real rigid body
    assert moments[0] + moments[1] >= moments[2]
    # symmetric X layout: products of inertia are small next to the moments
    assert abs(mp.inertia[0, 1]) < 0.01 * mp.inertia[0, 0]
