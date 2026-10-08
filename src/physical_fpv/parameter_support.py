"""Inspect a published parameter representation and its sampled input envelope.

These are descriptive provenance checks, not new experimental acceptance gates.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from pathlib import Path

import numpy as np

KINETIC_HEADER = ["Stoichiometry", "Exchange Current Density / mA cm-2"]


def exchange_points(root: Path, manifest: dict) -> list[dict]:
    points = []
    for member in manifest["files"]:
        path = (root / member["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Parameter fixture leaves the repository")
        content = path.read_bytes()
        if (
            len(content) != member["size_bytes"]
            or hashlib.sha256(content).hexdigest() != member["sha256"]
        ):
            raise ValueError("Original parameter CSV bytes differ from the manifest")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if reader.fieldnames != member["header"]:
            raise ValueError("Parameter measurement header/units changed")
        if member["kind"] != "exchange_current":
            continue
        if reader.fieldnames != KINETIC_HEADER or member["electrode"] not in (
            "negative",
            "positive",
        ):
            raise ValueError("Unsupported exchange-current schema")
        temperature = float(member["temperature_C"]) + 273.15
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("Invalid absolute measurement temperature")
        for row_number, row in enumerate(reader, 2):
            x, raw_j0 = float(row[KINETIC_HEADER[0]]), float(row[KINETIC_HEADER[1]])
            if not (math.isfinite(x) and 0 <= x <= 1 and math.isfinite(raw_j0) and raw_j0 >= 0):
                raise ValueError("Invalid exchange-current measurement")
            points.append(
                {
                    "electrode": member["electrode"],
                    "temperature_k": temperature,
                    "electrode_stoichiometry": x,
                    "released_exchange_current_a_m2": raw_j0 * 10,
                    "source_path": member["path"],
                    "source_sha256": member["sha256"],
                    "source_csv_row": row_number,
                }
            )
    if not points:
        raise ValueError("No released exchange-current points")
    return points


def compare_fixed_functions(points, parameters):
    rows = []
    for point in points:
        name = point["electrode"]
        limit = parameters[f"Maximum concentration in {name} electrode [mol.m-3]"]
        value = parameters[f"{name.title()} electrode exchange-current density [A.m-2]"](
            1000.0, point["electrode_stoichiometry"] * limit, limit, point["temperature_k"]
        )
        predicted = float(
            parameters.process_symbol(value).evaluate() if hasattr(value, "evaluate") else value
        )
        if not math.isfinite(predicted) or predicted < 0:
            raise ValueError("Fixed parameter function returned invalid exchange current")
        rows.append(
            {
                **point,
                "installed_exchange_current_a_m2": predicted,
                "installed_minus_released_a_m2": predicted
                - point["released_exchange_current_a_m2"],
            }
        )
    summaries = []
    groups = sorted({(r["electrode"], r["temperature_k"]) for r in rows})
    for electrode, temperature in groups:
        group = [
            r for r in rows if (r["electrode"], r["temperature_k"]) == (electrode, temperature)
        ]
        errors = np.array([r["installed_minus_released_a_m2"] for r in group])
        summaries.append(
            {
                "electrode": electrode,
                "temperature_k": temperature,
                "points": len(group),
                "unweighted_point_rmse_a_m2": float(np.sqrt(np.mean(errors**2))),
                "maximum_absolute_point_error_a_m2": float(np.max(np.abs(errors))),
            }
        )
    return {"points": rows, "summaries": summaries, "fitting_performed": False}


def assess_surface_support(model_metadata, points):
    """Use saved full-trajectory surface extrema; do not infer crossing times."""
    audit = model_metadata["physical_audit"]
    if audit["passed"] is not True:
        raise ValueError("Saved physical audit did not pass")
    support = {}
    for name in ("negative", "positive"):
        source = [p for p in points if p["electrode"] == name]
        if not source:
            raise ValueError("Missing electrode measurement support")
        x_values = [p["electrode_stoichiometry"] for p in source]
        t_values = [p["temperature_k"] for p in source]
        bounds = audit["concentration_bounds"][name]
        if not {"limit_mol_m3", "surface_min_mol_m3", "surface_max_mol_m3"} <= bounds.keys():
            raise ValueError("Saved surface concentration extrema are unavailable")
        limit = float(bounds["limit_mol_m3"])
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("Invalid maximum concentration")
        interval = [bounds["surface_min_mol_m3"] / limit, bounds["surface_max_mol_m3"] / limit]
        if not all(math.isfinite(x) for x in interval) or interval[0] > interval[1]:
            raise ValueError("Invalid saved surface concentration interval")
        sampled = [min(x_values), max(x_values)]
        support[name] = {
            "sampled_stoichiometry_envelope": sampled,
            "sampled_temperature_envelope_k": [min(t_values), max(t_values)],
            "recorded_surface_stoichiometry_envelope": interval,
            "below_sampled_stoichiometry": interval[0] < sampled[0],
            "above_sampled_stoichiometry": interval[1] > sampled[1],
            "inside_sampled_stoichiometry_envelope": interval[0] >= sampled[0]
            and interval[1] <= sampled[1],
            "crossing_times_s": None,
            "fraction_of_trajectory_outside": None,
            "full_cell_soc_mapping_established": False,
            "interpretation": (
                "Envelope of released half-cell stoichiometry points, not a full-cell SOC range "
                "or validity guarantee between samples. Saved extrema establish coverage only; "
                "crossing times and duration cannot be recovered from extrema."
            ),
        }
    return support
