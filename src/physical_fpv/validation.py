"""Frozen, leakage-aware empirical metrics and numerical convergence checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from physical_fpv.core import ModelConfig, SimulationResult, simulate
from physical_fpv.data import Discharge, load_discharges

PROTOCOL_VERSION = "fixed-chen2020-v1"
PROTOCOL_SHA256 = "7b1e52db49a0affe8883cc439db9eed275dffe233079150ed9899199e7b0750e"
GATES = {
    "voltage_rmse_v": 0.050,
    "voltage_max_abs_error_v": 0.300,
    "capacity_relative_error": 0.05,
    "min_time_coverage": 0.95,
}


def compare_trace(measured: Discharge, model: SimulationResult) -> dict:
    if abs(measured.nominal_current_a - model.config.current_a) > 1e-9:
        raise ValueError("Cannot compare different current protocols")
    # No extrapolation, no best-fit alignment, no endpoint cropping or time rescaling.
    start = max(float(measured.time_s[0]), float(model.time_s[0]))
    stop = min(float(measured.time_s[-1]), float(model.time_s[-1]))
    if stop <= start:
        raise ValueError("No shared time interval")
    inside = measured.time_s[(measured.time_s > start) & (measured.time_s < stop)]
    model_inside = model.time_s[(model.time_s > start) & (model.time_s < stop)]
    common = np.unique(np.concatenate(([start], inside, model_inside, [stop])))
    prediction = np.interp(common, model.time_s, model.voltage_v)
    observation = np.interp(common, measured.time_s, measured.voltage_v)
    error = prediction - observation
    # Exact integral of the squared piecewise-linear difference on the union knots.
    squared_integral = np.sum(
        np.diff(common) * (error[:-1] ** 2 + error[:-1] * error[1:] + error[1:] ** 2) / 3
    )
    rmse = float(np.sqrt(squared_integral / (stop - start)))
    coverage = float((stop - start) / (measured.time_s[-1] - measured.time_s[0]))
    cap_error = abs(float(model.capacity_ah[-1]) - measured.measured_capacity_ah)
    cap_relative = cap_error / measured.measured_capacity_ah
    maximum = float(np.max(np.abs(error)))
    end_event = "Minimum voltage" in model.termination
    gates = {
        "voltage_rmse": rmse <= GATES["voltage_rmse_v"],
        "voltage_max": maximum <= GATES["voltage_max_abs_error_v"],
        "capacity": cap_relative <= GATES["capacity_relative_error"],
        "coverage": coverage >= GATES["min_time_coverage"],
        "voltage_cutoff_reached": end_event,
        "physical_audit": model.physical_audit["passed"],
    }
    thermal_error = None
    if model.config.thermal == "lumped":
        delta = np.interp(common, model.time_s, model.temperature_k) - np.interp(
            common, measured.time_s, measured.temperature_k
        )
        thermal_error = {
            "rmse_k": float(np.sqrt(np.trapezoid(delta**2, common) / (stop - start))),
            "status": "EXPLORATORY: default thermal properties; not validated",
        }
    return {
        "cell": measured.cell,
        "step": measured.step,
        "implementation_split": "development" if measured.cell == "02" else "reserved_check",
        "independence": "same original parameterization study; NOT independent validation",
        "current_a": measured.nominal_current_a,
        "c_rate": measured.nominal_current_a / 5,
        "source_sha256": measured.source_sha256,
        "measured_capacity_ah": measured.measured_capacity_ah,
        "raw_reported_capacity_ah": measured.reported_capacity_ah,
        "raw_capacity_consistency_error_ah": abs(
            measured.reported_capacity_ah - measured.measured_capacity_ah
        ),
        "predicted_capacity_ah": float(model.capacity_ah[-1]),
        "predicted_cutoff_capacity_ah": float(model.capacity_ah[-1]) if end_event else None,
        "termination": model.termination,
        "capacity_relative_error": cap_relative,
        "measured_cutoff_time_s": float(measured.time_s[-1]),
        "predicted_endpoint_time_s": float(model.time_s[-1]),
        "predicted_cutoff_time_s": float(model.time_s[-1]) if end_event else None,
        "voltage_rmse_v": rmse,
        "voltage_max_abs_error_v": maximum,
        "time_coverage": coverage,
        "common_interval_s": [start, stop],
        "measured_temperature_range_k": [
            float(measured.temperature_k.min()),
            float(measured.temperature_k.max()),
        ],
        "measured_chamber_temperature_range_k": [
            float(measured.chamber_temperature_k.min()),
            float(measured.chamber_temperature_k.max()),
        ],
        "thermal_comparison": thermal_error,
        "gates": gates,
        "passed": all(gates.values()),
    }


def compare_numerics(coarse: SimulationResult, fine: SimulationResult) -> dict:
    stop = min(coarse.time_s[-1], fine.time_s[-1])
    time = np.unique(
        np.concatenate(
            (coarse.time_s[coarse.time_s <= stop], fine.time_s[fine.time_s <= stop], [stop])
        )
    )
    error = np.interp(time, coarse.time_s, coarse.voltage_v) - np.interp(
        time, fine.time_s, fine.voltage_v
    )
    voltage = float(np.max(np.abs(error)))
    capacity = float(abs(coarse.capacity_ah[-1] - fine.capacity_ah[-1]) / fine.capacity_ah[-1])
    return {
        "voltage_max_difference_v": voltage,
        "capacity_relative_difference": capacity,
        "coarse": coarse.metadata(),
        "fine": fine.metadata(),
        "passed": bool(
            voltage <= 0.005
            and capacity <= 0.01
            and "Minimum voltage" in coarse.termination
            and "Minimum voltage" in fine.termination
            and coarse.physical_audit["passed"]
            and fine.physical_audit["passed"]
        ),
    }


def write_timeseries(path: Path, result: SimulationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.column_stack(
        (
            result.time_s,
            result.voltage_v,
            result.capacity_ah,
            result.temperature_k,
            result.lithium_mol,
        )
    )
    np.savetxt(
        path,
        values,
        delimiter=",",
        comments="",
        header="time_s,voltage_v,capacity_ah,temperature_k,lithium_inventory_mol",
    )


def run_benchmark(
    data_dir: Path,
    output_dir: Path,
    model_name: str = "DFN",
    thermal: str = "isothermal",
    numerical: bool = True,
    mesh_points: int = 40,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    traces = [
        trace
        for cell in ("02", "03", "04")
        for trace in load_discharges(data_dir / f"LGM50_cell{cell}.csv", cell)
    ]
    results = {}
    for current in (0.5, 2.5, 5.0, 7.5):
        result = simulate(
            ModelConfig(
                model=model_name, thermal=thermal, current_a=current, mesh_points=mesh_points
            )
        )
        results[current] = result
        write_timeseries(output_dir / f"{model_name}_{current:g}A.csv", result)
    comparisons = [compare_trace(trace, results[trace.nominal_current_a]) for trace in traces]
    numerical_checks = []
    if numerical:
        for current, coarse in results.items():
            fine = simulate(replace(coarse.config, mesh_points=mesh_points * 2))
            strict = simulate(replace(coarse.config, tolerance=1e-8))
            numerical_checks.append(
                {
                    "current_a": current,
                    "mesh_refinement": compare_numerics(coarse, fine),
                    "tolerance_refinement": compare_numerics(coarse, strict),
                }
            )
    empirical = all(c["passed"] for c in comparisons)
    numeric_pass = bool(numerical_checks) and all(
        c["mesh_refinement"]["passed"] and c["tolerance_refinement"]["passed"]
        for c in numerical_checks
    )
    source_hash = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        source_hash.update(source.name.encode())
        source_hash.update(source.read_bytes())
    report = {
        "implementation_sha256": source_hash.hexdigest(),
        "schema_version": 1,
        "protocol": PROTOCOL_VERSION,
        "numerical_procedure": "mesh-refinement-addendum-v1",
        "mesh_points": mesh_points,
        "predeclared_protocol_sha256": PROTOCOL_SHA256,
        "gates": GATES,
        "parameter_set": "Chen2020",
        "model": model_name,
        "thermal": thermal,
        "fitting_performed": False,
        "numerical_checks_performed": numerical,
        "claim": "public fixed-parameter benchmark reconstruction only",
        "thermal_validated": False,
        "empirical_gate_passed": empirical,
        "numerical_gate_passed": numeric_pass,
        "research_gate_passed": empirical and numeric_pass and thermal == "isothermal",
        "simulations": [r.metadata() for r in results.values()],
        "comparisons": comparisons,
        "numerical_checks": numerical_checks,
    }
    report_text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (output_dir / "report.json").write_text(report_text, encoding="utf-8")
    (output_dir / "report.sha256").write_text(
        hashlib.sha256(report_text.encode()).hexdigest() + "  report.json\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(render_report(report), encoding="utf-8")
    return report


def render_report(report: dict) -> str:
    lines = [
        "# Battery benchmark report",
        "",
        f"Protocol: {report['protocol']}",
        f"Model: {report['model']} / Chen2020 / {report['thermal']}",
        f"Empirical gate: {'PASS' if report['empirical_gate_passed'] else 'FAIL'}",
        f"Numerical gate: {'PASS' if report['numerical_gate_passed'] else 'FAIL / NOT RUN'}",
        "Thermal validity: NOT ESTABLISHED",
        "",
        "No fitting. These are original-study benchmark data, not independent validation.",
        "Failed thresholds are retained. Isothermal temperature is imposed, not predicted.",
        "",
        "| Cell | C-rate | RMSE (mV) | Max error (mV) | Capacity error | Coverage | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for c in report["comparisons"]:
        lines.append(
            f"| {c['cell']} | {c['c_rate']:g} | {c['voltage_rmse_v'] * 1000:.2f} "
            f"| {c['voltage_max_abs_error_v'] * 1000:.2f} "
            f"| {c['capacity_relative_error']:.2%} | {c['time_coverage']:.2%} "
            f"| {'PASS' if c['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Limits",
        "",
        "- Chen thermal properties contain generic defaults; no validated thermal claim.",
        "- The original study retuned diffusivity by rate; this benchmark does not.",
        "- Not validated for pulses, high-C FPV loads, packs, aging, abuse or safety.",
        "- Full provenance, termination, coverage and physical audits are in report.json.",
        "- Do not interpret a solver or software-test pass as experimental agreement.",
    ]
    return "\n".join(lines) + "\n"
