"""Read-only, single-cell polarization accounting from an already solved model.

No solve, fitting, interpolation, or change to the model is performed here. Spatial
observables use ``entries`` at physical finite-volume nodes, never plotting ghosts.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pybamm
from pybamm.models.submodels.particle.base_particle import BaseParticle
from pybamm.models.submodels.particle.total_particle_concentration import TotalConcentration

from physical_fpv.core import SimulationResult, parameter_fingerprint, simulate
from physical_fpv.current_profile import CurrentProfile

ACCOUNTING_TOLERANCE = 1e-6
# Exact split-by-electrode names and signs in the installed plot_voltage_components.
# This exporter deliberately requires one series cell, so battery and cell volts agree.
VOLTAGE_TERMS = (
    ("negative_bulk_ocp", "Negative electrode bulk open-circuit potential [V]", -1),
    ("positive_bulk_ocp", "Positive electrode bulk open-circuit potential [V]", 1),
    ("negative_particle", "Negative particle concentration overpotential [V]", -1),
    ("positive_particle", "Positive particle concentration overpotential [V]", 1),
    ("negative_reaction", "X-averaged negative electrode reaction overpotential [V]", -1),
    ("positive_reaction", "X-averaged positive electrode reaction overpotential [V]", 1),
    ("electrolyte_concentration", "X-averaged battery concentration overpotential [V]", 1),
    ("electrolyte_ohmic", "X-averaged battery electrolyte ohmic losses [V]", 1),
    ("negative_solid_ohmic", "X-averaged battery negative solid phase ohmic losses [V]", -1),
    ("positive_solid_ohmic", "X-averaged battery positive solid phase ohmic losses [V]", 1),
    ("contact", "Contact overpotential [V]", -1),
)


def _source(function) -> dict:
    lines, first_line = inspect.getsourcelines(function)
    source_file = Path(inspect.getsourcefile(function))
    package_root = (
        Path(pybamm.__file__).parent.parent
        if function.__module__.startswith("pybamm.")
        else Path(__file__).parent.parent
    )
    return {
        "function": f"{function.__module__}.{function.__qualname__}",
        "module": function.__module__,
        "qualname": function.__qualname__,
        "source_sha256": hashlib.sha256("".join(lines).encode()).hexdigest(),
        "package_file": str(source_file.relative_to(package_root)),
        "package_file_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
        "line_range": [first_line, first_line + len(lines) - 1],
    }


def _statistics(values: np.ndarray, time: np.ndarray) -> dict:
    def point(index):
        index = int(index) % len(time)
        return {"value": float(values[index]), "time_s": float(time[index]), "index": int(index)}

    return {
        "initial": point(0),
        "endpoint": point(-1),
        "minimum": point(np.argmin(values)),
        "maximum": point(np.argmax(values)),
        "peak_absolute": point(np.argmax(np.abs(values))),
        "raw_sign_observed": (
            "zero"
            if np.all(values == 0)
            else "nonnegative"
            if np.all(values >= 0)
            else "nonpositive"
            if np.all(values <= 0)
            else "mixed"
        ),
    }


def export_polarization(
    output_dir: Path,
    result: SimulationResult,
    solution,
    parameters: pybamm.ParameterValues,
    *,
    current_profile: CurrentProfile | None = None,
) -> dict:
    """Export native-time CSV observables and a JSON summary with accounting gates.

    The caller supplies the cached ``Simulation.solution`` immediately after
    ``core.simulate`` and the exact numerical parameter values used for that solve.
    Accounting failure is exported as a failed gate; unsupported/mismatched inputs
    raise before writing. The caller owns the solve and any scientific interpretation.
    """
    time = np.asarray(result.time_s, dtype=float)
    if (
        time.ndim != 1
        or time.size < 2
        or not np.isfinite(time).all()
        or np.any(np.diff(time) <= 0)
        or not np.array_equal(time, solution.t)
    ):
        raise ValueError("Result and solution must share finite, increasing native output times")
    expected_fingerprint = parameter_fingerprint(parameters)
    profile_identity = None
    if current_profile is not None:
        expected_fingerprint = hashlib.sha256(
            (
                expected_fingerprint
                + ":piecewise-linear-current:"
                + current_profile.fingerprint_sha256
            ).encode()
        ).hexdigest()
        if (result.current_protocol or {}).get("fingerprint_sha256") != (
            current_profile.fingerprint_sha256
        ):
            raise ValueError("Result current-profile identity does not match diagnostic input")
        actual_current = np.asarray(solution["Current [A]"].entries, dtype=float).reshape(-1)
        expected_current = np.asarray(current_profile.value_at(time))
        if (
            actual_current.shape != time.shape
            or not np.isfinite(actual_current).all()
            or np.max(np.abs(actual_current - expected_current)) > 1e-9
        ):
            raise ValueError("Solved current does not reproduce the declared waveform")
        profile_identity = {
            "fingerprint_sha256": current_profile.fingerprint_sha256,
            "actual_solution_current_max_difference_a": float(
                np.max(np.abs(actual_current - expected_current))
            ),
            "scalar_parameter_current_is_envelope_metadata_only": True,
        }
    if expected_fingerprint != result.parameter_fingerprint:
        raise ValueError("Parameter fingerprint does not match the supplied result")
    options = solution.all_models[0].options
    required = {
        "working electrode": "both",
        "particle phases": "1",
        "dimensionality": 0,
        "SEI": "none",
        "lithium plating": "none",
        "loss of active material": "none",
    }
    if any(options[key] != value for key, value in required.items()):
        raise ValueError("Accounting requires a full, single-phase cell without side reactions")
    if parameters["Number of cells connected in series to make a battery"] != 1:
        raise ValueError("Accounting currently supports one series cell only")

    columns = {"time_s": time}
    series = {"time_s": {"variable": "Time [s]", "units": "s"}}
    profiles = {}

    def entries(name):
        values = np.asarray(solution[name].entries, dtype=float)
        if values.shape[-1:] != time.shape or not np.isfinite(values).all():
            raise ValueError(f"Nonfinite or non-native-time entries: {name}")
        return values

    def add(key, values, variable, units, **metadata):
        values = np.asarray(values, dtype=float)
        if values.shape != time.shape or not np.isfinite(values).all():
            raise ValueError(f"Invalid scalar trajectory: {key}")
        columns[key] = values
        series[key] = {"variable": variable, "units": units, **metadata}
        return values

    def scalar(key, name, units):
        return add(key, entries(name).reshape(-1), name, units)

    capacity = scalar("capacity_ah", "Discharge capacity [A.h]", "A.h")
    terminal = scalar("terminal_voltage_v", "Terminal voltage [V]", "V")
    scalar("bulk_temperature_k", "Volume-averaged cell temperature [K]", "K")
    scalar("imposed_surface_boundary_temperature_k", "Volume-averaged surface temperature [K]", "K")
    scalar("ambient_temperature_k", "Volume-averaged ambient temperature [K]", "K")
    scalar("bulk_ocv_v", "Bulk open-circuit voltage [V]", "V")
    reconstructed = np.zeros_like(time)
    terms = []
    for key, name, sign in VOLTAGE_TERMS:
        raw_key, signed_key = f"{key}_raw_v", f"{key}_signed_v"
        raw = scalar(raw_key, name, "V")
        signed = add(signed_key, sign * raw, name, "V", multiplier=sign)
        reconstructed += signed
        terms.append(
            {
                "term": key,
                "variable": name,
                "units": "V",
                "raw_column": raw_key,
                "signed_column": signed_key,
                "rawsign": "unmodified PyBaMM entries",
                "signed_multiplier": sign,
                "raw_sign_observed": _statistics(raw, time)["raw_sign_observed"],
            }
        )
    add("reconstructed_voltage_v", reconstructed, "sum of signed voltage terms", "V")
    voltage_error = add(
        "voltage_reconstruction_error_v",
        reconstructed - terminal,
        "reconstructed voltage - Terminal voltage [V]",
        "V",
    )

    charge_errors, capacities, capacity_errors, mean_errors = {}, {}, {}, {}
    initial_mean_errors, declared_initial = {}, {}
    for electrode, direction in (("negative", -1), ("positive", 1)):
        title = electrode.capitalize()
        mean = scalar(
            f"{electrode}_volume_mean_stoichiometry", f"{title} electrode stoichiometry", "1"
        )
        average = scalar(
            f"{electrode}_particle_average_stoichiometry",
            f"Average {electrode} particle stoichiometry",
            "1",
        )
        scalar(
            f"{electrode}_surface_x_average_stoichiometry",
            f"X-averaged {electrode} particle surface stoichiometry",
            "1",
        )
        for label, name, coordinate in (
            ("r_average", f"R-averaged {electrode} particle stoichiometry", "electrode x"),
            ("x_average", f"X-averaged {electrode} particle stoichiometry", "particle r"),
            ("surface", f"{title} particle surface stoichiometry", "electrode x"),
        ):
            values = entries(name)
            nodes = np.asarray(solution[name].mesh.nodes, dtype=float)
            if values.ndim != 2 or nodes.shape != values.shape[:-1]:
                raise ValueError(f"Expected a native one-dimensional spatial profile: {name}")
            key = f"{electrode}_{label}_stoichiometry"
            names = [f"{key}_node_{i:03d}" for i in range(len(nodes))]
            columns.update(zip(names, values, strict=True))
            profiles[key] = {
                "variable": name,
                "units": "1",
                "coordinate": coordinate,
                "coordinate_units": "m",
                "nodes": nodes.tolist(),
                "entries_shape": list(values.shape),
                "csv_columns": names,
                "reduction": "native entries; no spatial interpolation or ghosts",
            }
            if label == "surface":
                for extremum, operation in (("min", np.min), ("max", np.max)):
                    add(
                        f"{electrode}_surface_{extremum}_stoichiometry",
                        operation(values, axis=0),
                        name,
                        "1",
                        reduction=f"{extremum} over physical electrode nodes, from .entries",
                    )

        # Fixed active volumes and no side reactions: q changes mean electrode inventory.
        geometric_capacity = (
            float(pybamm.constants.F.value)
            / 3600
            * parameters[f"Maximum concentration in {electrode} electrode [mol.m-3]"]
            * parameters[f"{title} electrode active material volume fraction"]
            * parameters[f"{title} electrode thickness [m]"]
            * parameters["Electrode height [m]"]
            * parameters["Electrode width [m]"]
            * parameters["Number of electrodes connected in parallel to make a cell"]
        )
        if not np.isfinite(geometric_capacity) or geometric_capacity <= 0:
            raise ValueError(f"Invalid fixed active capacity for {electrode}")
        capacities[electrode] = float(geometric_capacity)
        native_capacity = scalar(
            f"{electrode}_active_capacity_ah", f"{title} electrode capacity [A.h]", "A.h"
        )
        capacity_errors[electrode] = float(np.max(np.abs(native_capacity - geometric_capacity)))
        initial = (
            parameters[f"Initial concentration in {electrode} electrode [mol.m-3]"]
            / parameters[f"Maximum concentration in {electrode} electrode [mol.m-3]"]
        )
        declared_initial[electrode] = float(initial)
        initial_mean_errors[electrode] = float(abs(mean[0] - initial))
        expected = add(
            f"{electrode}_charge_expected_stoichiometry",
            initial + direction * capacity / geometric_capacity,
            f"parameter c0/cmax {direction:+d} * discharged Ah / fixed active Ah",
            "1",
        )
        errors = add(
            f"{electrode}_mean_charge_error",
            mean - expected,
            "volume-averaged stoichiometry - charge-conservation expectation",
            "1",
        )
        charge_errors[electrode] = float(np.max(np.abs(errors)))
        mean_errors[electrode] = float(np.max(np.abs(mean - average)))

    result_errors = {}
    for name, original in (
        ("terminal_voltage_v", result.voltage_v),
        ("capacity_ah", result.capacity_ah),
        ("bulk_temperature_k", result.temperature_k),
    ):
        original = np.asarray(original, dtype=float)
        if original.shape != time.shape or not np.isfinite(original).all():
            raise ValueError(f"Invalid supplied result trajectory: {name}")
        result_errors[name] = float(np.max(np.abs(columns[name] - original)))
    maximum_voltage_error = float(np.max(np.abs(voltage_error)))
    accounting_passed = all(
        error <= ACCOUNTING_TOLERANCE
        for error in (
            maximum_voltage_error,
            *charge_errors.values(),
            *initial_mean_errors.values(),
            *mean_errors.values(),
            *capacity_errors.values(),
            *result_errors.values(),
        )
    )
    states = []
    for label, fraction in (
        ("initial", 0),
        ("early", 0.1),
        ("middle", 0.5),
        ("late", 0.9),
        ("end", 1),
    ):
        target = time[0] + fraction * (time[-1] - time[0])
        index = int(np.argmin(np.abs(time - target)))
        states.append(
            {
                "label": label,
                "target_time_fraction": fraction,
                "index": index,
                "time_s": float(time[index]),
                "scalars": {key: float(columns[key][index]) for key in series},
                "profiles": {
                    key: [float(columns[c][index]) for c in p["csv_columns"]]
                    for key, p in profiles.items()
                },
            }
        )
    for key in series:
        series[key]["summary"] = _statistics(columns[key], time)
    parameter_values = {
        name: _source(value) if callable(value) else value for name, value in parameters.items()
    }
    summary = {
        "schema_version": 1,
        "accounting_passed": accounting_passed,
        "voltage_reconstruction_max_error_v": maximum_voltage_error,
        "mean_stoichiometry_charge_max_error": charge_errors,
        "accounting_tolerance": {
            "voltage_v": ACCOUNTING_TOLERANCE,
            "absolute_stoichiometry": ACCOUNTING_TOLERANCE,
        },
        "accounting": {
            "fixed_active_capacity_ah": capacities,
            "capacity_variable_max_error_ah": capacity_errors,
            "volume_vs_particle_mean_max_error": mean_errors,
            "solution_vs_result_max_error": result_errors,
            "declared_initial_stoichiometry": declared_initial,
            "initial_mean_vs_declared_max_error": initial_mean_errors,
            "charge_relation": "theta(t) = parameter c0/cmax +/- Q(t)/Q_active",
            "faraday_constant_c_mol": float(pybamm.constants.F.value),
        },
        "voltage_terms": terms,
        "voltage_identity": "U_bulk_positive - U_bulk_negative + sum(signed overpotentials)",
        "series": series,
        "profiles": profiles,
        "states": states,
        "state_selection": "Nearest existing output time to 0%, 10%, 50%, 90%, 100% of run",
        "result_metadata": result.metadata(),
        "provenance": {
            "pybamm_version": pybamm.__version__,
            "parameter_fingerprint": result.parameter_fingerprint,
            "current_profile": profile_identity,
            "parameters": parameter_values,
            "model_options": dict(options),
            "functions": [
                _source(f)
                for f in (
                    pybamm.plot_voltage_components,
                    simulate,
                    BaseParticle._get_standard_concentration_variables,
                    TotalConcentration.get_coupled_variables,
                )
            ],
        },
        "limitations": [
            "Accounting identities are not experimental validation or mesh-convergence evidence.",
            "Electrode stoichiometries are model lithium fractions, not measured cell SOC.",
            "Charge accounting assumes constant active volumes and no side reactions.",
            "R averages use spherical volume weights; X averages use electrode-thickness weights.",
            "Bulk OCPs and overpotentials are model observables, not direct measurements.",
            "Overpotential signs are preserved, not rectified into positive loss magnitudes.",
            "Extrema cover native output times and physical nodes, not all continuous space/time.",
            "Default surface temperature is imposed ambient; lumped bulk temperature is dynamic.",
            "Contact term is exported even when zero; default model disables contact resistance.",
            "No fitting, smoothing, extra solve, or changed model parameters in this extraction.",
        ],
    }
    # Serialize before touching the destination; reject non-JSON provenance/NaN values.
    encoded = json.dumps(summary, indent=2, allow_nan=False) + "\n"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "polarization.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(zip(*columns.values(), strict=True))
    (output / "polarization.json").write_text(encoded, encoding="utf-8")
    return summary
