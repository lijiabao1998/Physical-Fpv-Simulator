"""Unit handling.

Every model in fpvsim works in SI units (kg, m, s, A, V, ohm, rad, N, W, C).
Conversion happens only at the boundaries: when data files are read and when
results are displayed. Each supported unit is listed explicitly below so a
typo in a data file fails loudly instead of being silently misread.
"""

from __future__ import annotations

import math

G0 = 9.80665
"""Standard gravity in m/s^2 (exact by definition, 3rd CGPM 1901)."""

RPM_TO_RADS = 2.0 * math.pi / 60.0
RADS_TO_RPM = 60.0 / (2.0 * math.pi)

# unit -> (factor, offset, SI unit); si_value = factor * value + offset
_UNITS: dict[str, tuple[float, float, str]] = {
    "1": (1.0, 0.0, "1"),
    "%": (0.01, 0.0, "1"),
    # length
    "m": (1.0, 0.0, "m"),
    "cm": (1e-2, 0.0, "m"),
    "mm": (1e-3, 0.0, "m"),
    "in": (0.0254, 0.0, "m"),
    # mass
    "kg": (1.0, 0.0, "kg"),
    "g": (1e-3, 0.0, "kg"),
    # time
    "s": (1.0, 0.0, "s"),
    "min": (60.0, 0.0, "s"),
    "h": (3600.0, 0.0, "s"),
    # electrical
    "V": (1.0, 0.0, "V"),
    "mV": (1e-3, 0.0, "V"),
    "A": (1.0, 0.0, "A"),
    "mA": (1e-3, 0.0, "A"),
    "ohm": (1.0, 0.0, "ohm"),
    "mohm": (1e-3, 0.0, "ohm"),
    "Ah": (3600.0, 0.0, "C"),
    "mAh": (3.6, 0.0, "C"),
    "W": (1.0, 0.0, "W"),
    "mW": (1e-3, 0.0, "W"),
    # force and torque
    "N": (1.0, 0.0, "N"),
    "gf": (G0 * 1e-3, 0.0, "N"),
    "kgf": (G0, 0.0, "N"),
    "N*m": (1.0, 0.0, "N*m"),
    "N/W": (1.0, 0.0, "N/W"),
    "gf/W": (G0 * 1e-3, 0.0, "N/W"),
    "N*mm": (1e-3, 0.0, "N*m"),
    # angle and rotation
    "rad": (1.0, 0.0, "rad"),
    "deg": (math.pi / 180.0, 0.0, "rad"),
    "rad/s": (1.0, 0.0, "rad/s"),
    "deg/s": (math.pi / 180.0, 0.0, "rad/s"),
    "deg/s/sqrt(Hz)": (math.pi / 180.0, 0.0, "rad/s/sqrt(Hz)"),
    "Hz": (1.0, 0.0, "1/s"),
    "m/s": (1.0, 0.0, "m/s"),
    "km/h": (1.0 / 3.6, 0.0, "m/s"),
    "m^2": (1.0, 0.0, "m^2"),
    "cm^2": (1e-4, 0.0, "m^2"),
    "N/m": (1.0, 0.0, "N/m"),
    "N*s/m": (1.0, 0.0, "N*s/m"),
    "rpm": (RPM_TO_RADS, 0.0, "rad/s"),
    "rpm/V": (RPM_TO_RADS, 0.0, "rad/s/V"),
    "1/rad": (1.0, 0.0, "1/rad"),
    "1/deg": (180.0 / math.pi, 0.0, "1/rad"),
    # inertia
    "kg*m^2": (1.0, 0.0, "kg*m^2"),
    "g*cm^2": (1e-7, 0.0, "kg*m^2"),
    "g*mm^2": (1e-9, 0.0, "kg*m^2"),
    # pressure and temperature
    "Pa": (1.0, 0.0, "Pa"),
    "hPa": (100.0, 0.0, "Pa"),
    "kPa": (1000.0, 0.0, "Pa"),
    "K": (1.0, 0.0, "K"),
    "degC": (1.0, 273.15, "K"),
}


class UnitError(ValueError):
    pass


def _lookup(unit: str) -> tuple[float, float, str]:
    try:
        return _UNITS[unit]
    except KeyError:
        known = ", ".join(sorted(_UNITS))
        raise UnitError(f"unknown unit {unit!r}; supported units: {known}") from None


def is_known(unit: str) -> bool:
    return unit in _UNITS


def to_si(value: float, unit: str) -> float:
    factor, offset, _ = _lookup(unit)
    return value * factor + offset


def from_si(value: float, unit: str) -> float:
    factor, offset, _ = _lookup(unit)
    return (value - offset) / factor


def scale(unit: str) -> float:
    """Multiplicative factor to SI, used for differences and uncertainties."""
    return _lookup(unit)[0]


def si_unit(unit: str) -> str:
    return _lookup(unit)[2]
