"""Explore the recorded k1 voltage residual and adjacent rests without solving/fitting.

This is a post-result diagnostic, not a prospectively selected acceptance gate.
The mesh80 curve remains preliminary until the separate spatial check completes.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import openpyxl
import pybamm

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.core import parameter_fingerprint
from physical_fpv.stanford_benchmark import prepare_pilot
from physical_fpv.stanford_data import HEADERS, inspect_records
from physical_fpv.stanford_reference import load_mesh80_reference


def scalar(value):
    return float(value.evaluate() if hasattr(value, "evaluate") else value)


def residual_window(time, error, requested_start, requested_stop):
    start, stop = max(requested_start, time[0]), min(requested_stop, time[-1])
    if stop <= start:
        raise ValueError("Diagnostic window has no observed/model overlap")
    knots = np.unique(np.r_[start, time[(time > start) & (time < stop)], stop])
    values = np.interp(knots, time, error)
    integral = np.sum(
        np.diff(knots) * (values[:-1] ** 2 + values[:-1] * values[1:] + values[1:] ** 2) / 3
    )
    return {
        "requested_interval_s": [float(requested_start), float(requested_stop)],
        "available_interval_s": [float(start), float(stop)],
        "coverage": float((stop - start) / (requested_stop - requested_start)),
        "voltage_rmse_v": float(np.sqrt(integral / (stop - start))),
        "signed_time_mean_error_v": float(np.trapezoid(values, knots) / (stop - start)),
        "minimum_error_v": float(values.min()),
        "maximum_error_v": float(values.max()),
        "squared_error_integral_v2_s": float(integral),
    }


def point(row, excel_row):
    return {
        "excel_row": excel_row,
        "source_test_time_s": float(row[1]),
        "source_step_time_s": float(row[2]),
        "voltage_v": float(row[4]),
        "current_a": float(row[5]),
        "skin_temperature_c": float(row[6]),
    }


def rest_summary(indexed_rows):
    values = np.array([r[1][1:] for r in indexed_rows], dtype=float)
    time, voltage, current = values[:, 1], values[:, 3], values[:, 4]
    if np.any(np.diff(time) <= 0):
        raise ValueError("Rest diagnostic requires unique increasing original times")
    start = max(time[0], time[-1] - 600)
    voltage_start = np.interp(start, time, voltage)
    return {
        "first": point(indexed_rows[0][1], indexed_rows[0][0]),
        "last": point(indexed_rows[-1][1], indexed_rows[-1][0]),
        "record_count": len(indexed_rows),
        "maximum_absolute_recorded_current_a": float(np.max(np.abs(current))),
        "signed_observed_charge_ah": float(np.trapezoid(current, time) / 3600),
        "last_600s_voltage_change_v": float(voltage[-1] - voltage_start),
        "equilibrium_established": False,
    }


def uniform_state(parameters, charge_ah, temperature_k):
    expressions = pybamm.LithiumIonParameters()
    area = parameters["Electrode height [m]"] * parameters["Electrode width [m]"]
    parallel = parameters["Number of electrodes connected in parallel to make a cell"]
    if parallel != 1 or parameters["Number of cells connected in series to make a battery"] != 1:
        raise ValueError("This diagnostic is for the single-cell published parameter set")
    electrodes = {}
    for name, sign, expression in (
        ("negative", -1, expressions.n.prim),
        ("positive", 1, expressions.p.prim),
    ):
        title = name.title()
        volume = (
            parallel
            * area
            * parameters[f"{title} electrode thickness [m]"]
            * parameters[f"{title} electrode active material volume fraction"]
        )
        c0 = parameters[f"Initial concentration in {name} electrode [mol.m-3]"]
        concentration = c0 + sign * charge_ah * 3600 / (scalar(pybamm.constants.F) * volume)
        sto = concentration / parameters[f"Maximum concentration in {name} electrode [mol.m-3]"]
        if not 0 < sto < 1:
            raise ValueError("Conditional charge transfer leaves the electrode domain")
        potential = scalar(
            parameters.process_symbol(
                expression.U(pybamm.Scalar(sto), pybamm.Scalar(temperature_k))
            )
        )
        electrodes[name] = {
            "active_volume_m3": volume,
            "mean_concentration_mol_m3": concentration,
            "mean_stoichiometry": sto,
            "solid_lithium_mol": volume * concentration,
            "uniform_ocp_v": potential,
        }
    return {
        "discharged_charge_ah": charge_ah,
        "temperature_k": temperature_k,
        "electrodes": electrodes,
        "uniform_ocv_v": electrodes["positive"]["uniform_ocp_v"]
        - electrodes["negative"]["uniform_ocp_v"],
        "solid_lithium_mol": sum(e["solid_lithium_mol"] for e in electrodes.values()),
    }


def diagnose(root):
    manifest = json.loads((root / "data/stanford-manifest.json").read_text())
    observed, profile, config, assumptions = prepare_pilot(root / "data/stanford/raw", manifest)
    parameters = pybamm.ParameterValues("ORegan2022")
    parameters.update(
        {
            "Current function [A]": config.current_a,
            "Ambient temperature [K]": config.ambient_temperature_k,
            "Initial temperature [K]": config.initial_temperature_k,
            "Total heat transfer coefficient [W.m-2.K-1]": config.heat_transfer_coefficient_w_m2_k,
        }
    )
    fingerprint = hashlib.sha256(
        (
            parameter_fingerprint(parameters)
            + ":piecewise-linear-current:"
            + profile.fingerprint_sha256
        ).encode()
    ).hexdigest()
    recorded = load_mesh80_reference(root, config, profile, fingerprint)
    path = root / "data/stanford/raw" / assumptions["source"]["filename"]
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        stream = book.worksheets[0].iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Source schema changed")
        rows = list(stream)
    finally:
        book.close()
    inspected, _ = inspect_records(rows)
    if not inspected["canonical_six_step_sequence"]:
        raise ValueError("Expected exactly the six original contiguous protocol phases")
    blocks = {n: [(i, r) for i, r in enumerate(rows, 2) if r[3] == n] for n in (4, 5, 6)}
    pre, post = rest_summary(blocks[4]), rest_summary(blocks[6])
    first, last = point(blocks[5][0][1], blocks[5][0][0]), point(blocks[5][-1][1], blocks[5][-1][0])
    start, measured_stop = observed[[0, -1], 0]
    stop = min(measured_stop, recorded.time_s[-1])
    time = np.unique(
        np.r_[
            start,
            observed[(observed[:, 0] > start) & (observed[:, 0] < stop), 0],
            recorded.time_s[(recorded.time_s > start) & (recorded.time_s < stop)],
            stop,
        ]
    )
    error = np.interp(time, recorded.time_s, recorded.voltage_v) - np.interp(
        time, observed[:, 0], observed[:, 2]
    )
    overall = residual_window(time, error, start, measured_stop)
    if abs(overall["voltage_rmse_v"] - recorded.empirical_report["voltage_rmse_v"]) > 1e-12:
        raise ValueError("Independent residual reconstruction differs from saved evidence")
    edges = np.linspace(start, measured_stop, 4)
    measured_charge = float(np.trapezoid(-observed[:, 1], observed[:, 0]) / 3600)
    initial_charge = profile.charge_integral_ah(start)
    initial = uniform_state(parameters, 0.0, config.initial_temperature_k)
    end = uniform_state(
        parameters, measured_charge + initial_charge, post["last"]["skin_temperature_c"] + 273.15
    )
    if abs(initial["solid_lithium_mol"] - end["solid_lithium_mol"]) > 1e-12:
        raise ValueError("Conditional charge transfer failed solid lithium conservation")
    first_predicted_voltage = float(np.interp(start, recorded.time_s, recorded.voltage_v))
    return {
        "scope": (
            "Exploratory analysis after the mesh80 result; "
            "no new acceptance gates, model solves or fitting"
        ),
        "source": assumptions["source"],
        "recorded_reference": recorded.metadata()["recorded_reference"],
        "software": {
            "pybamm_version": pybamm.__version__,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "parameter_function_file_sha256": hashlib.sha256(
                Path(inspect.getsourcefile(parameters["Negative electrode OCP [V]"])).read_bytes()
            ).hexdigest(),
        },
        "pre_discharge_rest": pre,
        "post_discharge_rest": post,
        "loaded_first": first,
        "loaded_last": last,
        "first_load_transition": {
            "source_sample_gap_s": first["source_test_time_s"] - pre["last"]["source_test_time_s"],
            "observed_voltage_drop_v": pre["last"]["voltage_v"] - first["voltage_v"],
            "apparent_step_ratio_ohm": (pre["last"]["voltage_v"] - first["voltage_v"])
            / abs(first["current_a"] - pre["last"]["current_a"]),
            "predicted_loaded_voltage_at_first_observed_time_v": first_predicted_voltage,
            "predicted_average_temperature_at_first_observed_time_k": float(
                np.interp(start, recorded.time_s, recorded.temperature_k)
            ),
            "model_uniform_initial_ocv_minus_first_loaded_voltage_v": (
                initial["uniform_ocv_v"] - first_predicted_voltage
            ),
            "warning": (
                "Includes unresolved sub-second response, polarization, finite rest and sensing; "
                "not isolated ohmic/contact resistance"
            ),
        },
        "initial_uniform_state": initial,
        "initial_uniform_ocv_minus_measured_rest_v": initial["uniform_ocv_v"]
        - pre["last"]["voltage_v"],
        "conditional_post_discharge_uniform_state": end,
        "conditional_uniform_ocv_minus_one_hour_rest_v": end["uniform_ocv_v"]
        - post["last"]["voltage_v"],
        "observed_discharge_charge_ah": measured_charge,
        "assumed_initial_gap_charge_ah": initial_charge,
        "conditional_state_warning": (
            "Uses published active volumes, initial concentrations, charge conservation and "
            "OCP/entropy expressions. Assumes unmeasured initial current and complete uniform "
            "redistribution; not an actual relaxation simulation or measured cell SOC. "
            "Finite rest and unknown parasitic/history effects remain."
        ),
        "residuals": {
            "error_sign": "prediction minus measurement",
            "overall": overall,
            "first_60s": residual_window(time, error, start, 60.0),
            "observed_duration_thirds": [
                residual_window(time, error, lo, hi)
                for lo, hi in zip(edges[:-1], edges[1:], strict=True)
            ],
        },
        "original_electrical_gates_passed": recorded.empirical_report["electrical_gates_passed"],
        "fitting_performed": False,
        "new_model_solves": 0,
        "unique_physical_cause_established": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-residual-diagnostic"))
    args = parser.parse_args()
    report = diagnose(Path.cwd())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    write_evidence_attribution(args.out, ["stanford2021", "oregan2022_parameters"])
    print(
        json.dumps(
            {
                "voltage_rmse_v": report["residuals"]["overall"]["voltage_rmse_v"],
                "initial_rest_difference_v": report["initial_uniform_ocv_minus_measured_rest_v"],
                "new_model_solves": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
