"""Bounded electrochemical simulation using published PyBaMM equations/parameters."""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Literal

# Telemetry is unnecessary for reproducible offline simulations.
os.environ.setdefault("PYBAMM_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pybamm  # noqa: E402

from physical_fpv.current_profile import CurrentProfile  # noqa: E402

MODEL_TYPES = {
    "SPM": pybamm.lithium_ion.SPM,
    "SPMe": pybamm.lithium_ion.SPMe,
    "DFN": pybamm.lithium_ion.DFN,
}


@dataclass(frozen=True)
class ModelConfig:
    model: Literal["SPM", "SPMe", "DFN"] = "DFN"
    thermal: Literal["isothermal", "lumped"] = "isothermal"
    parameter_set: Literal["Chen2020", "ORegan2022"] = "Chen2020"
    initial_temperature_k: float | None = None
    heat_transfer_coefficient_w_m2_k: float | None = None
    current_a: float = 5.0
    ambient_temperature_k: float = 298.15
    mesh_points: int = 20
    tolerance: float = 1e-7
    sample_period_s: float = 10.0
    max_temperature_k: float = 333.15

    def validate(self) -> None:
        if self.model not in MODEL_TYPES or self.thermal not in {"isothermal", "lumped"}:
            raise ValueError("Unsupported model or thermal option")
        if self.parameter_set not in {"Chen2020", "ORegan2022"}:
            raise ValueError("Unsupported parameter set")
        if self.initial_temperature_k is not None and (
            not np.isfinite(self.initial_temperature_k)
            or not 263.15 <= self.initial_temperature_k < self.max_temperature_k
        ):
            raise ValueError("Initial temperature must be finite and inside the research envelope")
        if self.heat_transfer_coefficient_w_m2_k is not None and (
            not np.isfinite(self.heat_transfer_coefficient_w_m2_k)
            or not 1 <= self.heat_transfer_coefficient_w_m2_k <= 50
        ):
            raise ValueError("Heat transfer coefficient must be within 1 to 50 W/m2/K")
        scalars = (
            self.current_a,
            self.ambient_temperature_k,
            self.tolerance,
            self.sample_period_s,
            self.max_temperature_k,
        )
        if not np.isfinite(scalars).all():
            raise ValueError("All numerical settings must be finite")
        maximum_current = 7.5 if self.parameter_set == "Chen2020" else 10.0
        if not 0.5 <= self.current_a <= maximum_current:
            raise ValueError(f"Supported current is 0.5 to {maximum_current} A; no FPV claim")
        minimum_temperature = 288.15 if self.parameter_set == "Chen2020" else 273.15
        if not minimum_temperature <= self.ambient_temperature_k <= 318.15:
            raise ValueError("Ambient temperature outside the parameter-set research envelope")
        maximum_mesh = 120 if self.parameter_set == "ORegan2022" else 80
        if not isinstance(self.mesh_points, int) or not 10 <= self.mesh_points <= maximum_mesh:
            raise ValueError(
                f"Mesh must be an integer from 10 to {maximum_mesh} (bounded CPU cost)"
            )
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
    solver_cache_info: dict | None = None
    current_protocol: dict | None = None

    def metadata(self) -> dict:
        return {
            "config": asdict(self.config),
            "pybamm_version": pybamm.__version__,
            "parameter_set": self.config.parameter_set,
            "parameter_fingerprint": self.parameter_fingerprint,
            "compiled_template_cache": self.solver_cache_info,
            "current_protocol": self.current_protocol
            or {
                "type": "constant discharge",
                "current_a": self.config.current_a,
            },
            "initial_state": f"{self.config.parameter_set} initial concentrations; no SOC fit",
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
            else (
                "exploratory; thermal parameter provenance incomplete; NOT validated"
                if self.config.parameter_set == "Chen2020"
                else "lumped volume-average prediction; empirical qualification reported separately"
            ),
            "scope": "fresh LG M50 benchmark; not certified for FPV, abuse, aging or safety",
            "outside_benchmark_temperature": self.config.ambient_temperature_k != 298.15,
            "concentration_audit_scope": (
                "finite-volume nodes and surface states at output times; no plotting ghost points"
            ),
        }


def parameter_fingerprint(parameters: pybamm.ParameterValues) -> str:
    import hashlib
    import inspect
    import json

    values = {k: inspect.getsource(v) if callable(v) else v for k, v in parameters.items()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=6)
def _simulation_template(
    model_name, thermal, parameter_set, mesh_points, tolerance, maximum_temperature, heat_transfer
):
    """Reuse symbolic/discretized equations only; every solve resets initial state.

    Current and temperature boundary values are explicit inputs, not fitted parameters.
    This cache is deliberately small and intended for sequential CPU research runs.
    """
    model = MODEL_TYPES[model_name](options={"thermal": thermal})
    model.events.append(
        pybamm.Event(
            "Research temperature envelope",
            maximum_temperature - model.variables["Volume-averaged cell temperature [K]"],
        )
    )
    parameters = pybamm.ParameterValues(parameter_set)
    parameters.update(
        {
            "Current function [A]": "[input]",
            "Ambient temperature [K]": "[input]",
            "Initial temperature [K]": "[input]",
        }
    )
    if heat_transfer is not None:
        parameters.update({"Total heat transfer coefficient [W.m-2.K-1]": heat_transfer})
    var_pts = {
        "x_n": mesh_points,
        "x_s": max(5, mesh_points // 2),
        "x_p": mesh_points,
        "r_n": mesh_points,
        "r_p": mesh_points,
    }
    solver = pybamm.IDAKLUSolver(rtol=tolerance, atol=tolerance, options={"num_threads": 1})
    return pybamm.Simulation(model, parameter_values=parameters, var_pts=var_pts, solver=solver)


def simulate(
    config: ModelConfig, current_profile: CurrentProfile | None = None
) -> SimulationResult:
    config.validate()
    duration = min(86400.0, 1.5 * 5.0 / config.current_a * 3600)
    if current_profile is not None:
        if not isinstance(current_profile, CurrentProfile):
            raise TypeError("Expected an immutable CurrentProfile")
        current_profile.require_coverage(duration)
        maximum_current = 7.5 if config.parameter_set == "Chen2020" else 10.0
        if current_profile.min_current_a < 0.5 or current_profile.max_current_a > maximum_current:
            raise ValueError("Current profile leaves the parameter-set research envelope")
    parameters = pybamm.ParameterValues(config.parameter_set)
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": (
                config.initial_temperature_k
                if config.initial_temperature_k is not None
                else config.ambient_temperature_k
            ),
        }
    )
    if config.heat_transfer_coefficient_w_m2_k is not None:
        parameters.update(
            {"Total heat transfer coefficient [W.m-2.K-1]": config.heat_transfer_coefficient_w_m2_k}
        )
    cache_before = _simulation_template.cache_info()
    fingerprint = parameter_fingerprint(parameters)
    if current_profile is None:
        simulation = _simulation_template(
            config.model,
            config.thermal,
            config.parameter_set,
            config.mesh_points,
            config.tolerance,
            config.max_temperature_k,
            config.heat_transfer_coefficient_w_m2_k,
        )
        inputs = {
            key: parameters[key]
            for key in (
                "Current function [A]",
                "Ambient temperature [K]",
                "Initial temperature [K]",
            )
        }
    else:
        model = MODEL_TYPES[config.model](options={"thermal": config.thermal})
        model.events.append(
            pybamm.Event(
                "Research temperature envelope",
                config.max_temperature_k - model.variables["Volume-averaged cell temperature [K]"],
            )
        )
        parameters.update(
            {
                "Current function [A]": pybamm.Interpolant(
                    current_profile.time_s,
                    current_profile.current_a,
                    pybamm.t,
                    interpolator="linear",
                    extrapolate=False,
                )
            }
        )
        simulation = pybamm.Simulation(
            model,
            parameter_values=parameters,
            var_pts={
                "x_n": config.mesh_points,
                "x_s": max(5, config.mesh_points // 2),
                "x_p": config.mesh_points,
                "r_n": config.mesh_points,
                "r_p": config.mesh_points,
            },
            solver=pybamm.IDAKLUSolver(
                rtol=config.tolerance, atol=config.tolerance, options={"num_threads": 1}
            ),
        )
        # Profile-specific equations are never mixed into the constant-current cache.
        inputs = {}
        fingerprint = hashlib.sha256(
            (
                fingerprint + ":piecewise-linear-current:" + current_profile.fingerprint_sha256
            ).encode()
        ).hexdigest()
    output_time = np.arange(0, duration + config.sample_period_s, config.sample_period_s)
    output_time = output_time[output_time <= duration]
    integration_stops = (
        [0, duration]
        if current_profile is None
        else np.unique(np.r_[current_profile.time_s[current_profile.time_s < duration], duration])
    )
    solution = simulation.solve(integration_stops, t_interp=output_time, inputs=inputs)
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
        concentration = np.asarray(
            solution[f"{electrode} particle concentration [mol.m-3]"].entries
        )
        maximum = parameters[f"Maximum concentration in {electrode.lower()} electrode [mol.m-3]"]
        surface = np.asarray(
            solution[f"{electrode} particle surface concentration [mol.m-3]"].entries
        )
        lower = min(float(np.min(concentration)), float(np.min(surface)))
        upper = max(float(np.max(concentration)), float(np.max(surface)))
        concentration_bounds[electrode.lower()] = {
            "node_min_mol_m3": float(np.min(concentration)),
            "node_max_mol_m3": float(np.max(concentration)),
            "surface_min_mol_m3": float(np.min(surface)),
            "surface_max_mol_m3": float(np.max(surface)),
            "node_array_shape": list(concentration.shape),
            "min_mol_m3": lower,
            "max_mol_m3": upper,
            "limit_mol_m3": maximum,
            "passed": bool(
                np.isfinite(concentration).all()
                and np.isfinite(surface).all()
                and lower >= -1e-6
                and upper <= maximum + 1e-6
            ),
        }
    electrolyte = np.asarray(solution["Electrolyte concentration [mol.m-3]"].entries)
    drift = float(np.max(np.abs(lithium - lithium[0])) / lithium[0])
    expected_charge = (
        config.current_a * time / 3600
        if current_profile is None
        else current_profile.charge_integral_ah(time)
    )
    charge_error = float(np.max(np.abs(capacity - expected_charge)))
    thermal_residual = None
    if config.thermal == "lumped":
        # Cooling is signed. Integrate temperature-dependent heat capacity along the trajectory.
        stored = float(np.trapezoid(heat_capacity, temperature))
        net_heat = float(np.trapezoid(heating + cooling, time))
        generated_heat = float(np.trapezoid(np.abs(heating), time))
        thermal_residual = {
            "stored_energy_j": stored,
            "integrated_net_heat_j": net_heat,
            "absolute_residual_j": abs(stored - net_heat),
            "relative_residual": abs(stored - net_heat) / max(abs(stored), 1.0),
            "relative_to_generated_heat": abs(stored - net_heat) / max(generated_heat, 1.0),
            "passed": abs(stored - net_heat) / max(generated_heat, 1.0) <= 0.01,
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
            and (thermal_residual is None or thermal_residual["passed"])
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
        fingerprint,
        {
            "hit": current_profile is None
            and _simulation_template.cache_info().hits > cache_before.hits,
            "templates": _simulation_template.cache_info().currsize,
            "maximum_templates": 6,
            "state_reset": "fresh initial conditions every solve",
            "profile_template_reused": False,
        },
        (
            None
            if current_profile is None
            else {
                "type": "explicit piecewise-linear discharge current",
                "fingerprint_sha256": current_profile.fingerprint_sha256,
                "time_units": "s",
                "current_units": "A; positive discharge",
                "current_range_a": [current_profile.min_current_a, current_profile.max_current_a],
                "profile_end_time_s": current_profile.end_time_s,
                "implicit_extrapolation": False,
                "solver_stops_at_profile_knots": True,
            }
        ),
    )
