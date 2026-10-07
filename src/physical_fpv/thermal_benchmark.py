"""Fixed-protocol ORegan2022 thermal reproduction with inspectable residual evidence."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import replace
from pathlib import Path

import numpy as np

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.core import ModelConfig, SimulationResult, simulate
from physical_fpv.thermal_data import ThermalTrace, inspect_cohort, load_thermal_cohort
from physical_fpv.validation import compare_numerics, compare_trace, write_timeseries

THERMAL_PROTOCOL_SHA256 = "bb16c670d090854d1a2ade8ef300eec6c5ab39d1eb073182186113fb6de5d6cf"
THERMAL_GATES = {
    "voltage_rmse_v": 0.050,
    "voltage_max_error_v": 0.300,
    "temperature_rmse_k": 2.0,
    "temperature_max_error_k": 5.0,
    "capacity_relative_error": 0.05,
    "energy_relative_error": 0.05,
    "min_coverage": 0.95,
    "numerical_temperature_max_difference_k": 0.1,
}
PROPERTY_TEMPERATURE_DOMAINS_C = {
    "solid_diffusion_measurements": [5.0, 45.0],
    "exchange_current_measurements": [15.0, 45.0],
    "heat_capacity_measurements": [25.0, 100.0],
}


def piecewise_error(time: np.ndarray, difference: np.ndarray) -> tuple[float, float]:
    duration = time[-1] - time[0]
    if duration <= 0 or not np.isfinite(difference).all():
        raise ValueError("Invalid residual samples")
    integral = np.sum(
        np.diff(time)
        * (difference[:-1] ** 2 + difference[:-1] * difference[1:] + difference[1:] ** 2)
        / 3
    )
    return float(np.sqrt(integral / duration)), float(np.max(np.abs(difference)))


def temperature_domains(observed_k: np.ndarray, predicted_k: np.ndarray) -> dict:
    ranges = {
        "surface_measurement_c": [
            float(observed_k.min() - 273.15),
            float(observed_k.max() - 273.15),
        ],
        "volume_average_prediction_c": [
            float(predicted_k.min() - 273.15),
            float(predicted_k.max() - 273.15),
        ],
    }
    breaches = []
    for property_name, (low, high) in PROPERTY_TEMPERATURE_DOMAINS_C.items():
        for trajectory, (minimum, maximum) in ranges.items():
            if minimum < low or maximum > high:
                breaches.append(
                    {
                        "property": property_name,
                        "trajectory": trajectory,
                        "supported_c": [low, high],
                        "observed_c": [minimum, maximum],
                    }
                )
    return {
        "ranges": ranges,
        "measurement_domains_c": PROPERTY_TEMPERATURE_DOMAINS_C,
        "breaches": breaches,
        "inside_all_listed_measurement_domains": not breaches,
        "note": "measurement domains are not proof of universal model validity",
    }


def thermal_numerics(coarse: SimulationResult, fine: SimulationResult) -> dict:
    check = compare_numerics(coarse, fine)
    stop = min(coarse.time_s[-1], fine.time_s[-1])
    time = np.unique(
        np.r_[coarse.time_s[coarse.time_s <= stop], fine.time_s[fine.time_s <= stop], stop]
    )
    difference = np.interp(time, coarse.time_s, coarse.temperature_k) - np.interp(
        time, fine.time_s, fine.temperature_k
    )
    max_temp = float(np.max(np.abs(difference)))
    return {
        "voltage_max_difference_v": check["voltage_max_difference_v"],
        "capacity_relative_difference": check["capacity_relative_difference"],
        "temperature_max_difference_k": max_temp,
        "coarse_mesh": coarse.config.mesh_points,
        "fine_mesh": fine.config.mesh_points,
        "coarse_tolerance": coarse.config.tolerance,
        "fine_tolerance": fine.config.tolerance,
        "passed": check["passed"] and max_temp <= 0.1,
    }


def audit_refinements(primary: SimulationResult) -> dict:
    """Keep empirical evidence even when a numerical refinement fails."""
    checks = {}
    configurations = {
        "mesh": replace(primary.config, mesh_points=80),
        "solver_tolerance": replace(primary.config, tolerance=1e-8),
    }
    for stage, config in configurations.items():
        try:
            checks[stage] = thermal_numerics(primary, simulate(config))
        except Exception as error:
            checks[stage] = {
                "passed": False,
                "status": "solver_failure",
                "error": f"{type(error).__name__}: {error}",
            }
    return checks


def evaluate_thermal_trace(
    trace: ThermalTrace, model: SimulationResult, residual_path: Path | None = None
) -> dict:
    observed = trace.discharge
    report = compare_trace(observed, model)
    start, stop = report["common_interval_s"]
    time = np.unique(
        np.r_[
            observed.time_s[(observed.time_s >= start) & (observed.time_s <= stop)],
            model.time_s[(model.time_s >= start) & (model.time_s <= stop)],
            start,
            stop,
        ]
    )
    predicted_t = np.interp(time, model.time_s, model.temperature_k)
    measured_t = np.interp(time, observed.time_s, observed.temperature_k)
    predicted_v = np.interp(time, model.time_s, model.voltage_v)
    measured_v = np.interp(time, observed.time_s, observed.voltage_v)
    temp_rmse, temp_max = piecewise_error(time, predicted_t - measured_t)
    energy = float(np.trapezoid(model.config.current_a * model.voltage_v, model.time_s) / 3600)
    energy_relative_error = abs(energy - trace.measured_energy_wh) / trace.measured_energy_wh
    gates = dict(report["gates"])
    gates.update(
        {
            "temperature_rmse": temp_rmse <= 2,
            "temperature_max_error": temp_max <= 5,
            "delivered_energy": energy_relative_error <= 0.05,
        }
    )
    report.update(
        {
            "protocol": "oregan2022-thermal-v1",
            "implementation_split": trace.split,
            "independence": "same-source reproduction; published fitted parameters",
            "parameter_set": "ORegan2022",
            "nominal_temperature_c": trace.nominal_temperature_c,
            "initial_temperature_k": trace.initial_temperature_k,
            "initial_temperature_source": trace.initial_temperature_source,
            "initial_rest_voltage_v": trace.initial_rest_voltage_v,
            "ambient_sensor": trace.ambient_sensor_status,
            "thermal_comparison": {
                "rmse_k": temp_rmse,
                "max_absolute_error_k": temp_max,
                "full_discharge_peak_difference_k": float(
                    model.temperature_k.max() - observed.temperature_k.max()
                ),
                "observable": "lumped volume-average prediction vs surface thermocouple proxy",
                "independent_thermal_validation": False,
            },
            "measured_energy_wh": trace.measured_energy_wh,
            "predicted_delivered_energy_wh": energy,
            "energy_relative_error": energy_relative_error,
            "accumulator_energy_error_wh": abs(
                trace.measured_energy_wh - trace.accumulator_energy_wh
            ),
            "data_quality_flags": trace.quality_flags,
            "duplicate_records_kept_last": trace.duplicate_count,
            "changed_duplicate_records": trace.changed_duplicate_count,
            "original_discharge_rows": trace.original_discharge_rows,
            "normalized_discharge_rows": len(observed.time_s),
            "changed_duplicate_fields": trace.changed_duplicate_fields,
            "duplicate_policy": "keep last, first constant-current DCH block only",
            "temperature_applicability": temperature_domains(
                observed.temperature_k, model.temperature_k
            ),
            "simulation": model.metadata(),
            "gates": gates,
            "empirical_gate_passed": all(gates.values()),
        }
    )
    report.pop("passed")
    if residual_path is not None:
        residual_path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(
            residual_path,
            np.column_stack(
                [
                    time,
                    measured_v,
                    predicted_v,
                    predicted_v - measured_v,
                    measured_t,
                    predicted_t,
                    predicted_t - measured_t,
                ]
            ),
            delimiter=",",
            comments="",
            header="time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v,"
            "surface_temperature_k,volume_average_temperature_k,temperature_error_k",
        )
    return report


def thermal_report_markdown(report: dict) -> str:
    lines = [
        "# Thermal-electrochemical public reconstruction",
        "",
        "Model: PyBaMM26.9.0.0 / ORegan2022 / DFN / lumped / paper h=15 W/m²/K.",
        "No new fitting or voltage/SOC alignment. Published diffusivity corrections retained once.",
        f"Empirical targets: {report['empirical_pass_count']}/{report['case_count']} cases pass.",
        (
            f"Numerical: {report['numerical_pass_count']}/{report['case_count']} cases pass."
            if report["numerical_checks_requested"]
            else "Numerical targets: NOT RUN in this report; no convergence claim."
        ),
        "Independent validation: NOT ESTABLISHED. Temperature is a surface-proxy comparison.",
        "Parameter-temperature extrapolations and raw quality flags remain visible.",
        "",
        "| Cell | Ambient°C | C-rate | V RMSE mV | T RMSE K | Energy err | Empirical | Numerical |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for case in report["cases"]:
        if "error" in case:
            lines.append(
                f"| {case['cell']} | {case['nominal_temperature_c']} | "
                f"{case['c_rate']:g} | failed | failed | failed | FAIL | FAIL |"
            )
        else:
            lines.append(
                f"| {case['cell']} | {case['nominal_temperature_c']} | {case['c_rate']:g} "
                f"| {1000 * case['voltage_rmse_v']:.2f} "
                f"| {case['thermal_comparison']['rmse_k']:.2f} "
                f"| {case['energy_relative_error']:.2%} "
                f"| {'PASS' if case['empirical_gate_passed'] else 'FAIL'} "
                f"| {case['numerical_status'].upper()} |"
            )
    lines += [
        "",
        "## Inspect the evidence",
        "",
        "The JSON includes cutoff/coverage, physical audits, domain breaches, raw quality flags,",
        "initial temperatures, source hashes and mesh/tolerance checks. Each case has model",
        "time-series and common-interval residual CSVs. Failed cases are never removed.",
        "",
        "The 36 files represent12 cells reused across temperatures. Cell791 is retained with",
        "the source's exclusion/sensor-anomaly warning. Cold runs and high-current heating",
        "cross measured property domains. No claim of core-temperature accuracy or safety.",
        "",
        "Chen2020 baseline failures remain independently preserved.",
    ]
    return "\n".join(lines) + "\n"


def run_thermal_benchmark(archive: Path, output: Path, numerical: bool = True) -> dict:
    source_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        source_hash.update(path.name.encode())
        source_hash.update(path.read_bytes())
    traces = load_thermal_cohort(archive)
    output.mkdir(parents=True, exist_ok=True)
    write_evidence_attribution(output, ["tec_validation", "oregan2022_parameters"])
    (output / "data-inspection.json").write_text(
        json.dumps(inspect_cohort(traces), indent=2) + "\n"
    )
    cases = []
    for trace in traces:
        data = trace.discharge
        name = f"cell{data.cell}_{trace.nominal_temperature_c}C_{data.nominal_current_a:g}A"
        print(f"Computing {name}", flush=True)
        try:
            config = ModelConfig(
                parameter_set="ORegan2022",
                thermal="lumped",
                current_a=data.nominal_current_a,
                mesh_points=40,
                ambient_temperature_k=trace.nominal_temperature_c + 273.15,
                initial_temperature_k=trace.initial_temperature_k,
                heat_transfer_coefficient_w_m2_k=15.0,
            )
            result = simulate(config)
            write_timeseries(output / f"{name}-model.csv", result)
            case = evaluate_thermal_trace(trace, result, output / f"{name}-residuals.csv")
            case["numerical_status"] = "pending" if numerical else "not_run"
            case["numerical_gate_passed"] = False
            (output / "partial-cases.json").write_text(
                json.dumps(cases + [case], indent=2, allow_nan=False) + "\n"
            )
            checks = audit_refinements(result) if numerical else {}
            case["numerical_checks"] = checks
            case["numerical_status"] = (
                "passed"
                if checks and all(c["passed"] for c in checks.values())
                else "failed"
                if checks
                else "not_run"
            )
            case["numerical_gate_passed"] = bool(checks) and all(
                c["passed"] for c in checks.values()
            )
        except Exception as error:
            # Preserve the case and exact failure. Never silently drop failed physical conditions.
            case = {
                "cell": data.cell,
                "nominal_temperature_c": trace.nominal_temperature_c,
                "c_rate": data.nominal_current_a / 5,
                "source_sha256": data.source_sha256,
                "error": f"{type(error).__name__}: {error}",
                "empirical_gate_passed": False,
                "numerical_gate_passed": False,
                "numerical_status": "blocked_by_simulation_failure",
            }
        cases.append(case)
        # Persist after every case so a stopped CPU run leaves a usable partial audit.
        (output / "partial-cases.json").write_text(
            json.dumps(cases, indent=2, allow_nan=False) + "\n"
        )
    empirical_count = sum(c["empirical_gate_passed"] for c in cases)
    numeric_count = sum(c["numerical_gate_passed"] for c in cases)
    report = {
        "protocol": "oregan2022-thermal-v1",
        "run_complete": True,
        "protocol_sha256": THERMAL_PROTOCOL_SHA256,
        "implementation_sha256": source_hash.hexdigest(),
        "python_version": platform.python_version(),
        "gates": THERMAL_GATES,
        "case_count": len(cases),
        "unique_cells": 12,
        "empirical_pass_count": empirical_count,
        "numerical_pass_count": numeric_count,
        "numerical_checks_requested": numerical,
        "numerical_status_counts": {
            status: sum(c.get("numerical_status") == status for c in cases)
            for status in ["passed", "failed", "not_run", "blocked_by_simulation_failure"]
        },
        "all_empirical_targets_passed": empirical_count == len(cases),
        "all_numerical_targets_passed": numeric_count == len(cases),
        "independent_validation": False,
        "fitting_performed": False,
        "cases": cases,
    }
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (output / "report.json").write_text(text, encoding="utf-8")
    (output / "report.md").write_text(thermal_report_markdown(report), encoding="utf-8")
    (output / "report.sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "  report.json\n"
    )
    return report
