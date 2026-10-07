"""LiPo battery: first-order Thevenin equivalent circuit.

    V_terminal = OCV(SoC) - v_rc - I * R0
    dv_rc/dt   = (I * R1 - v_rc) / tau1
    dSoC/dt    = -I / Q

R0 is the ohmic resistance (instant sag), the R1-C1 pair the slower
polarisation sag that builds up over tens of seconds. Temperature dependence,
Peukert-type rate effects and ageing are not modelled; see docs/models.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Battery:
    series: int
    parallel: int
    capacity: float  # C (coulomb), whole pack
    r0_cell: float  # ohm
    r1_cell: float  # ohm
    tau1: float  # s
    ocv_soc: np.ndarray  # state of charge grid, 0..1 ascending
    ocv_cell: np.ndarray  # open-circuit cell voltage at each grid point, V
    max_current: float  # A, label continuous rating (C rating x capacity)

    def __post_init__(self) -> None:
        if np.any(np.diff(self.ocv_soc) <= 0):
            raise ValueError("OCV SoC grid must be strictly ascending")
        if self.ocv_soc[0] != 0.0 or self.ocv_soc[-1] != 1.0:
            raise ValueError("OCV SoC grid must span 0 to 1")

    @property
    def r0(self) -> float:
        return self.series * self.r0_cell / self.parallel

    @property
    def r1(self) -> float:
        return self.series * self.r1_cell / self.parallel

    @property
    def capacity_mah(self) -> float:
        return self.capacity / 3.6

    def ocv(self, soc: float) -> float:
        return self.series * float(np.interp(soc, self.ocv_soc, self.ocv_cell))

    def nominal_energy(self) -> float:
        """Energy between SoC 1 and 0 at open-circuit voltage, J."""
        soc = np.linspace(0.0, 1.0, 201)
        v = self.series * np.interp(soc, self.ocv_soc, self.ocv_cell)
        return float(np.trapezoid(v, soc)) * self.capacity


@dataclass(frozen=True)
class BatteryState:
    soc: float = 1.0
    v_rc: float = 0.0  # V across the R1-C1 pair

    def step(self, battery: Battery, current: float, dt: float) -> "BatteryState":
        """Advance by ``dt`` at constant ``current`` (exact for the RC pair)."""
        target = current * battery.r1
        decay = math.exp(-dt / battery.tau1)
        return BatteryState(
            soc=self.soc - current * dt / battery.capacity,
            v_rc=target + (self.v_rc - target) * decay,
        )

    def source_voltage(self, battery: Battery) -> float:
        """Thevenin source voltage seen behind R0."""
        return battery.ocv(self.soc) - self.v_rc
