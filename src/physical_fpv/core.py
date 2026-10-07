"""Bounded electrochemical simulation using published PyBaMM equations/parameters."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Literal

# Telemetry is unnecessary for reproducible offline simulations.
os.environ.setdefault("PYBAMM_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pybamm  # noqa: E402

MODEL_TYPES = {
    "SPM": pybamm.lithium_ion.SPM,
    "SPMe": pybamm.lithium_ion.SPMe,
    "DFN": pybamm.lithium_ion.DFN,
}


@dataclass(frozen=True)
class ModelConfig:
    model: Literal["SPM", "SPMe", "DFN"] = "DFN"
    thermal: Literal["isothermal", "lumped"] = "isothermal"
    current_a: float = 5.0
    ambient_temperature_k: float = 298.15
    mesh_points: int = 20
    tolerance: float = 1e-7
    sample_period_s: float = 10.0
    max_temperature_k: float = 333.15

    def validate(self) -> None:
        if self.model not in MODEL_TYPES or self.thermal not in {"isothermal", "lumped"}:
            raise ValueError("Unsupported model or thermal option")
        scalars = (
            self.current_a,
            self.ambient_temperature_k,
            self.tolerance,
            self.sample_period_s,
            self.max_temperature_k,
        )
        if not np.isfinite(scalars).all():
            raise ValueError("All numerical settings must be finite")
        if not 0.5 <= self.current_a <= 7.5:
            raise ValueError("Supported research envelope is 0.5 to 7.5 A; no high-C FPV claim")
        if not 288.15 <= self.ambient_temperature_k <= 318.15:
            raise ValueError("Exploratory temperature envelope is 288.15 to 318.15 K")
        if not isinstance(self.mesh_points, int) or not 10 <= self.mesh_points <= 80:
            raise ValueError("Mesh must be an integer from 10 to 80 (bounded CPU cost)")
        if not 1e-9 <= self.tolerance <= 1e-5:
            raise ValueError("Solver tolerance must be between 1e-9 and 1e-5")
        if not 1 <= self.sample_period_s <= 60:
            raise ValueError("Sampling period must be between 1 and 60 seconds")
        if not self.ambient_temperature_k < self.max_temperature_k <= 333.15:
            raise ValueError("Temperature guard must exceed ambient and be at most 333.15 K")


@dataclass
class SimulationResult:
    config: ModelConfig
    time_s: np.ndarray
    voltage_v: np.ndarray
    capacity_ah: np.ndarray
    temperature_k: np.ndarray
    lithium_mol: np.ndarray
    heating_w: np.ndarray
    cooling_w: np.ndarray
    heat_capacity_j_k: np.ndarray | None
    termination: str
    physical_audit: dict
    parameter_fingerprint: str

    def metadata(self) -> dict:
        return {
            "config": asdict(self.config),
            "pybamm_version": pybamm.__version__,
            "parameter_set": "Chen2020",
            "parameter_fingerprint": self.parameter_fingerprint,
            "initial_state": "published Chen2020 initial concentrations; no SOC fitting",
            "termination": self.termination,
            "voltage_cutoff_reached": "Minimum voltage" in self.termination,
            "endpoint_time_s": float(self.time_s[-1]),
            "cutoff_capacity_ah": (
                float(self.capacity_ah[-1]) if "Minimum voltage" in self.termination else None
            ),
            "capacity_ah": float(self.capacity_ah[-1]),
            "physical_audit": self.physical_audit,
            "temperature_status": "imposed, not predicted"
            if self.config.thermal == "isothermal"
            else "exploratory; thermal parameter provenance incomplete; NOT validated",
            "scope": "fresh LG M50 benchmark; not certified for FPV, abuse, aging or safety",
            "outside_benchmark_temperature": self.config.ambient_temperature_k != 298.15,
            "concentration_audit_scope": "output samples only; not every internal solver step",
        }


def parameter_fingerprint(parameters: pybamm.ParameterValues) -> str:
    import hashlib
    import inspect
    import json

    values = {k: inspect.getsource(v) if callable(v) else v for k, v in parameters.items()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def simulate(config: ModelConfig) -> SimulationResult:
    config.validate()
    model = MODEL_TYPES[config.model](options={"thermal": config.thermal})
    model.events.append(
        pybamm.Event(
            "Research temperature envelope",
            config.max_temperature_k - model.variables["Volume-averaged cell temperature [K]"],
        )
    )
    parameters = pybamm.ParameterValues("Chen2020")
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.ambient_temperature_k,
        }
    )
    points = config.mesh_points
    var_pts = {
        "x_n": points,
        "x_s": max(5, points // 2),
        "x_p": points,
        "r_n": points,
        "r_p": points,
    }
    solver = pybamm.IDAKLUSolver(
        rtol=config.tolerance, atol=config.tolerance, options={"num_threads": 1}
    )
    simulation = pybamm.Simulation(
        model, parameter_values=parameters, var_pts=var_pts, solver=solver
    )
    duration = min(86400.0, 1.5 * 5.0 / config.current_a * 3600)
    output_time = np.arange(0, duration + config.sample_period_s, config.sample_period_s)
    output_time = output_time[output_time <= duration]
    solution = simulation.solve([0, duration], t_interp=output_time)
    time = np.asarray(solution.t)

    def get(name):
        return np.asarray(solution[name](time), dtype=float).reshape(-1)

    voltage = get("Terminal voltage [V]")
    capacity = get("Discharge capacity [A.h]")
    temperature = get("Volume-averaged cell temperature [K]")
    lithium = get("Total lithium [mol]")
    heating = get("Total heating [W]")
    cooling = get("Surface total cooling [W]")
    heat_capacity = None
    if config.thermal == "lumped":
        heat_capacity = (
            get("Volume-averaged effective heat capacity [J.K-1.m-3]")
            * parameters["Cell volume [m3]"]
        )
    finite = all(
        np.isfinite(x).all()
        for x in (time, voltage, capacity, temperature, lithium, heating, cooling)
    )
    if heat_capacity is not None:
        finite = finite and np.isfinite(heat_capacity).all() and np.all(heat_capacity > 0)
    if not finite or np.any(np.diff(time) <= 0):
        raise RuntimeError("Solver returned invalid/nonmonotone outputs")
    concentration_bounds = {}
    for electrode in ("Negative", "Positive"):
        concentration = np.asarray(solution[f"{electrode} particle concentration [mol.m-3]"](time))
        maximum = parameters[f"Maximum concentration in {electrode.lower()} electrode [mol.m-3]"]
        concentration_bounds[electrode.lower()] = {
            "min_mol_m3": float(np.min(concentration)),
            "max_mol_m3": float(np.max(concentration)),
            "limit_mol_m3": maximum,
            "passed": bool(
                np.isfinite(concentration).all()
                and np.min(concentration) >= -1e-6
                and np.max(concentration) <= maximum + 1e-6
            ),
        }
    electrolyte = np.asarray(solution["Electrolyte concentration [mol.m-3]"](time))
    drift = float(np.max(np.abs(lithium - lithium[0])) / lithium[0])
    charge_error = float(np.max(np.abs(capacity - config.current_a * time / 3600)))
    thermal_residual = None
    if config.thermal == "lumped":
        # Surface cooling is signed negative when removing heat. Constant Chen heat capacities.
        stored = float(heat_capacity[0] * (temperature[-1] - temperature[0]))
        net_heat = float(np.trapezoid(heating + cooling, time))
        thermal_residual = {
            "stored_energy_j": stored,
            "integrated_net_heat_j": net_heat,
            "absolute_residual_j": abs(stored - net_heat),
            "relative_residual": abs(stored - net_heat) / max(abs(stored), 1.0),
            "note": "trapezoidal sampled-output audit, not experimental validation",
        }
    audit = {
        "lithium_inventory_relative_drift": drift,
        "charge_integral_error_ah": charge_error,
        "concentration_bounds": concentration_bounds,
        "electrolyte_min_mol_m3": float(np.min(electrolyte)),
        "thermal_energy_balance": thermal_residual,
        "passed": bool(
            drift <= 1e-6
            and charge_error <= 1e-6
            and np.isfinite(electrolyte).all()
            and np.min(electrolyte) > 0
            and all(v["passed"] for v in concentration_bounds.values())
        ),
    }
    return SimulationResult(
        config,
        time,
        voltage,
        capacity,
        temperature,
        lithium,
        heating,
        cooling,
        heat_capacity,
        str(solution.termination),
        audit,
        parameter_fingerprint(parameters),
    )
