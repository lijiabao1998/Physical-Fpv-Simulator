"""Small, explicit multiscale contracts. No atom arrangement -> capacity bonus shortcut.

The analytical jump-network calculation is a method benchmark, not a battery material
prediction. Electronic structure, migration barriers, defects and thermodynamic factors
must come from separately qualified calculations/measurements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

BOLTZMANN_EV_K = 8.617333262145e-5


@dataclass(frozen=True)
class PropertyEstimate:
    name: Literal["chemical_diffusivity", "tracer_diffusivity", "electronic_conductivity"]
    value: float
    unit: str
    temperature_k: float
    validity_temperature_k: tuple[float, float]
    uncertainty_fraction: float
    evidence_kind: Literal["measured", "atomistic_calculation", "analytic_benchmark"]
    method: str
    source: str
    structure_sha256: str
    phase: str
    stoichiometry_support: tuple[float, float]
    spatial_scope: Literal["intrinsic_particle", "effective_electrode", "analytic_only"]

    def validate(self) -> None:
        units = {
            "chemical_diffusivity": "m2/s",
            "tracer_diffusivity": "m2/s",
            "electronic_conductivity": "S/m",
        }
        if self.name not in units or self.unit != units[self.name]:
            raise ValueError("Unknown property or incompatible SI units")
        scalars = (
            self.value,
            self.temperature_k,
            *self.validity_temperature_k,
            self.uncertainty_fraction,
        )
        if not np.isfinite(scalars).all() or self.value <= 0 or self.temperature_k <= 0:
            raise ValueError("Properties must be finite and positive")
        low, high = self.validity_temperature_k
        if not 0 < low <= self.temperature_k <= high:
            raise ValueError("Property evaluated outside its declared temperature support")
        if not 0 <= self.uncertainty_fraction <= 1:
            raise ValueError("Relative uncertainty must be supplied in [0, 1]")
        if self.evidence_kind not in {"measured", "atomistic_calculation", "analytic_benchmark"}:
            raise ValueError("Unknown evidence class")
        if (
            len(self.stoichiometry_support) != 2
            or not np.isfinite(self.stoichiometry_support).all()
            or not 0 <= self.stoichiometry_support[0] < self.stoichiometry_support[1] <= 1
        ):
            raise ValueError("Specify a valid supported lithium stoichiometry interval in [0, 1]")
        if not self.phase.strip() or self.spatial_scope not in {
            "intrinsic_particle",
            "effective_electrode",
            "analytic_only",
        }:
            raise ValueError("Phase and intrinsic/effective spatial scope must be explicit")
        if not self.method.strip() or not self.source.strip():
            raise ValueError("Method and evidence source are required")
        if len(self.structure_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.structure_sha256
        ):
            raise ValueError("A valid SHA256 ties the estimate to a specific structure")

    def electrode_mapping(
        self,
        electrode: str,
        temperature_k: float,
        *,
        phase: str,
        stoichiometry_range: tuple[float, float],
    ) -> dict:
        self.validate()
        if electrode not in {"negative", "positive"}:
            raise ValueError("Electrode must be negative or positive")
        if self.evidence_kind == "analytic_benchmark":
            raise ValueError("Analytical method benchmarks are not qualified battery properties")
        if self.name != "chemical_diffusivity":
            raise ValueError(
                "Only chemical diffusivity maps here; tracer diffusion needs a "
                "separately qualified thermodynamic/correlation conversion"
            )
        if not np.isclose(temperature_k, self.temperature_k, rtol=0, atol=1e-6):
            raise ValueError("A scalar property cannot be silently extrapolated in temperature")
        low, high = stoichiometry_range
        if (
            not np.isfinite([low, high]).all()
            or not self.stoichiometry_support[0] <= low < high <= self.stoichiometry_support[1]
        ):
            raise ValueError("Requested stoichiometry range exceeds the supporting evidence")
        if self.phase != phase or self.spatial_scope != "intrinsic_particle":
            raise ValueError(
                "Particle diffusion requires matching phase and intrinsic spatial scope"
            )
        return {f"{electrode.capitalize()} particle diffusivity [m2.s-1]": self.value}


def uncorrelated_jump_diffusivity(
    displacements_m: np.ndarray,
    barriers_ev: np.ndarray,
    attempt_frequencies_hz: np.ndarray,
    temperature_k: float,
) -> np.ndarray:
    """D = 1/2 sum_j k_j r_j tensor r_j for a zero-drift Poisson jump network.

    Each directed neighbour is listed separately. Assumes independent hops, fixed site
    occupancy, classical Arrhenius rates, no correlated motion, no blocking and no drift.
    Migration barriers are NOT formation energies. Result is a tracer diffusion tensor;
    it is not chemical diffusion or ionic/electronic conductivity.
    """
    jumps = np.asarray(displacements_m, dtype=float)
    barriers = np.asarray(barriers_ev, dtype=float)
    frequency = np.asarray(attempt_frequencies_hz, dtype=float)
    if jumps.ndim != 2 or jumps.shape[1] != 3 or not 1 <= len(jumps) <= 128:
        raise ValueError("Provide 1 to 128 explicit three-dimensional directed jumps")
    if barriers.shape != (len(jumps),) or frequency.shape != (len(jumps),):
        raise ValueError("One barrier and attempt frequency are required per jump")
    if not all(np.isfinite(x).all() for x in (jumps, barriers, frequency)):
        raise ValueError("Jump inputs must be finite")
    if not np.isfinite(temperature_k) or not 1 <= temperature_k <= 2000:
        raise ValueError("Analytical benchmark temperature must be in [1, 2000] K")
    if np.any(barriers < 0) or np.any(frequency <= 0):
        raise ValueError("Migration barriers must be nonnegative and frequencies positive")
    lengths = np.linalg.norm(jumps, axis=1)
    if np.any((lengths < 1e-12) | (lengths > 1e-7)):
        raise ValueError("Jump displacement lengths must be expressed in metres")
    rates = frequency * np.exp(-barriers / (BOLTZMANN_EV_K * temperature_k))
    drift = np.sum(rates[:, None] * jumps, axis=0)
    scale = float(np.sum(rates * lengths))
    if np.linalg.norm(drift) > max(1e-30, 1e-10 * scale):
        raise ValueError("Nonzero drift: this equilibrium benchmark requires balanced jumps")
    return 0.5 * np.einsum("i,ij,ik->jk", rates, jumps, jumps)


def analytic_material_example() -> dict:
    spacing = 3e-10
    jumps = np.vstack([np.eye(3), -np.eye(3)]) * spacing
    barriers = np.full(6, 0.5)
    frequencies = np.full(6, 1e13)
    temperature = 298.15
    tensor = uncorrelated_jump_diffusivity(jumps, barriers, frequencies, temperature)
    structure = {
        "lattice": "hypothetical simple cubic",
        "spacing_m": spacing,
        "barrier_ev": 0.5,
        "attempt_frequency_hz": 1e13,
    }
    estimate = PropertyEstimate(
        "tracer_diffusivity",
        float(np.trace(tensor) / 3),
        "m2/s",
        temperature,
        (temperature, temperature),
        1.0,
        "analytic_benchmark",
        "uncorrelated classical Arrhenius random walk; prescribed migration barrier",
        "Analytical method check only; not an experimental or ab-initio material",
        hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest(),
        "hypothetical simple cubic",
        (0.0, 1.0),
        "analytic_only",
    )
    estimate.validate()
    return {
        "status": "hypothetical analytical benchmark, NOT a discovered battery material",
        "structure": structure,
        "diffusion_tensor_m2_s": tensor.tolist(),
        "estimate": asdict(estimate),
        "battery_parameter_mapping_allowed": False,
        "missing": [
            "calculated migration pathways/barriers",
            "defect concentrations",
            "correlation and thermodynamic factors",
            "phase/electrochemical stability",
            "electrode characterization",
            "independent cell validation",
        ],
    }
