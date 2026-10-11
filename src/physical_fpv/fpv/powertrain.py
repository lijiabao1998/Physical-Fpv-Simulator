"""Bounded synthetic pack/ESC/DC-motor/static-propeller reference model.

This is *not* a parameterization or extension of the PyBaMM research cells.
All dimensional defaults are invented fixtures, not measured hardware data.
See docs/fpv-powertrain.md for topology, conservation equations and limitations.
"""

from dataclasses import asdict, dataclass
from numbers import Integral

import numpy as np

SYNTHETIC_PROVENANCE = {
    "evidence_kind": "synthetic_analytical_baseline",
    "parameter_source": "invented deterministic fixtures; no fitted or measured values",
    "empirically_validated": False,
    "pybamm_parameter_mapping": False,
    "motor_model": "quasi-steady averaged DC equivalent; no rotor or winding dynamics",
    "propeller_model": "constant static CT/CQ; airspeed changes cooling only",
    "cell_model": "linear SOC OCV and constant resistance; no electrochemical polarization",
}


@dataclass(frozen=True)
class PowertrainConfig:
    """SI units except capacity (Ah); cell parameters accept scalars or (S,P) arrays.

    Four identical motor/ESC/propeller channels are attached to the shared bus.
    A pack is S series-connected groups, each containing P parallel cell branches.
    User-supplied parameter variations remain synthetic, not validated hardware.
    """

    series: int = 4
    parallel: int = 2
    cell_capacity_ah: object = 1.5
    cell_resistance_ohm: object = 0.020
    cell_harness_resistance_ohm: object = 0.001
    cell_thermal_capacity_j_k: object = 45.0
    initial_soc: object = 0.90
    initial_temperature_k: object = 298.15
    ocv_empty_v: object = 3.1
    ocv_full_v: object = 4.2
    harness_resistance_ohm: float = 0.006
    ambient_temperature_k: float = 298.15
    cooling_w_k: float = 0.12
    airspeed_cooling_w_k_per_m_s: float = 0.02
    motor_resistance_ohm: float = 0.060
    motor_constant_si: float = 0.0045
    motor_viscous_friction_nm_s: float = 1e-6
    esc_resistance_ohm: float = 0.008
    propeller_diameter_m: float = 0.127
    thrust_coefficient: float = 0.11
    torque_coefficient: float = 0.012
    air_density_kg_m3: float = 1.225
    max_step_s: float = 0.1


def _scalar(value, name, lower, upper):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite real scalar in [{lower}, {upper}]")
    try:
        array = np.asarray(value)
        if array.shape != () or np.iscomplexobj(array) or array.dtype.kind in "bUS":
            raise ValueError
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real scalar") from exc
    if not np.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{name} outside synthetic domain [{lower}, {upper}]")
    return result


def _array(value, name, shape, lower, upper):
    try:
        raw = np.asarray(value)
        if np.iscomplexobj(raw) or raw.dtype.kind in "bUS":
            raise ValueError
        result = np.asarray(value, dtype=float)
        if result.shape == ():
            result = np.full(shape, float(result))
        if result.shape != shape:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be real scalar or have shape {shape}") from exc
    if not np.all(np.isfinite(result)) or np.any(result < lower) or np.any(result > upper):
        raise ValueError(f"{name} outside synthetic domain [{lower}, {upper}]")
    return result.copy()


