"""International Standard Atmosphere (ISA), troposphere only.

Pressure follows the ISA pressure-altitude relation; density uses the actual
air temperature, so a hot day at sea level is modelled correctly. Humidity is
neglected (it lowers density by under 1 % at typical flying conditions).
Dynamic viscosity follows Sutherland's law (it sets the blade Reynolds number,
see prop.ReynoldsCorrection).

References: ISO 2533:1975 Standard Atmosphere (also for the Sutherland
constants); Sutherland, Phil. Mag. 36 (1893).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .units import G0

R_AIR = 287.05287  # J/(kg K), specific gas constant of dry air (ISA)
GAMMA_AIR = 1.4
T0 = 288.15  # K, ISA sea-level temperature
P0 = 101325.0  # Pa, ISA sea-level pressure
LAPSE = 0.0065  # K/m, troposphere lapse rate
TROPOPAUSE = 11000.0  # m
MU_SUTHERLAND = 1.458e-6  # kg/(m s K^0.5), Sutherland's law constant (ISO 2533)
S_SUTHERLAND = 110.4  # K, Sutherland temperature (ISO 2533)


def isa_temperature(altitude: float) -> float:
    _check(altitude)
    return T0 - LAPSE * altitude


def isa_pressure(altitude: float) -> float:
    _check(altitude)
    return P0 * (1.0 - LAPSE * altitude / T0) ** (G0 / (R_AIR * LAPSE))


def viscosity(temperature: float) -> float:
    """Dynamic viscosity of air (Pa s), Sutherland's law: 1.789e-5 at 15 degC."""
    return MU_SUTHERLAND * temperature**1.5 / (temperature + S_SUTHERLAND)


def _check(altitude: float) -> None:
    if not -500.0 <= altitude <= TROPOPAUSE:
        raise ValueError(f"altitude {altitude} m is outside the modelled troposphere (-500 to 11000 m)")


@dataclass(frozen=True)
class Environment:
    altitude: float  # m, pressure altitude
    temperature: float  # K, actual air temperature
    g: float = G0

    @property
    def pressure(self) -> float:
        return isa_pressure(self.altitude)

    @property
    def rho(self) -> float:
        return self.pressure / (R_AIR * self.temperature)

    @property
    def viscosity(self) -> float:
        return viscosity(self.temperature)

    @property
    def kinematic_viscosity(self) -> float:
        return self.viscosity / self.rho

    @property
    def speed_of_sound(self) -> float:
        return math.sqrt(GAMMA_AIR * R_AIR * self.temperature)

    @classmethod
    def isa(cls, altitude: float = 0.0, temperature_offset: float = 0.0) -> "Environment":
        return cls(altitude, isa_temperature(altitude) + temperature_offset)
