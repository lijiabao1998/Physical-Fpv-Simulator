"""Isolated, unvalidated k2 low-rate research configuration and scalar-output build.

This module does not extend ModelConfig or bypass the ordinary core's current
checks. Scientific execution requires the separately reviewed bounded runner.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pybamm

from physical_fpv.core import parameter_fingerprint
from physical_fpv.current_profile import CurrentProfile

LOW_GZIP_SHA = "5c5f0969e411d2be96bcdbb02cfcb397e2fd79d8ad92a26e5466f311d70ae5ef"
LOW_CSV_SHA = "4c551b20febfc90e59df25a3ef9321aa975a328143a84d6d5f5c427e968f64a9"
LOW_RECEIPT_SHA = "984b83c1f105493f14d5894441c7bcebee2474e2c3904313213e71633ac89eda"
CROSS_RATE_SHA = "92bdf117f74347824d3bcfda6553f0b0b66afc914c3152ba7317924836f83382"
CORE_SHA = "1295d1b51e0989021b037ecc8a5b7b66d8e38da43958cfd1df98bc1c031f506b"
INITIAL_TEMPERATURE_K = 297.4955352783203
AMBIENT_TEMPERATURE_K = 298.15
MAX_TEMPERATURE_K = 333.15
FINAL_INPUT_TIME_S = 70369.9178

BASE_OUTPUTS = {
    "voltage_v": "Terminal voltage [V]",
    "capacity_ah": "Discharge capacity [A.h]",
    "temperature_k": "Volume-averaged cell temperature [K]",
    "lithium_inventory_mol": "Total lithium [mol]",
    "heating_w": "Total heating [W]",
    "cooling_w": "Surface total cooling [W]",
    "heat_capacity_volumetric_j_k_m3": "Volume-averaged effective heat capacity [J.K-1.m-3]",
}
FIELDS = {
    "negative_node": "Negative particle concentration [mol.m-3]",
    "negative_surface": "Negative particle surface concentration [mol.m-3]",
    "positive_node": "Positive particle concentration [mol.m-3]",
    "positive_surface": "Positive particle surface concentration [mol.m-3]",
    "electrolyte": "Electrolyte concentration [mol.m-3]",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError("Input identity changed: " + path.name)
    return data


@dataclass(frozen=True)
class LowRateInput:
    observed: np.ndarray  # time, positive current, voltage, skin K
    profile: CurrentProfile
    output_time_s: np.ndarray
    mean_current_a: float
    initial_assumed_charge_ah: float
    metadata: dict


def prepare(root: Path) -> LowRateInput:
    verified(root / "src/physical_fpv/core.py", CORE_SHA)
    source = root / "docs/benchmarks"
    packed = verified(source / "stanford-k2-low-rate-discharge.csv.gz", LOW_GZIP_SHA)
    raw = gzip.decompress(packed)
    if sha256(raw) != LOW_CSV_SHA:
        raise ValueError("Normalized CSV identity changed")
    receipt = json.loads(verified(source / "stanford-k2-low-rate-source.json", LOW_RECEIPT_SHA))
    prior = json.loads(verified(source / "stanford-cross-rate-onset.json", CROSS_RATE_SHA))
    if prior["comparison"]["cases"]["k2_005c"]["rest"]["endpoint_skin_k"] != INITIAL_TEMPERATURE_K:
        raise ValueError("Frozen initial-temperature proxy changed")
    reader = csv.DictReader(io.StringIO(raw.decode()))
    if reader.fieldnames != [
        "excel_row",
        "date_time_naive",
        "step_time_s",
        "raw_current_a",
        "voltage_v",
        "skin_k",
    ]:
        raise ValueError("Unexpected normalized schema")
    rows = list(reader)
    if len(rows) != 70370 or receipt["discharge_rows"] != 70370:
        raise ValueError("Complete source row count changed")
    indices = [int(r["excel_row"]) for r in rows]
    dates = [datetime.fromisoformat(r["date_time_naive"]) for r in rows]
    if any(b != a + 1 for a, b in zip(indices[:-1], indices[1:], strict=True)):
        raise ValueError("Source rows missing or reordered")
    if any(b <= a for a, b in zip(dates[:-1], dates[1:], strict=True)):
        raise ValueError("Source dates not increasing")
    observed = np.array(
        [
            [
                float(r["step_time_s"]),
                -float(r["raw_current_a"]),
                float(r["voltage_v"]),
                float(r["skin_k"]),
            ]
            for r in rows
        ]
    )
    if not np.isfinite(observed).all() or np.any(np.diff(observed[:, 0]) <= 0):
        raise ValueError("Nonfinite or nonmonotone source")
    if observed[0, 0] != 1.0 or observed[-1, 0] != FINAL_INPUT_TIME_S:
        raise ValueError("Frozen measured support changed")
    if np.min(observed[:, 1]) < 0.249 or np.max(observed[:, 1]) > 0.251:
        raise ValueError("Outside isolated experimental current envelope")
    discrepancy = max(
        abs((d - dates[0]).total_seconds() - (t - observed[0, 0]))
        for d, t in zip(dates, observed[:, 0], strict=True)
    )
    if discrepancy > 1:
        raise ValueError("Date/step clock discrepancy")
    profile = CurrentProfile(np.r_[0.0, observed[:, 0]], np.r_[observed[0, 1], observed[:, 1]])
    from physical_fpv.contrast_persistence import time_at_charge

    query_times = [time_at_charge(observed, q) for q in np.arange(0.5, 4.51, 0.5)]
    output_time = np.unique(
        np.r_[np.arange(0.0, FINAL_INPUT_TIME_S, 1.0), FINAL_INPUT_TIME_S, query_times]
    )
    if len(output_time) > 71000:
        raise ValueError("Output sample cap exceeded")
    mean = float(np.trapezoid(observed[:, 1], observed[:, 0]) / (observed[-1, 0] - observed[0, 0]))
    missing_charge = float(profile.charge_integral_ah(observed[0, 0]))
    if abs(missing_charge - 0.00006945052080684238) > 1e-15:
        raise ValueError("Frozen initial assumed charge changed")
    observed.setflags(write=False)
    output_time.setflags(write=False)
    metadata = {
        "source_gzip_sha256": LOW_GZIP_SHA,
        "source_csv_sha256": LOW_CSV_SHA,
        "source_receipt_sha256": LOW_RECEIPT_SHA,
        "first_date_naive": dates[0].isoformat(),
        "last_date_naive": dates[-1].isoformat(),
        "source_rows": len(rows),
        "recorded_interval_s": [1.0, FINAL_INPUT_TIME_S],
        "initial_current_assumption_a": float(observed[0, 1]),
        "initial_assumed_charge_ah": missing_charge,
        "initial_bulk_temperature_proxy_k": INITIAL_TEMPERATURE_K,
        "initial_heat_capacity_domain_excursion_k": 298.15 - INITIAL_TEMPERATURE_K,
        "observed_initial_charge_known": False,
        "source_date_step_discrepancy_s": discrepancy,
        "output_samples": len(output_time),
        "output_time_sha256": sha256(output_time.astype("<f8").tobytes()),
        "no_input_tail_extension": True,
        "experimental_current_envelope_a": [0.249, 0.251],
        "ordinary_core_domain_unchanged": True,
    }
    return LowRateInput(observed, profile, output_time, mean, missing_charge, metadata)


def output_symbols(model):
    outputs = dict(BASE_OUTPUTS)
    for field, source in FIELDS.items():
        reductions = (
            (("min", pybamm.min),)
            if field == "electrolyte"
            else (("min", pybamm.min), ("max", pybamm.max))
        )
        for reduction, function in reductions:
            name = f"Experimental audit {field} {reduction}"
            model.variables[name] = function(model.variables[source])
            outputs[f"{field}_{reduction}_mol_m3"] = name
        outputs[f"{field}_finite_sum_mol_m3"] = f"Experimental finite witness {field}"
    if len(outputs) != 21:
        raise ValueError("Scalar audit specification changed")
    return outputs


def finite_witness(expression):
    """A full-field sum, including every entry, which propagates NaN/Inf."""
    size = int(expression.size)
    return (pybamm.Matrix(np.ones((1, size))) @ expression).without_domains()


def add_finite_witnesses(built, outputs):
    sizes = {}
    for field, name in FIELDS.items():
        expression = built.get_processed_variable(name)
        size = int(expression.size)
        # Every native spatial entry has coefficient one. CasADi extrema alone
        # ignore NaNs, so these finite-propagating sums are mandatory.
        witness = finite_witness(expression)
        key = outputs[f"{field}_finite_sum_mol_m3"]
        built.variables[key] = witness
        built.update_processed_variables({key: witness})
        sizes[field] = size
    for name in outputs.values():
        if int(np.prod(built.get_processed_variable(name).shape)) != 1:
            raise ValueError("Audit output is not scalar: " + name)
    return sizes


def build(prepared: LowRateInput, mesh: int):
    """Build/discretize only; this function never calls a solver."""
    if mesh not in (80, 120):
        raise ValueError("Only prospectively frozen meshes80/120")
    if prepared.profile.min_current_a < 0.249 or prepared.profile.max_current_a > 0.251:
        raise ValueError("Experimental current envelope violated")
    if prepared.profile.time_s[-1] != FINAL_INPUT_TIME_S:
        raise ValueError("Measured-support stop changed")
    model = pybamm.lithium_ion.DFN(options={"thermal": "lumped"})
    model.events.append(
        pybamm.Event(
            "Research temperature envelope",
            MAX_TEMPERATURE_K - model.variables["Volume-averaged cell temperature [K]"],
        )
    )
    parameters = pybamm.ParameterValues("ORegan2022")
    if parameters["Lower voltage cut-off [V]"] != 2.5:
        raise ValueError("Frozen cutoff changed")
    initial = {
        side: parameters[f"Initial concentration in {side} electrode [mol.m-3]"]
        for side in ("negative", "positive")
    }
    if initial != {"negative": 28866.0, "positive": 13975.0}:
        raise ValueError("Frozen initial concentrations changed")
    parameters.update(
        {
            "Current function [A]": prepared.mean_current_a,
            "Ambient temperature [K]": AMBIENT_TEMPERATURE_K,
            "Initial temperature [K]": INITIAL_TEMPERATURE_K,
            "Total heat transfer coefficient [W.m-2.K-1]": 15,
        }
    )
    fingerprint = hashlib.sha256(
        (
            parameter_fingerprint(parameters)
            + ":piecewise-linear-current:"
            + prepared.profile.fingerprint_sha256
        ).encode()
    ).hexdigest()
    parameters.update(
        {
            "Current function [A]": pybamm.Interpolant(
                prepared.profile.time_s,
                prepared.profile.current_a,
                pybamm.t,
                interpolator="linear",
                extrapolate=False,
            )
        }
    )
    outputs = output_symbols(model)
    solver = pybamm.IDAKLUSolver(
        rtol=1e-7,
        atol=1e-7,
        output_variables=list(outputs.values()),
        options={"num_threads": 1},
        on_extrapolation="error",
    )
    sim = pybamm.Simulation(
        model,
        parameter_values=parameters,
        var_pts={"x_n": mesh, "x_s": mesh // 2, "x_p": mesh, "r_n": mesh, "r_p": mesh},
        solver=solver,
    )
    sim.build()
    sizes = add_finite_witnesses(sim.built_model, outputs)
    metadata = {
        "experimental_protocol": "stanford-k2-low-rate-model-v1",
        "parameter_set": "ORegan2022",
        "model": "DFN",
        "thermal": "lumped",
        "mesh_points": mesh,
        "tolerance": 1e-7,
        "initial_concentrations_mol_m3": initial,
        "initial_temperature_k": INITIAL_TEMPERATURE_K,
        "ambient_temperature_k": AMBIENT_TEMPERATURE_K,
        "heat_transfer_coefficient_w_m2_k": 15,
        "minimum_voltage_v": 2.5,
        "maximum_temperature_k": MAX_TEMPERATURE_K,
        "mean_observed_current_a": prepared.mean_current_a,
        "parameter_and_profile_fingerprint_sha256": fingerprint,
        "forcing_sha256": prepared.profile.fingerprint_sha256,
        "output_storage": "IDAKLU scalar output variables plus final state",
        "scalar_output_names": outputs,
        "finite_witness_field_sizes": sizes,
        "electrode_maximum_concentrations_mol_m3": {
            side: parameters[f"Maximum concentration in {side} electrode [mol.m-3]"]
            for side in ("negative", "positive")
        },
        "cell_volume_m3": parameters["Cell volume [m3]"],
        "ordinary_core_certification_claimed": False,
    }
    return sim, outputs, metadata


def validate_output_grid(time, prepared):
    """Verify the frozen grid prefix and final point without a solver object."""
    time = np.asarray(time, dtype=float).reshape(-1)
    if len(time) < 2 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError("Invalid solver time grid")
    if time[0] != 0 or time[-1] > FINAL_INPUT_TIME_S:
        raise ValueError("Solver left measured forcing support")
    expected_before_end = prepared.output_time_s[prepared.output_time_s < time[-1]]
    if not np.array_equal(time[:-1], expected_before_end):
        raise ValueError("Prescribed observation points were dropped or changed")


def verify_endpoint(sim, arrays, endpoint, outputs):
    """Reevaluate saved scalar endpoints from the retained native final state."""
    time = arrays["time_s"]
    if endpoint.shape != (sim.built_model.len_rhs_and_alg, 1) or not np.isfinite(endpoint).all():
        raise ValueError("Invalid retained final state")
    endpoint_checks = {}
    for column, name in outputs.items():
        direct = float(
            np.asarray(
                sim.built_model.get_processed_variable(name).evaluate(
                    t=time[-1], y=endpoint, inputs={}
                )
            ).reshape(-1)[0]
        )
        saved = float(arrays[column][-1])
        tolerance = 256 * np.finfo(float).eps * max(1.0, abs(direct))
        endpoint_checks[column] = bool(
            np.isfinite(direct) and np.isfinite(saved) and abs(direct - saved) <= tolerance
        )
    if not all(endpoint_checks.values()):
        raise ValueError("Saved scalar output differs from true final state")
    return endpoint_checks


def collect_outputs(sim, solution, outputs, prepared):
    """Read scalar results and verify the prescribed grid and true endpoint."""
    time = np.asarray(solution.t, dtype=float).reshape(-1)
    validate_output_grid(time, prepared)
    if solution.t_event is None or float(np.asarray(solution.t_event).reshape(-1)[-1]) != time[-1]:
        raise ValueError("True final/event time not retained")
    if int(solution.y.size) != 0:
        raise ValueError("Dense state history was unexpectedly retained")
    arrays = {"time_s": time}
    for column, name in outputs.items():
        values = np.asarray(solution[name](time), dtype=float).reshape(-1)
        if values.shape != time.shape:
            raise ValueError("Unexpected scalar output shape")
        arrays[column] = values
    endpoint = np.asarray(solution.last_state.y)
    endpoint_checks = verify_endpoint(sim, arrays, endpoint, outputs)
    return arrays, {
        "requested_grid_preserved": True,
        "true_endpoint_preserved": True,
        "stored_full_history_values": 0,
        "last_state_shape": [int(v) for v in endpoint.shape],
        "endpoint_scalar_checks": endpoint_checks,
    }


def physical_audit(arrays, metadata, prepared):
    required = {"time_s", *metadata["scalar_output_names"]}
    if set(arrays) != required:
        raise ValueError("Scalar evidence schema changed")
    time = arrays["time_s"]
    if any(np.asarray(v).shape != time.shape for v in arrays.values()):
        raise ValueError("Scalar evidence lengths differ")
    nonfinite = [name for name, values in arrays.items() if not np.isfinite(values).all()]
    if nonfinite:
        return {
            "passed": False,
            "nonfinite_scalar_columns": nonfinite,
            "spatial_finiteness_witnesses_required": True,
        }
    if len(time) < 2 or np.any(np.diff(time) <= 0) or time[0] != 0:
        raise ValueError("Invalid audit time grid")
    lithium = arrays["lithium_inventory_mol"]
    if lithium[0] <= 0:
        return {"passed": False, "reason": "Nonpositive initial lithium inventory"}
    drift = float(np.max(np.abs(lithium - lithium[0])) / lithium[0])
    expected = prepared.profile.charge_integral_ah(time)
    charge_error = float(np.max(np.abs(arrays["capacity_ah"] - expected)))
    bounds = {}
    for side in ("negative", "positive"):
        minimum = min(
            float(np.min(arrays[f"{side}_{kind}_min_mol_m3"])) for kind in ("node", "surface")
        )
        maximum = max(
            float(np.max(arrays[f"{side}_{kind}_max_mol_m3"])) for kind in ("node", "surface")
        )
        limit = metadata["electrode_maximum_concentrations_mol_m3"][side]
        bounds[side] = {
            "minimum_mol_m3": minimum,
            "maximum_mol_m3": maximum,
            "limit_mol_m3": limit,
            "passed": minimum >= -1e-6 and maximum <= limit + 1e-6,
        }
    electrolyte_min = float(np.min(arrays["electrolyte_min_mol_m3"]))
    heat_capacity = arrays["heat_capacity_volumetric_j_k_m3"] * metadata["cell_volume_m3"]
    stored = float(np.trapezoid(heat_capacity, arrays["temperature_k"]))
    net = float(np.trapezoid(arrays["heating_w"] + arrays["cooling_w"], time))
    generated = float(np.trapezoid(np.abs(arrays["heating_w"]), time))
    thermal_error = abs(stored - net) / max(generated, 1.0)
    return {
        "lithium_inventory_relative_drift": drift,
        "charge_integral_error_ah": charge_error,
        "concentration_bounds": bounds,
        "electrolyte_min_mol_m3": electrolyte_min,
        "all_spatial_finiteness_witnesses_finite": True,
        "thermal_energy_balance": {
            "stored_energy_j": stored,
            "integrated_net_heat_j": net,
            "integrated_absolute_generated_heat_j": generated,
            "relative_to_generated_heat": thermal_error,
            "positive_heat_capacity": bool(np.all(heat_capacity > 0)),
            "passed": bool(np.all(heat_capacity > 0) and thermal_error <= 0.01),
        },
        "passed": bool(
            drift <= 1e-6
            and charge_error <= 1e-6
            and electrolyte_min > 0
            and all(b["passed"] for b in bounds.values())
            and np.all(heat_capacity > 0)
            and thermal_error <= 0.01
        ),
        "audit_scope": (
            "All prescribed sampled times; scalar extrema and whole-field finite witnesses"
        ),
    }


def empirical_report(prepared, arrays, termination, audit):
    from physical_fpv.stanford_benchmark import product_integral
    from physical_fpv.thermal_benchmark import THERMAL_GATES, piecewise_error, temperature_domains

    observed = prepared.observed
    time = arrays["time_s"]
    start = float(observed[0, 0])
    stop = min(float(observed[-1, 0]), float(time[-1]))
    if stop <= start:
        raise ValueError("No observed/model overlap")
    common = np.unique(
        np.r_[
            start,
            stop,
            observed[(observed[:, 0] > start) & (observed[:, 0] < stop), 0],
            time[(time > start) & (time < stop)],
        ]
    )
    measured_v = np.interp(common, observed[:, 0], observed[:, 2])
    model_v = np.interp(common, time, arrays["voltage_v"])
    measured_t = np.interp(common, observed[:, 0], observed[:, 3])
    model_t = np.interp(common, time, arrays["temperature_k"])
    vrmse, vmax = piecewise_error(common, model_v - measured_v)
    trmse, tmax = piecewise_error(common, model_t - measured_t)
    observed_q = float(np.trapezoid(observed[:, 1], observed[:, 0]) / 3600)
    endpoint_q = float(arrays["capacity_ah"][-1] - prepared.initial_assumed_charge_ah)
    observed_energy = product_integral(observed[:, 0], observed[:, 1], observed[:, 2]) / 3600
    energy_time = np.unique(
        np.r_[
            start,
            time[time > start],
            prepared.profile.time_s[
                (prepared.profile.time_s > start) & (prepared.profile.time_s < time[-1])
            ],
        ]
    )
    endpoint_energy = (
        product_integral(
            energy_time,
            prepared.profile.value_at(energy_time),
            np.interp(energy_time, time, arrays["voltage_v"]),
        )
        / 3600
    )
    cutoff = (
        termination == "event: Minimum voltage [V]"
        and abs(float(arrays["voltage_v"][-1]) - 2.5) <= 1e-6
    )
    capacity_error = abs(endpoint_q - observed_q) / observed_q if cutoff else None
    energy_error = abs(endpoint_energy - observed_energy) / observed_energy if cutoff else None
    coverage = (stop - start) / (observed[-1, 0] - start)
    electrical = {
        "voltage_rmse": vrmse <= THERMAL_GATES["voltage_rmse_v"],
        "voltage_max": vmax <= THERMAL_GATES["voltage_max_error_v"],
        "capacity": cutoff and capacity_error <= THERMAL_GATES["capacity_relative_error"],
        "energy": cutoff and energy_error <= THERMAL_GATES["energy_relative_error"],
        "coverage": bool(coverage >= THERMAL_GATES["min_coverage"]),
        "voltage_cutoff_reached": cutoff,
        "physical_audit": audit["passed"],
    }
    return {
        "voltage_rmse_v": vrmse,
        "voltage_max_error_v": vmax,
        "common_interval_s": [start, stop],
        "observed_time_coverage": float(coverage),
        "initial_assumed_charge_excluded_ah": prepared.initial_assumed_charge_ah,
        "measured_observed_charge_ah": observed_q,
        "predicted_endpoint_observed_start_charge_ah": endpoint_q,
        "predicted_cutoff_observed_start_charge_ah": endpoint_q if cutoff else None,
        "capacity_relative_error": capacity_error,
        "measured_observed_energy_wh": observed_energy,
        "predicted_endpoint_observed_start_energy_wh": endpoint_energy,
        "predicted_cutoff_observed_start_energy_wh": endpoint_energy if cutoff else None,
        "energy_relative_error": energy_error,
        "termination": termination,
        "cutoff_qualification_available": cutoff,
        "electrical_gates": electrical,
        "electrical_gates_passed": all(electrical.values()),
        "temperature_proxy_rmse_k": trmse,
        "temperature_proxy_max_error_k": tmax,
        "thermal_proxy_gates": {"rmse": trmse <= 2.0, "maximum": tmax <= 5.0},
        "temperature_domains": temperature_domains(observed[:, 3], arrays["temperature_k"]),
        "independent_thermal_validation_established": False,
        "independent_validation_established": False,
        "parameters_fitted": False,
        "empirical_thresholds": dict(THERMAL_GATES),
    }


def compare_meshes(coarse, fine, coarse_report, fine_report):
    end = min(float(coarse["time_s"][-1]), float(fine["time_s"][-1]))
    time = np.unique(
        np.r_[coarse["time_s"][coarse["time_s"] <= end], fine["time_s"][fine["time_s"] <= end], end]
    )
    differences = {
        key: float(
            np.max(
                np.abs(
                    np.interp(time, coarse["time_s"], coarse[key])
                    - np.interp(time, fine["time_s"], fine[key])
                )
            )
        )
        for key in ("voltage_v", "temperature_k")
    }
    coarse_q = coarse_report["empirical"]["predicted_endpoint_observed_start_charge_ah"]
    fine_q = fine_report["empirical"]["predicted_endpoint_observed_start_charge_ah"]
    if not np.isfinite([coarse_q, fine_q]).all() or min(coarse_q, fine_q) <= 0:
        raise ValueError("No positive observed-start endpoint capacity")
    relative_capacity = float(abs(coarse_q - fine_q) / fine_q)
    physical = coarse_report["physical_audit"]["passed"] and fine_report["physical_audit"]["passed"]
    cutoffs = (
        coarse_report["empirical"]["cutoff_qualification_available"]
        and fine_report["empirical"]["cutoff_qualification_available"]
    )
    common_pass = (
        differences["voltage_v"] <= 0.005 and differences["temperature_k"] <= 0.1 and physical
    )
    return {
        "common_support_end_s": end,
        "voltage_max_difference_v": differences["voltage_v"],
        "temperature_max_difference_k": differences["temperature_k"],
        "endpoint_capacity_relative_difference": relative_capacity,
        "common_support_mesh_check_passed": common_pass,
        "both_voltage_cutoffs_verified": cutoffs,
        "full_numerical_qualification_passed": common_pass
        and relative_capacity <= 0.01
        and cutoffs,
        "thresholds": {"voltage_v": 0.005, "temperature_k": 0.1, "relative_capacity": 0.01},
        "full_endpoint_status": "verified"
        if cutoffs
        else "UNVERIFIED: measured-support boundary or other termination",
    }
