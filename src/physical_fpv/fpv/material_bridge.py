"""Explicit, fail-closed materials-to-solver boundary; original core stays untouched.

A published parameter reconstruction and a supplied material estimate are different
sources. Passing this software boundary does not independently qualify the source.
No automatic atomistic-to-battery conversion is implemented or implied.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np

from physical_fpv.materials import PropertyEstimate

CHEN_SOURCE = "https://doi.org/10.1149/1945-7111/ab9050"


@dataclass(frozen=True)
class ElectrodeMapping:
    porosity: float
    tortuosity_factor: float
    solid_volume_fraction: float
    active_fraction_of_solid: float
    assumption_source: str

    def validate(self):
        vals = [
            self.porosity,
            self.tortuosity_factor,
            self.solid_volume_fraction,
            self.active_fraction_of_solid,
        ]
        if not np.isfinite(vals).all():
            raise ValueError("Mapping coefficients must be finite")
        if not 0 < self.porosity < 1 or not self.tortuosity_factor >= 1:
            raise ValueError("Porosity in (0,1), tortuosity factor >= 1 required")
        if not 0 < self.solid_volume_fraction <= 1 - self.porosity + 1e-12:
            raise ValueError("Solid and pore volume fractions exceed unity")
        if not 0 < self.active_fraction_of_solid <= 1 or not self.assumption_source.strip():
            raise ValueError("Active fraction and assumption provenance required")

    def effective_electrolyte_transport(self, intrinsic):
        self.validate()
        if not np.isfinite(intrinsic) or intrinsic <= 0:
            raise ValueError("Positive intrinsic transport required in consistent SI units")
        return intrinsic * self.porosity / self.tortuosity_factor

    def active_volume_fraction(self):
        self.validate()
        return self.solid_volume_fraction * self.active_fraction_of_solid


def chemical_from_tracer(tracer_m2_s, thermodynamic_factor, correlation_factor, *, source):
    """User-supplied factors only; no inference that they describe an actual electrode."""
    vals = [tracer_m2_s, thermodynamic_factor, correlation_factor]
    if not np.isfinite(vals).all() or min(vals) <= 0 or not source.strip():
        raise ValueError("Positive factors and independent conversion provenance required")
    return {
        "chemical_diffusivity_m2_s": float(np.prod(vals)),
        "source": source,
        "qualification": "algebra only; source validity not established",
    }


def solve_material_spm(*, estimates=(), duration_s=30.0, current_a=1.0, mesh_points=20):
    """Bounded Chen SPM reconstruction with explicit optional material overrides.

    Existing PropertyEstimate.electrode_mapping rejects tracer/analytic conversions.
    Scalar overrides require full stoichiometry support and exactly 298.15 K.
    The independent validation gate remains NOT ESTABLISHED even on successful solve.
    """
    import pybamm

    from physical_fpv.core import ModelConfig, parameter_fingerprint

    if not np.isfinite(duration_s) or not 0 < duration_s <= 60:
        raise ValueError("Bridge demonstration is bounded to 60 simulated seconds")
    config = ModelConfig(model="SPM", current_a=current_a, mesh_points=mesh_points)
    config.validate()  # preserves 0.5..7.5 A core domain; never high-C extension
    parameters = pybamm.ParameterValues("Chen2020")
    parameters.update(
        {
            "Current function [A]": current_a,
            "Ambient temperature [K]": 298.15,
            "Initial temperature [K]": 298.15,
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
            raise TypeError("Expected the existing provenance-aware PropertyEstimate")
        if electrode in seen:
            raise ValueError("Duplicate electrode override")
        seen.add(electrode)
        mapping = estimate.electrode_mapping(
            electrode, 298.15, phase=phase, stoichiometry_range=(0.0, 1.0)
        )
        parameters.update(mapping)
        sources.append(
            {
                "electrode": electrode,
                "estimate": asdict(estimate),
                "qualification": "caller supplied evidence; not independently verified",
            }
        )
    model = pybamm.lithium_ion.SPM(options={"thermal": "isothermal"})
    solver = pybamm.IDAKLUSolver(rtol=1e-8, atol=1e-8, options={"num_threads": 1})
    simulation = pybamm.Simulation(
        model,
        parameter_values=parameters,
        var_pts={
            "x_n": mesh_points,
            "x_s": 10,
            "x_p": mesh_points,
            "r_n": mesh_points,
            "r_p": mesh_points,
        },
        solver=solver,
    )
    times = np.linspace(0, duration_s, 61)
    solution = simulation.solve([0, duration_s], t_interp=times)
    voltage = np.asarray(solution["Voltage [V]"].entries)
    capacity = np.asarray(solution["Discharge capacity [A.h]"].entries)
    lithium = np.asarray(solution["Total lithium [mol]"].entries)
    charge_error = float(np.max(abs(capacity - current_a * times / 3600)))
    lithium_error = float(np.max(abs(lithium - lithium[0])))
    payload = {
        "schema": "fpv-material-spm-v1",
        "time_s": times.tolist(),
        "voltage_v": voltage.tolist(),
        "capacity_ah": capacity.tolist(),
        "sources": sources,
        "pybamm_version": pybamm.__version__,
        "parameter_fingerprint": parameter_fingerprint(parameters),
        "parameters_used": {
            k: parameters[k]
            for k in [
                "Negative particle diffusivity [m2.s-1]",
                "Positive particle diffusivity [m2.s-1]",
            ]
        },
        "physical_audit": {
            "charge_error_ah": charge_error,
            "lithium_error_mol": lithium_error,
            "passed": charge_error < 1e-7 and lithium_error < 1e-9,
        },
        "empirical_gate": "NOT ESTABLISHED",
        "duration_s": duration_s,
        "current_a": current_a,
        "scope": "bounded cell parameter bridge only; not FPV pack or high-C qualification",
    }
    payload["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload
