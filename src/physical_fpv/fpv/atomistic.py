"""Bounded ASE EMT fcc-Al equation-of-state reference; not DFT/battery transport."""

from __future__ import annotations

import hashlib
import json

import numpy as np


def aluminum_eos(points=9, repeats=2):
    if type(points) is not int or points not in (7, 9, 11):
        raise ValueError("Use 7, 9 or 11 fixed strain points")
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise ValueError("Use 1..3 conventional-cell repeats (at most 108 atoms)")
    import ase
    from ase.build import bulk
    from ase.calculators.emt import EMT
    from ase.eos import EquationOfState
    from ase.units import _amu

    structure = bulk("Al", "fcc", a=4.05, cubic=True).repeat((repeats,) * 3)
    structure.calc = EMT()
    initial = structure.cell.copy()
    volumes = []
    energies = []
    forces = []
    for scale in np.linspace(0.96, 1.04, points):
        structure.set_cell(initial * scale, scale_atoms=True)
        volumes.append(structure.get_volume() / len(structure))
        energies.append(structure.get_potential_energy() / len(structure))
        forces.append(float(np.max(abs(structure.get_forces()))))
    v0, e0, bulk_ev_a3 = EquationOfState(volumes, energies, eos="birchmurnaghan").fit()
    if not min(volumes) < v0 < max(volumes) or bulk_ev_a3 <= 0:
        raise ValueError("No stable interior EOS fit")
    # 1 eV/angstrom^3 = 160.2176634 GPa. Density is 0-K perfect crystal only.
    density = float(structure.get_masses()[0] * _amu / (v0 * 1e-30))
    result = {
        "schema": "fpv-emt-al-eos-v1",
        "ase_version": ase.__version__,
        "method": "ASE empirical EMT / Birch-Murnaghan EOS; zero-K perfect fcc Al",
        "source": "https://docs.ase-lib.org/ase/calculators/emt.html",
        "structure": {
            "element": "Al",
            "lattice": "fcc",
            "initial_lattice_a": 4.05,
            "atoms": len(structure),
            "periodic": True,
        },
        "volume_per_atom_a3": volumes,
        "energy_per_atom_ev": energies,
        "equilibrium_volume_per_atom_a3": float(v0),
        "energy_min_ev_per_atom": float(e0),
        "bulk_modulus_gpa": float(bulk_ev_a3 * 160.2176634),
        "density_kg_m3": density,
        "max_force_ev_a": max(forces),
        "battery_mapping_allowed": False,
        "empirical_gate": "NOT ESTABLISHED",
        "limits": [
            "empirical potential, not ab initio",
            "no lithium migration or defect kinetics",
            "not measured frame or electrode density",
            "zero-temperature reference only",
        ],
    }
    result["structure_sha256"] = hashlib.sha256(
        json.dumps(result["structure"], sort_keys=True).encode()
    ).hexdigest()
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def frame_mass_kg(eos_result, solid_volume_m3):
    """Actual geometric density->mass mapping; hypothetical solid Al frame only."""
    if eos_result.get("schema") != "fpv-emt-al-eos-v1":
        raise ValueError("EMT reference result required")
    if not np.isfinite(solid_volume_m3) or not 0 < solid_volume_m3 <= 0.001:
        raise ValueError("Frame solid volume must be in (0, 0.001] m3")
    return eos_result["density_kg_m3"] * solid_volume_m3
