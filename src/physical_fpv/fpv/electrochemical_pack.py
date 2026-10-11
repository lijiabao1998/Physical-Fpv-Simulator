"""Bounded Chen SPM -> homogeneous pack -> synthetic quasi-static motor load.

The cell current is a DAE unknown, not a prescribed trace or lagged estimate.
This independent bridge never changes the original research core or its gates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from numbers import Integral
from time import process_time

import numpy as np

from physical_fpv.fpv.powertrain import Powertrain, PowertrainConfig, _scalar


@dataclass(frozen=True)
class ElectrochemicalPackConfig:
    """Identical Chen2020 cells; SI units; downstream defaults remain synthetic."""

    series: int = 4
    parallel: int = 2
    branch_harness_resistance_ohm: float = 0.001
    harness_resistance_ohm: float = 0.006
    motor_resistance_ohm: float = 0.060
    motor_constant_si: float = 0.0045
    motor_viscous_friction_nm_s: float = 1e-6
    esc_resistance_ohm: float = 0.008
    propeller_diameter_m: float = 0.127
    thrust_coefficient: float = 0.11
    torque_coefficient: float = 0.012
    air_density_kg_m3: float = 1.225
    temperature_k: float = 298.15
    duration_s: float = 10.0
    sample_period_s: float = 0.1
    max_step_s: float = 0.1
    mesh_points: int = 40
    tolerance: float = 1e-8

    def validate(self):
        from physical_fpv.core import ModelConfig

        for name in ("series", "parallel"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or not 1 <= value <= 12:
                raise ValueError(f"{name} must be an integer in [1, 12]")
        _scalar(self.duration_s, "duration_s", 0.001, 30.0)
        _scalar(self.sample_period_s, "sample_period_s", 0.01, 1.0)
        _scalar(self.max_step_s, "max_step_s", 0.01, 1.0)
        _scalar(self.temperature_k, "temperature_k", 298.15, 298.15)
        _scalar(self.branch_harness_resistance_ohm, "branch_harness_resistance_ohm", 0, 0.2)
        # Reuse the core's supported mesh/tolerance envelope, without altering it.
        if isinstance(self.mesh_points, bool):
            raise ValueError("mesh_points must be an integer")
        ModelConfig(
            model="SPM", current_a=1.0, mesh_points=self.mesh_points, tolerance=self.tolerance
        ).validate()
        self.reference_load()  # Canonical downstream domains and CT/CQ energy guard.

    def reference_load(self):
        """Validation/oracle only: this synthetic cell is never used in the solve."""
        names = (
            "motor_resistance_ohm",
            "motor_constant_si",
            "motor_viscous_friction_nm_s",
            "esc_resistance_ohm",
            "propeller_diameter_m",
            "thrust_coefficient",
            "torque_coefficient",
            "air_density_kg_m3",
            "harness_resistance_ohm",
        )
        return Powertrain(PowertrainConfig(**{key: getattr(self, key) for key in names}))


def _schedule(duties, duty_times_s, duration_s):
    raw = np.asarray(duties)
    if np.iscomplexobj(raw) or raw.dtype.kind in "bUS":
        raise ValueError("duties must contain finite real values")
    values = np.asarray(raw, dtype=float)
    if duty_times_s is None:
        if values.shape != (4,):
            raise ValueError("constant duties must have shape (4,)")
        times = np.array([0.0, duration_s])
        values = np.tile(values, (2, 1))
    else:
        raw_times = np.asarray(duty_times_s)
        if np.iscomplexobj(raw_times) or raw_times.dtype.kind in "bUS":
            raise ValueError("duty_times_s must be finite real values")
        times = np.asarray(raw_times, dtype=float)
        if times.ndim != 1 or not 2 <= len(times) <= 61 or values.shape != (len(times), 4):
            raise ValueError("schedules require 2..61 times and duties of shape (times, 4)")
        if (
            not np.isfinite(times).all()
            or times[0] != 0
            or times[-1] != duration_s
            or np.any(np.diff(times) <= 0)
        ):
            raise ValueError("duty times must strictly increase from 0 to duration_s")
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
        raise ValueError("duties must be finite and in [0, 1]")
    return times.copy(), values.copy()


def _motor_state(duty, voltage, config, sqrt):
    """Same stable positive DC-motor/static-propeller root as Powertrain._motors."""
    c = config
    torque_factor = c.torque_coefficient * c.air_density_kg_m3 * c.propeller_diameter_m**5
    torque_factor /= (2 * np.pi) ** 2
    resistance = c.motor_resistance_ohm + c.esc_resistance_ohm
    a = resistance * torque_factor / c.motor_constant_si
    b = c.motor_constant_si + resistance * c.motor_viscous_friction_nm_s / c.motor_constant_si
    applied = duty * voltage
    omega = 2 * applied / (b + sqrt(b * b + 4 * a * applied))
    torque = torque_factor * omega**2
    current = (torque + c.motor_viscous_friction_nm_s * omega) / c.motor_constant_si
    return omega, torque, current


def solve_electrochemical_pack(
    duties=(0.35, 0.35, 0.35, 0.35), *, config=None, duty_times_s=None, estimates=()
):
    """Solve one bounded load-coupled, isothermal, homogeneous pack demonstration.

    Optional schedules interpolate linearly, never extrapolate; zero pack load is
    outside the deliberately preserved 0.5..7.5 A/cell research envelope.
    Material overrides use the existing strict PropertyEstimate mapping contract.
    An event/domain exit raises ValueError instead of returning partial success.
    """
    from physical_fpv.core import parameter_fingerprint, pybamm
    from physical_fpv.fpv.material_bridge import CHEN_SOURCE
    from physical_fpv.materials import PropertyEstimate

    started = process_time()
    c = config if config is not None else ElectrochemicalPackConfig()
    if not isinstance(c, ElectrochemicalPackConfig):
        raise ValueError("config must be an ElectrochemicalPackConfig")
    c.validate()
    knot_times, knot_duties = _schedule(duties, duty_times_s, c.duration_s)
    effective_harness = (
        c.harness_resistance_ohm + c.series * c.branch_harness_resistance_ohm / c.parallel
    )
    symbolic_duties = [
        pybamm.Interpolant(knot_times, knot_duties[:, j], pybamm.t, interpolator="linear")
        for j in range(4)
    ]

    def load_residual(variables):
        cell_current = variables["Current [A]"]
        bus = c.series * variables["Voltage [V]"] - effective_harness * c.parallel * cell_current
        load = sum(duty * _motor_state(duty, bus, c, pybamm.sqrt)[2] for duty in symbolic_duties)
        return cell_current - load / c.parallel

    model = pybamm.lithium_ion.SPM(
        options={"thermal": "isothermal", "operating mode": load_residual}
    )
    current = model.variables["Current [A]"]
    bus = c.series * model.variables["Voltage [V]"] - effective_harness * c.parallel * current
    for name, expression in (
        ("Bridge lower current envelope", current - 0.5),
        ("Bridge upper current envelope", 7.5 - current),
        ("Bridge positive bus voltage", bus),
    ):
        model.events.append(pybamm.Event(name, expression))
    for index, duty in enumerate(symbolic_duties):
        omega, _, motor_current = _motor_state(duty, bus, c, pybamm.sqrt)
        model.events.append(pybamm.Event(f"Bridge motor {index} speed envelope", 5000 - omega))
        model.events.append(
            pybamm.Event(f"Bridge motor {index} current envelope", 60 - motor_current)
        )
    # Initial algebraic guess is only a guess; IDA calculates the consistent root.
    # Avoid a large current guess putting the harness voltage below zero.
    model.initial_conditions[model.variables["Current variable [A]"]] = pybamm.Scalar(0.5)
    parameters = pybamm.ParameterValues("Chen2020")
    parameters.update(
        {
            "Ambient temperature [K]": c.temperature_k,
            "Initial temperature [K]": c.temperature_k,
        }
    )
    sources = [
        {
            "kind": "published_parameter_reconstruction",
            "source": CHEN_SOURCE,
            "implementation": "PyBaMM Chen2020",
            "independently_validated": False,
        }
    ]
    seen = set()
    for electrode, phase, estimate in estimates:
        if not isinstance(estimate, PropertyEstimate):
            raise TypeError("Expected a provenance-aware PropertyEstimate")
        if electrode in seen:
            raise ValueError("Duplicate electrode override")
        seen.add(electrode)
        parameters.update(
            estimate.electrode_mapping(
                electrode, c.temperature_k, phase=phase, stoichiometry_range=(0.0, 1.0)
            )
        )
        sources.append(
            {
                "electrode": electrode,
                "estimate": asdict(estimate),
                "qualification": "caller supplied evidence; not independently verified",
            }
        )
    solver = pybamm.IDAKLUSolver(
        rtol=c.tolerance,
        atol=c.tolerance,
        root_tol=c.tolerance,
        options={"num_threads": 1, "dt_max": c.max_step_s, "max_num_steps": 10000},
    )
    simulation = pybamm.Simulation(
        model,
        parameter_values=parameters,
        solver=solver,
        var_pts={
            "x_n": c.mesh_points,
            "x_s": 10,
            "x_p": c.mesh_points,
            "r_n": c.mesh_points,
            "r_p": c.mesh_points,
        },
    )
    output_times = np.unique(
        np.concatenate(
            [
                np.linspace(0, c.duration_s, int(np.ceil(c.duration_s / c.sample_period_s)) + 1),
                knot_times,
            ]
        )
    )
    try:
        solution = simulation.solve(knot_times, t_interp=output_times)
    except pybamm.SolverError as exc:
        message = f"Coupled solve failed or left the supported bridge domain: {exc}"
        raise ValueError(message) from exc
    if solution.termination != "final time" or not np.isclose(solution.t[-1], c.duration_s):
        raise ValueError(f"Coupled solve left supported domain: {solution.termination}")
    times = np.asarray(solution.t)

    def values(name):
        result = np.asarray(solution[name].entries, dtype=float)
        if not np.isfinite(result).all():
            raise ValueError(f"Non-finite electrochemical solution: {name}")
        return result

    voltage_cell = values("Voltage [V]")
    current_cell = values("Current [A]")
    temperature = values("Volume-averaged cell temperature [K]")
    charge_cell = 3600 * values("Discharge capacity [A.h]")
    lithium = values("Total lithium [mol]")
    lithium_n = values("Total lithium in negative electrode [mol]")
    lithium_p = values("Total lithium in positive electrode [mol]")
    ocv = values("Bulk open-circuit voltage [V]")
    if np.any(current_cell < 0.5) or np.any(current_cell > 7.5):
        raise ValueError("Cell current outside supported [0.5, 7.5] A; no high-C extension")
    if not np.allclose(temperature, 298.15, rtol=0, atol=1e-9):
        raise ValueError("Temperature left imposed 298.15 K bridge domain")
    current_pack = c.parallel * current_cell
    voltage_bus = c.series * voltage_cell - effective_harness * current_pack
    command = np.column_stack([np.interp(times, knot_times, knot_duties[:, j]) for j in range(4)])
    omega, torque, motor_current = _motor_state(command, voltage_bus[:, None], c, np.sqrt)
    if (
        np.any(voltage_bus <= 0)
        or not np.isfinite(omega).all()
        or np.any(omega > 5000)
        or np.any(motor_current > 60)
    ):
        raise ValueError("Synthetic downstream motor/bus domain exceeded")
    thrust = c.thrust_coefficient * c.air_density_kg_m3 * c.propeller_diameter_m**4
    thrust = thrust * omega**2 / (2 * np.pi) ** 2
    esc_current = command * motor_current
    copper = c.motor_resistance_ohm * motor_current**2
    esc_loss = c.esc_resistance_ohm * motor_current**2
    friction = c.motor_viscous_friction_nm_s * omega**2
    rotor_power = torque * omega
    branch_heat = c.series * c.parallel * current_cell**2 * c.branch_harness_resistance_ohm
    harness_heat = current_pack**2 * c.harness_resistance_ohm
    cell_terminal_power = c.series * c.parallel * voltage_cell * current_cell
    bus_power = voltage_bus * current_pack
    kcl = current_pack - esc_current.sum(axis=1)
    motor_kvl = command * voltage_bus[:, None] - (
        (c.motor_resistance_ohm + c.esc_resistance_ohm) * motor_current
        + c.motor_constant_si * omega
    )
    electrical_balance = cell_terminal_power - (
        branch_heat + harness_heat + (copper + esc_loss + friction + rotor_power).sum(axis=1)
    )
    faraday = float(pybamm.constants.F.value)
    charge_error = max(
        float(np.max(abs(charge_cell + faraday * (lithium_n - lithium_n[0])))),
        float(np.max(abs(charge_cell - faraday * (lithium_p - lithium_p[0])))),
    )
    audit = {
        "max_pack_kcl_residual_a": float(np.max(abs(kcl))),
        "max_motor_kvl_residual_v": float(np.max(abs(motor_kvl))),
        "max_terminal_power_balance_error_w": float(np.max(abs(electrical_balance))),
        "max_electrode_charge_error_c": charge_error,
        "max_total_lithium_error_mol": float(np.max(abs(lithium - lithium[0]))),
        "terminal_power_scope": "cell terminals to rotors; not cell thermodynamic energy",
        "charge_scope": "SPM integrated current compared to each electrode lithium inventory",
    }
    audit["passed"] = bool(
        audit["max_pack_kcl_residual_a"] < 1e-5
        and audit["max_motor_kvl_residual_v"] < 1e-9
        and audit["max_terminal_power_balance_error_w"] < 1e-3
        and charge_error < 1e-4
        and audit["max_total_lithium_error_mol"] < 1e-9
    )
    payload = {
        "schema": "fpv-electrochemical-pack-v1",
        "config": {
            key: value.item() if isinstance(value, np.generic) else value
            for key, value in asdict(c).items()
        },
        "time_s": times.tolist(),
        "cell_voltage_v": voltage_cell.tolist(),
        "cell_bulk_ocv_v": ocv.tolist(),
        "bus_voltage_v": voltage_bus.tolist(),
        "cell_current_a": current_cell.tolist(),
        "pack_current_a": current_pack.tolist(),
        "duties": command.tolist(),
        "cell_temperature_k": temperature.tolist(),
        "rotor_thrust_n": thrust.tolist(),
        "rotor_speed_rad_s": omega.tolist(),
        "rotor_torque_nm": torque.tolist(),
        "motor_current_a": motor_current.tolist(),
        "esc_input_current_a": esc_current.tolist(),
        "cell_charge_c": charge_cell.tolist(),
        "pack_charge_c": (c.parallel * charge_cell).tolist(),
        "cell_terminal_power_w": cell_terminal_power.tolist(),
        "bus_power_w": bus_power.tolist(),
        "branch_harness_heat_w": branch_heat.tolist(),
        "shared_harness_heat_w": harness_heat.tolist(),
        "motor_copper_loss_w": copper.tolist(),
        "esc_loss_w": esc_loss.tolist(),
        "motor_friction_loss_w": friction.tolist(),
        "rotor_power_w": rotor_power.tolist(),
        "physical_audit": audit,
        "termination": solution.termination,
        "pybamm_version": pybamm.__version__,
        "parameter_fingerprint": parameter_fingerprint(parameters),
        "sources": sources,
        "coupling": "simultaneous algebraic current/load constraint; no lagged current",
        "cell_model": "SPM spherical solid diffusion and Butler-Volmer kinetics; Chen2020",
        "pack_model": "identical cells; homogeneous S series/P parallel; equal branch current",
        "downstream_provenance": "invented Powertrain static DC/ESC/propeller coefficients",
        "temperature_status": "imposed 298.15 K; no electrochemical-pack heat prediction",
        "empirical_gate": "NOT ESTABLISHED",
        "validity_uplift": False,
        "scope": "bounded connection demonstration; not measured FPV or high-C qualification",
    }
    payload["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    # Diagnostic only, excluded from the reproducible scientific payload hash.
    payload["cpu_time_s"] = process_time() - started
    return payload