def _readonly(value):
    result = np.array(value, dtype=float, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class PowertrainOutput:
    voltage_v: float
    current_a: float
    thrust_n: np.ndarray
    rotor_torque_nm: np.ndarray
    rotor_speed_rad_s: np.ndarray
    cell_currents_a: np.ndarray
    cell_temperature_k: np.ndarray
    soc: np.ndarray
    group_voltage_v: np.ndarray
    cell_ocv_v: np.ndarray
    cell_terminal_voltage_v: np.ndarray
    motor_current_a: np.ndarray
    motor_voltage_v: np.ndarray
    esc_input_current_a: np.ndarray
    chemical_power_w: float
    bus_power_w: float
    cell_heat_w: np.ndarray
    branch_harness_heat_w: np.ndarray
    shared_harness_heat_w: float
    motor_copper_loss_w: np.ndarray
    esc_loss_w: np.ndarray
    motor_friction_loss_w: np.ndarray
    rotor_power_w: np.ndarray
    circuit_residual_v: float
    power_balance_error_w: float

    def as_dict(self):
        """Return a JSON-serializable detached snapshot."""
        return {
            key: value.tolist() if isinstance(value, np.ndarray) else value
            for key, value in asdict(self).items()
        }


class Powertrain:
    """Coupled quasi-static loads, with implicit-midpoint SOC and lumped heat.

    ``evaluate`` does not advance physical state. ``step`` returns the endpoint
    load, while integrated charge/energy use the step midpoint. Rejected steps
    are atomic: no time, state, ledger or last-output changes are retained.
    """

    def __init__(self, config=None):
        self.config = config if config is not None else PowertrainConfig()
        if not isinstance(self.config, PowertrainConfig):
            raise ValueError("config must be a PowertrainConfig")
        c = self.config
        for name, value in (("series", c.series), ("parallel", c.parallel)):
            if isinstance(value, bool) or not isinstance(value, Integral) or not 1 <= value <= 12:
                raise ValueError(f"{name} must be an integer in [1, 12]")
        shape = (c.series, c.parallel)
        cell_fields = {
            "cell_capacity_ah": (0.1, 20.0),
            "cell_resistance_ohm": (0.0001, 1.0),
            "cell_harness_resistance_ohm": (0.0, 0.2),
            "cell_thermal_capacity_j_k": (1.0, 1000.0),
            "initial_soc": (0.05, 1.0),
            "initial_temperature_k": (273.15, 333.15),
            "ocv_empty_v": (2.0, 4.0),
            "ocv_full_v": (2.1, 4.5),
        }
        self._cells = {
            name: _array(getattr(c, name), name, shape, *bounds)
            for name, bounds in cell_fields.items()
        }
        if np.any(self._cells["ocv_full_v"] <= self._cells["ocv_empty_v"]):
            raise ValueError("ocv_full_v must exceed ocv_empty_v for every cell")
        scalar_fields = {
            "harness_resistance_ohm": (0.0, 1.0),
            "ambient_temperature_k": (273.15, 333.15),
            "cooling_w_k": (0.0, 10.0),
            "airspeed_cooling_w_k_per_m_s": (0.0, 1.0),
            "motor_resistance_ohm": (0.0001, 2.0),
            "motor_constant_si": (0.0005, 0.1),
            "motor_viscous_friction_nm_s": (0.0, 0.01),
            "esc_resistance_ohm": (0.0, 0.5),
            "propeller_diameter_m": (0.025, 0.5),
            "thrust_coefficient": (0.001, 1.0),
            "torque_coefficient": (0.0001, 0.2),
            "air_density_kg_m3": (0.8, 1.5),
            "max_step_s": (0.00001, 1.0),
        }
        self._p = {
            name: _scalar(getattr(c, name), name, *bounds) for name, bounds in scalar_fields.items()
        }
        ideal_power_coefficient = self._p["thrust_coefficient"] ** 1.5 * np.sqrt(2.0 / np.pi)
        if 2.0 * np.pi * self._p["torque_coefficient"] < ideal_power_coefficient:
            raise ValueError("CT/CQ violate the ideal static actuator-disk power lower bound")
        self._soc = self._cells["initial_soc"].copy()
        self._temperature = self._cells["initial_temperature_k"].copy()
        self._resistance = (
            self._cells["cell_resistance_ohm"] + self._cells["cell_harness_resistance_ohm"]
        )
        self._conductance = 1.0 / self._resistance
        self._group_resistance = 1.0 / self._conductance.sum(axis=1)
        self._pack_resistance = float(
            self._group_resistance.sum() + self._p["harness_resistance_ohm"]
        )
        self._capacity_c = 3600.0 * self._cells["cell_capacity_ah"]
        self._ocv_slope = self._cells["ocv_full_v"] - self._cells["ocv_empty_v"]
        self._torque_factor = (
            self._p["torque_coefficient"]
            * self._p["air_density_kg_m3"]
            * self._p["propeller_diameter_m"] ** 5
            / (2.0 * np.pi) ** 2
        )
        self._thrust_factor = (
            self._p["thrust_coefficient"]
            * self._p["air_density_kg_m3"]
            * self._p["propeller_diameter_m"] ** 4
            / (2.0 * np.pi) ** 2
        )
        self._elapsed_s = 0.0
        self._cell_charge_c = np.zeros(shape)
        self._cell_heat_j = np.zeros(shape)
        self._cooling_j = np.zeros(shape)
        self._energies = dict.fromkeys(
            (
                "chemical_energy_j",
                "bus_energy_j",
                "branch_harness_heat_j",
                "shared_harness_heat_j",
                "motor_copper_heat_j",
                "esc_heat_j",
                "motor_friction_heat_j",
                "rotor_work_j",
            ),
            0.0,
        )
        self._bus_charge_c = 0.0
        self._last = self._evaluate(np.zeros(4), self._soc, self._temperature)

    @staticmethod
    def _duties(duties):
        result = _array(duties, "duties", (4,), 0.0, 1.0)
        # A scalar cannot accidentally broadcast into four commands.
        if np.asarray(duties).shape != (4,):
            raise ValueError("duties must contain exactly four values")
        return result

    @staticmethod
    def _state_domain(soc, temperature):
        if not np.all(np.isfinite(soc)) or np.any(soc < 0.05) or np.any(soc > 1.0):
            raise ValueError("cell SOC outside synthetic domain [0.05, 1.0]; step rejected")
        if (
            not np.all(np.isfinite(temperature))
            or np.any(temperature < 273.15)
            or np.any(temperature > 333.15)
        ):
            raise ValueError("cell temperature outside synthetic domain [273.15, 333.15] K")

    def _motors(self, duties, voltage):
        p = self._p
        k = p["motor_constant_si"]  # kt == ke in coherent SI units.
        resistance = p["motor_resistance_ohm"] + p["esc_resistance_ohm"]
        friction = p["motor_viscous_friction_nm_s"]
        a = resistance * self._torque_factor / k
        b = k + resistance * friction / k
        applied = duties * voltage
        # Stable positive root of a*w^2 + b*w - duty*V = 0 (also at zero duty).
        omega = 2.0 * applied / (b + np.sqrt(b * b + 4.0 * a * applied))
        torque = self._torque_factor * omega**2
        current = (torque + friction * omega) / k
        derivative = (
            duties * (2.0 * self._torque_factor * omega + friction) / (k * (2.0 * a * omega + b))
        )
        return omega, torque, current, float(np.dot(duties, derivative))

    def _evaluate(self, duties, soc, temperature):
        self._state_domain(soc, temperature)
        p = self._p
        ocv = self._cells["ocv_empty_v"] + self._ocv_slope * soc
        group_ocv = (ocv * self._conductance).sum(axis=1) * self._group_resistance
        pack_ocv = float(group_ocv.sum())
        # Passive monotone load: f(0)<0, f(E)>=0. Safeguarded Newton has a unique root.
        lower, upper, voltage = 0.0, pack_ocv, pack_ocv
        for _ in range(64):
            omega, torque, motor_current, slope = self._motors(duties, voltage)
            current = float(np.dot(duties, motor_current))
            residual = voltage + self._pack_resistance * current - pack_ocv
            if abs(residual) < 1e-12:
                break
            if residual > 0.0:
                upper = voltage
            else:
                lower = voltage
            candidate = voltage - residual / (1.0 + self._pack_resistance * slope)
            voltage = candidate if lower < candidate < upper else 0.5 * (lower + upper)
        else:
            raise ValueError("coupled circuit root did not converge")
        group_voltage = group_ocv - self._group_resistance * current
        # Computing deviation from weighted OCV avoids cancellation for equal cells at rest.
        cell_current = (ocv - group_ocv[:, None]) * self._conductance + (
            self._group_resistance[:, None] * self._conductance * current
        )
        if np.max(np.abs(cell_current)) > 60.0:
            raise ValueError("cell current outside synthetic domain [-60, 60] A")
        if np.any(group_voltage <= 0):
            raise ValueError("a series group has non-positive terminal voltage")
        if np.max(motor_current) > 60.0 or np.max(omega) > 5000.0:
            raise ValueError("motor outside synthetic domain: current <=60 A, speed <=5000 rad/s")
        cell_heat = cell_current**2 * self._cells["cell_resistance_ohm"]
        branch_heat = cell_current**2 * self._cells["cell_harness_resistance_ohm"]
        shared_heat = current**2 * p["harness_resistance_ohm"]
        copper = motor_current**2 * p["motor_resistance_ohm"]
        esc_loss = motor_current**2 * p["esc_resistance_ohm"]
        friction_loss = p["motor_viscous_friction_nm_s"] * omega**2
        rotor_power = torque * omega
        chemical = float(np.sum(ocv * cell_current))
        bus_power = voltage * current
        loss = float(
            cell_heat.sum()
            + branch_heat.sum()
            + shared_heat
            + copper.sum()
            + esc_loss.sum()
            + friction_loss.sum()
            + rotor_power.sum()
        )
        return PowertrainOutput(
            voltage_v=float(voltage),
            current_a=current,
            thrust_n=_readonly(self._thrust_factor * omega**2),
            rotor_torque_nm=_readonly(torque),
            rotor_speed_rad_s=_readonly(omega),
            cell_currents_a=_readonly(cell_current),
            cell_temperature_k=_readonly(temperature),
            soc=_readonly(soc),
            group_voltage_v=_readonly(group_voltage),
            cell_ocv_v=_readonly(ocv),
            cell_terminal_voltage_v=_readonly(
                ocv - cell_current * self._cells["cell_resistance_ohm"]
            ),
            motor_current_a=_readonly(motor_current),
            motor_voltage_v=_readonly(duties * voltage - p["esc_resistance_ohm"] * motor_current),
            esc_input_current_a=_readonly(duties * motor_current),
            chemical_power_w=chemical,
            bus_power_w=bus_power,
            cell_heat_w=_readonly(cell_heat),
            branch_harness_heat_w=_readonly(branch_heat),
            shared_harness_heat_w=float(shared_heat),
            motor_copper_loss_w=_readonly(copper),
            esc_loss_w=_readonly(esc_loss),
            motor_friction_loss_w=_readonly(friction_loss),
            rotor_power_w=_readonly(rotor_power),
            circuit_residual_v=float(residual),
            power_balance_error_w=chemical - loss,
        )

    def evaluate(self, duties):
        result = self._evaluate(self._duties(duties), self._soc, self._temperature)
        self._last = result
        return result

    def step(self, duties, dt_s, airspeed_m_s=0.0):
        duties = self._duties(duties)
        dt = _scalar(dt_s, "dt_s", 1e-9, self._p["max_step_s"])
        speed = _scalar(airspeed_m_s, "airspeed_m_s", 0.0, 50.0)
        h = self._p["cooling_w_k"] + self._p["airspeed_cooling_w_k_per_m_s"] * speed
        thermal_capacity = self._cells["cell_thermal_capacity_j_k"]
        if np.any(dt * h / (2.0 * thermal_capacity) > 1.0):
            raise ValueError("step too large for monotone cooling; reduce dt_s")
        midpoint_soc = self._soc.copy()
        # Implicit midpoint keeps the linear-OCV chemical-energy ledger conservative.
        for _ in range(32):
            mid = self._evaluate(duties, midpoint_soc, self._temperature)
            next_midpoint = self._soc - 0.5 * dt * mid.cell_currents_a / self._capacity_c
            if np.max(np.abs(next_midpoint - midpoint_soc)) < 2e-14:
                midpoint_soc = next_midpoint
                break
            midpoint_soc = next_midpoint
        else:
            raise ValueError("SOC midpoint did not converge; reduce dt_s")
        mid = self._evaluate(duties, midpoint_soc, self._temperature)
        new_soc = self._soc - dt * mid.cell_currents_a / self._capacity_c
        new_temperature = self._temperature + dt * (
            mid.cell_heat_w - h * (self._temperature - self._p["ambient_temperature_k"])
        ) / (thermal_capacity + 0.5 * dt * h)
        end = self._evaluate(duties, new_soc, new_temperature)
        cooling = h * (
            0.5 * (self._temperature + new_temperature) - self._p["ambient_temperature_k"]
        )
        # Commit only after endpoint and every intermediate state have passed all guards.
        self._soc = new_soc
        self._temperature = new_temperature
        self._elapsed_s += dt
        self._cell_charge_c += dt * mid.cell_currents_a
        self._bus_charge_c += dt * mid.current_a
        self._cell_heat_j += dt * mid.cell_heat_w
        self._cooling_j += dt * cooling
        rates = {
            "chemical_energy_j": mid.chemical_power_w,
            "bus_energy_j": mid.bus_power_w,
            "branch_harness_heat_j": float(mid.branch_harness_heat_w.sum()),
            "shared_harness_heat_j": mid.shared_harness_heat_w,
            "motor_copper_heat_j": float(mid.motor_copper_loss_w.sum()),
            "esc_heat_j": float(mid.esc_loss_w.sum()),
            "motor_friction_heat_j": float(mid.motor_friction_loss_w.sum()),
            "rotor_work_j": float(mid.rotor_power_w.sum()),
        }
        for name, rate in rates.items():
            self._energies[name] += dt * rate
        self._last = end
        return end

    def telemetry(self):
        """Latest output, domains/provenance, and independent state/ledger closure."""
        initial = self._cells["initial_soc"]
        # Integral of E(z)*capacity_C dz; not measured electrochemical free energy.
        chemical_removed = float(
            np.sum(
                self._capacity_c
                * (initial - self._soc)
                * (self._cells["ocv_empty_v"] + 0.5 * self._ocv_slope * (initial + self._soc))
            )
        )
        thermal_change = self._cells["cell_thermal_capacity_j_k"] * (
            self._temperature - self._cells["initial_temperature_k"]
        )
        outflow = (
            float(self._cell_heat_j.sum())
            + self._energies["branch_harness_heat_j"]
            + self._energies["shared_harness_heat_j"]
            + self._energies["motor_copper_heat_j"]
            + self._energies["esc_heat_j"]
            + self._energies["motor_friction_heat_j"]
            + self._energies["rotor_work_j"]
        )
        return {
            **self._last.as_dict(),
            "elapsed_s": self._elapsed_s,
            "provenance": dict(SYNTHETIC_PROVENANCE),
            "parameters": {
                **self._p,
                **{name: value.tolist() for name, value in self._cells.items()},
            },
            "topology": {
                "series_groups": int(self.config.series),
                "parallel_cells_per_group": int(self.config.parallel),
            },
            "domains": {
                "soc": [0.05, 1.0],
                "temperature_k": [273.15, 333.15],
                "cell_current_a": [-60.0, 60.0],
                "motor_current_a": [0.0, 60.0],
                "rotor_speed_rad_s": [0.0, 5000.0],
                "airspeed_m_s": [0.0, 50.0],
                "duty": [0.0, 1.0],
                "maximum_step_s": self._p["max_step_s"],
            },
            "integrals": {
                **self._energies,
                "cell_charge_drawn_c": self._cell_charge_c.tolist(),
                "bus_charge_drawn_c": self._bus_charge_c,
                "cell_heat_j": self._cell_heat_j.tolist(),
                "cell_cooling_j": self._cooling_j.tolist(),
            },
            "audits": {
                "charge_closure_max_abs_c": float(
                    np.max(np.abs(self._capacity_c * (initial - self._soc) - self._cell_charge_c))
                ),
                "series_charge_closure_max_abs_c": float(
                    np.max(np.abs(self._cell_charge_c.sum(axis=1) - self._bus_charge_c))
                ),
                "chemical_energy_state_change_j": chemical_removed,
                "chemical_energy_integration_error_j": chemical_removed
                - self._energies["chemical_energy_j"],
                "energy_balance_error_j": chemical_removed - outflow,
                "thermal_balance_max_abs_j": float(
                    np.max(np.abs(thermal_change - self._cell_heat_j + self._cooling_j))
                ),
            },
        }
