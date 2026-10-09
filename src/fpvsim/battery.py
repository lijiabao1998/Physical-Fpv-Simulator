"""LiPo battery: first-order Thevenin equivalent circuit with a lumped
thermal model.

    V_terminal = OCV(SoC) - v_rc - I * R0(T)
    dv_rc/dt   = (I * R1(T) - v_rc) / tau1
    dSoC/dt    = -I / Q
    C_th dT/dt = I^2 R0(T) + v_rc^2 / R1(T) - hA(v) (T - T_ambient)

R0 is the ohmic resistance (instant sag), the R1-C1 pair the slower
polarisation sag that builds up over tens of seconds. Both follow an
Arrhenius law around the temperature at which they were measured,

    R(T) = R(T_ref) exp[(Ea / R_gas) (1/T - 1/T_ref)],

so a cold pack sags more and a pack warms itself up under load. Heat leaves
by convection; hA grows with the air speed over the pack (laminar forced
convection, ~ v^0.5). Entropic (reversible) heat and the temperature
dependence of the OCV are neglected: at the C-rates of an FPV quad Joule
heating dominates. Ageing (capacity fade, resistance growth with cycle
count) is applied when the aircraft is realised, see design.py. Peukert-type
rate effects on capacity are not modelled; see docs/models.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

R_GAS = 8.314462618  # J/(mol K)
T_REF_DEFAULT = 298.15  # K


@dataclass(frozen=True)
class Battery:
    series: int
    parallel: int
    capacity: float  # C (coulomb), whole pack
    r0_cell: float  # ohm, at r_ref_temperature
    r1_cell: float  # ohm, at r_ref_temperature
    tau1: float  # s
    ocv_soc: np.ndarray  # state of charge grid, 0..1 ascending
    ocv_cell: np.ndarray  # open-circuit cell voltage at each grid point, V
    max_current: float  # A, label continuous rating (C rating x capacity)
    r_ref_temperature: float = T_REF_DEFAULT  # K, temperature of the r0/r1 values
    activation_energy: float = 0.0  # J/mol, Arrhenius; 0 = resistance independent of temperature
    heat_capacity: float = 0.0  # J/K, whole pack; 0 = no thermal model (temperature stays put)
    ha_hover: float = 0.0  # W/K, convective conductance in hover (prop inflow only)
    ha_ref: float = 0.0  # W/K, at air speed ha_speed
    ha_speed: float = 10.0  # m/s
    max_temperature: float = 333.15  # K, cell temperature limit
    cycles: float = 0.0  # charge cycles the pack has seen (ageing already applied to capacity and resistance)

    def __post_init__(self) -> None:
        if np.any(np.diff(self.ocv_soc) <= 0):
            raise ValueError("OCV SoC grid must be strictly ascending")
        if self.ocv_soc[0] != 0.0 or self.ocv_soc[-1] != 1.0:
            raise ValueError("OCV SoC grid must span 0 to 1")

    # ------------------------------------------------------------ resistance

    def resistance_factor(self, temperature: float) -> float:
        """R(T) / R(T_ref) from the Arrhenius law."""
        if self.activation_energy == 0.0:
            return 1.0
        return math.exp(self.activation_energy / R_GAS * (1.0 / temperature - 1.0 / self.r_ref_temperature))

    @property
    def r0(self) -> float:
        """Pack ohmic resistance at the reference temperature."""
        return self.series * self.r0_cell / self.parallel

    @property
    def r1(self) -> float:
        return self.series * self.r1_cell / self.parallel

    def r0_at(self, temperature: float) -> float:
        return self.r0 * self.resistance_factor(temperature)

    def r1_at(self, temperature: float) -> float:
        return self.r1 * self.resistance_factor(temperature)

    # --------------------------------------------------------------- thermal

    @property
    def thermal(self) -> bool:
        return self.heat_capacity > 0.0

    def conductance(self, air_speed: float) -> float:
        """Convective conductance hA (W/K) at the given air speed over the pack."""
        if self.ha_ref <= self.ha_hover or air_speed <= 0.0:
            return self.ha_hover
        return self.ha_hover + (self.ha_ref - self.ha_hover) * math.sqrt(air_speed / self.ha_speed)

    def heat(self, current: float, v_rc: float, temperature: float) -> float:
        """Joule heat (W): ohmic part plus the polarisation resistance's share."""
        r1 = self.r1_at(temperature)
        return current * current * self.r0_at(temperature) + (v_rc * v_rc / r1 if r1 > 0.0 else 0.0)

    # ----------------------------------------------------------------- other

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
    temperature: float = T_REF_DEFAULT  # K, lumped pack temperature

    def step(self, battery: Battery, current: float, dt: float, ambient: float | None = None,
             air_speed: float = 0.0) -> "BatteryState":
        """Advance by ``dt`` at constant ``current``: exact for the RC pair and,
        with the heat input frozen over the step, for the thermal node."""
        target = current * battery.r1_at(self.temperature)
        decay = math.exp(-dt / battery.tau1)
        temperature = self.temperature
        if battery.thermal:
            q = battery.heat(current, self.v_rc, self.temperature)
            ha = battery.conductance(air_speed)
            t_amb = self.temperature if ambient is None else ambient
            if ha > 0.0:
                t_ss = t_amb + q / ha
                temperature = t_ss + (self.temperature - t_ss) * math.exp(-ha * dt / battery.heat_capacity)
            else:
                temperature = self.temperature + q * dt / battery.heat_capacity
        return BatteryState(
            soc=self.soc - current * dt / battery.capacity,
            v_rc=target + (self.v_rc - target) * decay,
            temperature=temperature,
        )

    def source_voltage(self, battery: Battery) -> float:
        """Thevenin source voltage seen behind R0."""
        return battery.ocv(self.soc) - self.v_rc
