#!/usr/bin/env python3
"""Read existing evidence; evaluate parameter functions, never solve a battery model.

Run from the project root:
    python scripts/diagnose_rest_state.py --out results/rest-state
No simulation or fit is performed; all original scientific gates are unchanged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import io
import itertools
import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("PYBAMM_DISABLE_TELEMETRY", "true")
import numpy as np
import pybamm

from physical_fpv.attribution import write_evidence_attribution

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=Path("results/rest-state"))
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
OUT = args.out / "review.json"
ARCHIVE = ROOT / "data/oregan/raw/validation.zip"
BASE = ROOT / "docs/benchmarks"
EXPECTED = {
    "data/oregan/raw/validation.zip": (
        "3848d0eb1d70e4fc86cc77c272433053760b0bdfe25825ef652135edc43275b8"
    ),
    "docs/benchmarks/cell790-grid120-diagnosis.json": (
        "05f528e8b7d5bf4a50b1e8547d52dd426b3737d25e0cb812d2a03143b4232ba0"
    ),
    "docs/benchmarks/thermal-grid120-reference.csv": (
        "61585bc925a0328513f7f6a905d55a926eed762530f5e9faae2e005d8a492846"
    ),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scalar(x):
    return float(x.evaluate() if hasattr(x, "evaluate") else x)


def source_info(func):
    lines, start = inspect.getsourcelines(func)
    path = Path(inspect.getsourcefile(func)).resolve()
    return {
        "name": func.__name__,
        "package_file": "pybamm/" + str(path).rsplit("/pybamm/", 1)[1],
        "file_sha256": sha(path.read_bytes()),
        "lines_1_based_inclusive": [start, start + len(lines) - 1],
        "function_sha256": sha("".join(lines).encode()),
    }


def unique_last(rows):
    kept = []
    for row in rows:
        t = float(row["Step Time"])
        if kept and t == float(kept[-1]["Step Time"]):
            kept[-1] = row
        else:
            kept.append(row)
    assert np.all(np.diff([float(r["Step Time"]) for r in kept]) > 0)
    return kept


def arr(rows, key):
    return np.array([float(row[key]) for row in rows])


def row_values(row):
    out = {
        key: float(row[key])
        for key in (
            "Step Time",
            "Prog Time",
            "Voltage",
            "Current",
            "AhAccu",
            "WhAccu",
            "LogTemp001",
        )
    }
    out.update({key: row[key] for key in ("Step", "Status", "_line", "_measurement_row")})
    return out


def block_info(rows):
    return {
        "status": rows[0]["Status"],
        "step": int(rows[0]["Step"]),
        "csv_lines_1_based_inclusive": [rows[0]["_line"], rows[-1]["_line"]],
        "measurement_rows_1_based_inclusive": [
            rows[0]["_measurement_row"],
            rows[-1]["_measurement_row"],
        ],
        "raw_row_count": len(rows),
        "first": row_values(rows[0]),
        "last": row_values(rows[-1]),
    }


def rest_info(rows):
    info = block_info(rows)
    clean = unique_last(rows)
    t, v, temp, current = [arr(clean, k) for k in ("Step Time", "Voltage", "LogTemp001", "Current")]
    windows = []
    for start in (3600.0, 5400.0, 6600.0):
        i = int(np.flatnonzero(t >= start)[0])
        windows.append(
            {
                "requested_start_s": start,
                "actual_start_s": float(t[i]),
                "end_s": float(t[-1]),
                "start_csv_line": clean[i]["_line"],
                "end_csv_line": clean[-1]["_line"],
                "voltage_start_v": float(v[i]),
                "voltage_end_v": float(v[-1]),
                "voltage_change_v": float(v[-1] - v[i]),
                "voltage_change_mv_per_min": float((v[-1] - v[i]) * 1000 * 60 / (t[-1] - t[i])),
                "temperature_start_c": float(temp[i]),
                "temperature_end_c": float(temp[-1]),
                "voltage_range_v": [float(v[i:].min()), float(v[i:].max())],
            }
        )
    info.update(
        {
            "current_min_a": float(current.min()),
            "current_max_a": float(current.max()),
            "maximum_absolute_recorded_current_a": float(np.abs(current).max()),
            "signed_integrated_current_ah": float(np.trapezoid(current, t) / 3600),
            "AhAccu_range_ah": [
                float(arr(clean, "AhAccu").min()),
                float(arr(clean, "AhAccu").max()),
            ],
            "last_windows": windows,
            "equilibrium_established": False,
            "note": (
                "Recorded zero current is not proof of zero parasitic current. Finite "
                "rest and voltage drift do not prove equilibrium."
            ),
        }
    )
    return info


checks = {}
sources = {}
for rel, expected in EXPECTED.items():
    actual = sha((ROOT / rel).read_bytes())
    assert actual == expected, f"Source changed: {rel}"
    sources[rel] = {"sha256": actual, "matches_pinned_input": True}

diagnosis = json.loads((BASE / "cell790-grid120-diagnosis.json").read_text())
series = np.genfromtxt(BASE / "thermal-grid120-reference.csv", delimiter=",", names=True)

with zipfile.ZipFile(ARCHIVE) as archive:
    member = next(n for n in archive.namelist() if n.endswith("/data/25degC/Cell790_1C_25degC.csv"))
    raw = archive.read(member)
    assert sha(raw) == diagnosis["source_sha256"]
    sources[member] = {"archive": str(ARCHIVE.relative_to(ROOT)), "sha256": sha(raw)}
    lines = raw.decode("utf-8-sig").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("Step,Status,Step Time,"))
    reader = csv.DictReader(io.StringIO("\n".join(lines[header:])))
    next(reader)  # Units, not a measurement.
    rows = []
    for index, row in enumerate(reader, start=1):
        row["_line"] = header + reader.line_num
        row["_measurement_row"] = index
        rows.append(row)
    sources[member].update({"header_csv_line": header + 1, "units_csv_line": header + 2})
    blocks = [list(g) for _, g in itertools.groupby(rows, key=lambda r: (r["Step"], r["Status"]))]
    discharge_index = next(i for i, b in enumerate(blocks) if b[0]["Status"] == "DCH")
    dch_raw = blocks[discharge_index]
    previous_range = blocks[discharge_index - 1]
    pre_rest = blocks[discharge_index - 2]
    post_rest = blocks[discharge_index + 1]
    assert (pre_rest[0]["Status"], previous_range[0]["Status"], post_rest[0]["Status"]) == (
        "PAU",
        "RANGE",
        "PAU",
    )
    loader_name = next(
        n
        for n in archive.namelist()
        if n.endswith("tec_reduced_model/process_experimental_data.py")
    )
    loader_bytes = archive.read(loader_name)
    loader_lines = loader_bytes.decode().splitlines()
    loader_start = next(
        i for i, line in enumerate(loader_lines) if line.startswith("def get_idxs(")
    )
    sources[loader_name] = {
        "archive": str(ARCHIVE.relative_to(ROOT)),
        "sha256": sha(loader_bytes),
        "inspected_not_executed": True,
        "get_idxs_lines_1_based_inclusive": [loader_start + 1, len(loader_lines)],
    }

dch = unique_last(dch_raw)
td, vd, tempd, current = [arr(dch, k) for k in ("Step Time", "Voltage", "LogTemp001", "Current")]
tempd = tempd + 273.15
# Independently reproduce the inspected loader's index arithmetic, without
# importing or executing anything from the downloaded archive.
raw_current_changes = np.diff(arr(rows, "Current"))
source_start_index = int(
    np.flatnonzero((raw_current_changes < -4.75) & (raw_current_changes > -5.25))[0]
)
assert rows[source_start_index]["_line"] == previous_range[-1]["_line"]
checks["source_loader_transition_index_matches_last_range_row"] = True
qd = float(np.trapezoid(-current, td) / 3600)
assert abs(qd - diagnosis["measured_capacity_ah"]) < 1e-12
tm = series["time_s"]
stop, measured_stop = float(tm[-1]), float(td[-1])
union = np.unique(np.r_[0, td[(td > 0) & (td < stop)], tm[(tm > 0) & (tm < stop)], stop])
resid = {
    "voltage_error_v": np.interp(union, tm, series["voltage_v"]) - np.interp(union, td, vd),
    "temperature_error_k": np.interp(union, tm, series["temperature_k"])
    - np.interp(union, td, tempd),
}
checks["residuals_derived_from_raw_and_checksum_pinned_model_csv"] = True


def phase(lo, hi):
    end = min(hi, stop)
    knots = np.unique(np.r_[lo, union[(union > lo) & (union < end)], end])
    dt = np.diff(knots)
    out = {
        "requested_interval_s": [lo, hi],
        "available_interval_s": [lo, end],
        "coverage_of_requested_phase": (end - lo) / (hi - lo),
    }
    for field in ("voltage_error_v", "temperature_error_k"):
        e = np.interp(knots, union, resid[field])
        integral = float(np.sum(dt * (e[:-1] ** 2 + e[:-1] * e[1:] + e[1:] ** 2) / 3))
        out[field] = {
            "rmse": float(np.sqrt(integral / (end - lo))),
            "signed_time_mean": float(np.trapezoid(e, knots) / (end - lo)),
            "minimum": float(e.min()),
            "maximum": float(e.max()),
            "start": float(e[0]),
            "end": float(e[-1]),
            "squared_error_integral": integral,
        }
    return out


total = phase(0.0, measured_stop)
thirds = [phase(i * measured_stop / 3, (i + 1) * measured_stop / 3) for i in range(3)]
assert abs(total["voltage_error_v"]["rmse"] - diagnosis["voltage_rmse_v"]) < 1e-12
assert abs(total["temperature_error_k"]["rmse"] - diagnosis["thermal_comparison"]["rmse_k"]) < 1e-12
checks["exact_piecewise_linear_metrics_match_existing_diagnosis"] = True

p = pybamm.ParameterValues("ORegan2022")
assert pybamm.__version__ == diagnosis["simulation"]["pybamm_version"]
oregan_path = Path(inspect.getsourcefile(p["Negative electrode OCP [V]"]))
assert (
    sha(oregan_path.read_bytes())
    == "c0c8111cb37fd4e79726f17e0d02f0aaac6d06532060a677efb5743c92a0b259"
)
config = diagnosis["simulation"]["config"]
p.update(
    {
        "Current function [A]": config["current_a"],
        "Ambient temperature [K]": config["ambient_temperature_k"],
        "Initial temperature [K]": config["initial_temperature_k"],
        "Total heat transfer coefficient [W.m-2.K-1]": config["heat_transfer_coefficient_w_m2_k"],
    }
)
values = {key: inspect.getsource(value) if callable(value) else value for key, value in p.items()}
fingerprint = sha(json.dumps(values, sort_keys=True).encode())
assert fingerprint == diagnosis["simulation"]["parameter_fingerprint"]
checks["reconstructed_parameter_fingerprint_matches_frozen_simulation"] = True
parameters = {k: v for k, v in values.items() if not isinstance(v, str)}
functions = {
    key: source_info(p[key])
    for key in (
        "Negative electrode OCP [V]",
        "Positive electrode OCP [V]",
        "Negative electrode OCP entropic change [V.K-1]",
        "Positive electrode OCP entropic change [V.K-1]",
    )
}
F = scalar(pybamm.constants.F)
area = p["Electrode height [m]"] * p["Electrode width [m]"]
parallel = p["Number of electrodes connected in parallel to make a cell"]
assert parallel == 1 and p["Number of cells connected in series to make a battery"] == 1
li_parameters = pybamm.LithiumIonParameters()  # Parameter expressions only; no model or solver.
functions["PyBaMM temperature/asymptote application"] = source_info(type(li_parameters.n.prim).U)


def conserved_state(q, T):
    out = {"discharged_charge_ah": q, "temperature_k": T, "electrodes": {}}
    for e, sign in (("negative", -1), ("positive", 1)):
        E = e.title()
        volume = (
            parallel
            * area
            * p[f"{E} electrode thickness [m]"]
            * p[f"{E} electrode active material volume fraction"]
        )
        k = F * volume / 3600
        c0, cmax = (
            p[f"Initial concentration in {e} electrode [mol.m-3]"],
            p[f"Maximum concentration in {e} electrode [mol.m-3]"],
        )
        mean_c = c0 + sign * q / k
        theta = mean_c / cmax
        assert 0 < theta < 1
        uref = scalar(p[f"{E} electrode OCP [V]"](theta))
        dudt = scalar(p[f"{E} electrode OCP entropic change [V.K-1]"](theta))
        raw_u = uref + (T - p["Reference temperature [K]"]) * dudt
        phase_param = li_parameters.n.prim if e == "negative" else li_parameters.p.prim
        model_u = scalar(p.process_symbol(phase_param.U(pybamm.Scalar(theta), pybamm.Scalar(T))))
        out["electrodes"][e] = {
            "active_volume_m3": volume,
            "initial_concentration_mol_m3": c0,
            "maximum_concentration_mol_m3": cmax,
            "initial_stoichiometry": c0 / cmax,
            "ah_per_mol_m3": k,
            "full_stoichiometric_span_ah": k * cmax,
            "initial_charge_to_stoichiometric_limit_ah": k * (c0 if sign < 0 else cmax - c0),
            "inferred_mean_concentration_mol_m3": mean_c,
            "inferred_mean_stoichiometry": theta,
            "inferred_solid_lithium_mol": mean_c * volume,
            "reference_ocp_v": uref,
            "entropic_coefficient_v_k": dudt,
            "temperature_corrected_ocp_v": raw_u,
            "pybamm_parameter_expression_ocp_v": model_u,
            "pybamm_clipping_and_asymptote_correction_v": model_u - raw_u,
        }
    n, pp = out["electrodes"]["negative"], out["electrodes"]["positive"]
    out["uniform_state_reference_ocv_v"] = pp["reference_ocp_v"] - n["reference_ocp_v"]
    out["uniform_state_entropic_coefficient_v_k"] = (
        pp["entropic_coefficient_v_k"] - n["entropic_coefficient_v_k"]
    )
    out["uniform_state_temperature_corrected_ocv_v"] = (
        pp["temperature_corrected_ocp_v"] - n["temperature_corrected_ocp_v"]
    )
    out["uniform_state_pybamm_expression_ocv_v"] = (
        pp["pybamm_parameter_expression_ocp_v"] - n["pybamm_parameter_expression_ocp_v"]
    )
    out["total_solid_lithium_mol"] = (
        n["inferred_solid_lithium_mol"] + pp["inferred_solid_lithium_mol"]
    )
    return out


initial = conserved_state(0.0, float(previous_range[-1]["LogTemp001"]) + 273.15)
model_end = conserved_state(float(series["capacity_ah"][-1]), float(series["temperature_k"][-1]))
measured_end = conserved_state(qd, float(post_rest[-1]["LogTemp001"]) + 273.15)
initial["recorded_pre_discharge_rest_voltage_v"] = float(previous_range[-1]["Voltage"])
initial["uniform_state_minus_recorded_rest_v"] = (
    initial["uniform_state_pybamm_expression_ocv_v"]
    - initial["recorded_pre_discharge_rest_voltage_v"]
)
model_end["existing_model_terminal_voltage_v"] = float(series["voltage_v"][-1])
model_end["uniform_state_minus_terminal_voltage_v"] = (
    model_end["uniform_state_pybamm_expression_ocv_v"]
    - model_end["existing_model_terminal_voltage_v"]
)
measured_end["recorded_two_hour_rest_voltage_v"] = float(post_rest[-1]["Voltage"])
measured_end["uniform_state_minus_two_hour_rest_v"] = (
    measured_end["uniform_state_pybamm_expression_ocv_v"]
    - measured_end["recorded_two_hour_rest_voltage_v"]
)
electrolyte_li = (
    parallel
    * area
    * p["Initial concentration in electrolyte [mol.m-3]"]
    * sum(
        p[f"{region} thickness [m]"] * p[f"{region} porosity"]
        for region in ("Negative electrode", "Separator", "Positive electrode")
    )
)
initial_li = initial["total_solid_lithium_mol"] + electrolyte_li
inventory_series = series["lithium_inventory_mol"]
assert abs(initial_li - inventory_series[0]) < 1e-12
assert (
    max(
        abs(s["total_solid_lithium_mol"] - initial["total_solid_lithium_mol"])
        for s in (model_end, measured_end)
    )
    < 1e-12
)
expected_q = diagnosis["current_a"] * stop / 3600
assert abs(model_end["discharged_charge_ah"] - expected_q) < 1e-10
checks["inferred_initial_inventory_matches_saved_total_lithium"] = True
checks["two_electrode_inferred_charge_transfer_conserves_solid_lithium"] = True
checks["saved_model_cutoff_capacity_matches_current_times_time"] = True

report = {
    "schema_version": 1,
    "scope": (
        "Exploratory no-solve, no-fit audit of existing cell790 1C/25C grid120 "
        "evidence; not a new scientific gate."
    ),
    "software": {
        "pybamm_version": pybamm.__version__,
        "numpy_version": np.__version__,
        "script_sha256": sha(Path(__file__).read_bytes()),
        "frozen_parameter_fingerprint_reproduced": fingerprint,
    },
    "sources": sources,
    "consistency_checks": checks,
    "formulas": {
        "error_sign": "prediction minus measurement",
        "squared_error_integral": (
            "sum(dt * (e_left^2 + e_left*e_right + e_right^2) / 3) on union knots, "
            "including interpolated phase boundaries"
        ),
        "rmse": "sqrt(squared_error_integral / available_phase_duration)",
        "bias": "trapezoidal_integral(e) / available_phase_duration (exact for piecewise-linear e)",
        "measured_charge_ah": (
            "integral(-recorded_current_a, discharge_step_time_s) / 3600, "
            "retaining last duplicate timestamp"
        ),
        "negative_mean_concentration": "c_n0 - Q_Ah*3600/(F*N_parallel*A*L_n*epsilon_s_n)",
        "positive_mean_concentration": "c_p0 + Q_Ah*3600/(F*N_parallel*A*L_p*epsilon_s_p)",
        "stoichiometry": (
            "inferred_mean_concentration/cmax; electrode stoichiometry, NOT measured cell SOC"
        ),
        "uniform_state_ocv": (
            "U_p(theta_p,T_ref)-U_n(theta_n,T_ref)+(T-T_ref)*(dU_p/dT-dU_n/dT); "
            "separately checked through installed PyBaMM U expression including "
            "clipping/asymptotes"
        ),
        "initial_total_lithium": (
            "sum(active_volume*c_initial) + "
            "N_parallel*A*c_e0*sum(region_thickness*electrolyte_porosity)"
        ),
        "F_c_mol": F,
        "electrode_area_m2": area,
        "reference_temperature_k": p["Reference temperature [K]"],
    },
    "protocol_audit": {
        "first_discharge": block_info(dch_raw),
        "last_preceding_zero_current_range": block_info(previous_range),
        "predischarge_rest": rest_info(pre_rest),
        "first_postdischarge_rest": rest_info(post_rest),
        "normalized_first_discharge_rows": len(dch),
        "duplicate_rows_kept_last": len(dch_raw) - len(dch),
        "step_time_minus_elapsed_prog_time_max_abs_s": float(
            np.abs(td - (arr(dch, "Prog Time") - float(dch[0]["Prog Time"]))).max()
        ),
        "source_loader_start_row": row_values(previous_range[-1]),
        "source_loader_start_to_first_discharge_s": float(dch[0]["Prog Time"])
        - float(previous_range[-1]["Prog Time"]),
        "raw_discharge_current_min_max_a": [float(current.min()), float(current.max())],
        "measured_integrated_charge_ah": qd,
        "warning": (
            "Repeated cycles reuse step numbers. Select the first contiguous DCH "
            "and its adjacent rest blocks; never combine all rows with the same "
            "Step."
        ),
    },
    "residual_diagnostics": {
        "phase_choice": (
            "Exploratory thirds of full measured duration; no boundary chosen to "
            "minimize residuals. Missing tail retained as missing."
        ),
        "overall": total,
        "thirds": thirds,
        "first_60_seconds": phase(0.0, 60.0),
        "final_measured_decile": phase(0.9 * measured_stop, measured_stop),
        "tail_fraction_of_observed_voltage_squared_error": thirds[2]["voltage_error_v"][
            "squared_error_integral"
        ]
        / total["voltage_error_v"]["squared_error_integral"],
        "model_cutoff_s": stop,
        "measured_endpoint_s": measured_stop,
        "model_cutoff_minus_measured_endpoint_s": stop - measured_stop,
        "full_measured_time_coverage": diagnosis["time_coverage"],
        "capacity_relative_error_unchanged": diagnosis["capacity_relative_error"],
        "energy_relative_error_unchanged": diagnosis["energy_relative_error"],
        "scientific_gates_unchanged": diagnosis["gates"],
    },
    "parameter_values_scalar": parameters,
    "parameter_functions_and_exact_sources": functions,
    "conservation_diagnostics": {
        "initial": initial,
        "at_saved_model_cutoff": model_end,
        "at_measured_charge_with_frozen_inventory": measured_end,
        "initial_electrolyte_lithium_mol": electrolyte_li,
        "calculated_initial_total_lithium_mol": initial_li,
        "saved_initial_total_lithium_mol": float(inventory_series[0]),
        "saved_final_total_lithium_mol": float(inventory_series[-1]),
        "saved_max_relative_total_lithium_drift": float(
            np.max(np.abs(inventory_series - inventory_series[0])) / inventory_series[0]
        ),
        "model_cutoff_current_integral_ah": expected_q,
        "model_cutoff_capacity_minus_current_integral_ah": model_end["discharged_charge_ah"]
        - expected_q,
    },
    "limits_and_interpretation": [
        (
            "No model solve, optimization, parameter update of the frozen run, or "
            "author-archive code execution was performed."
        ),
        (
            "In-memory ParameterValues only reproduce existing experiment settings "
            "and evaluate published functions. No parameters are fitted or written "
            "back."
        ),
        (
            "Endpoint electrode means are inferred from charge conservation under "
            "the frozen single-phase DFN assumptions: uniform initial "
            "concentrations, fixed active volumes, one-electron transfer and no "
            "side-reaction/storage sink. The CSV exports total lithium and "
            "capacity, not endpoint spatial electrode concentration arrays; direct "
            "endpoint means cannot be verified from these exports."
        ),
        (
            "The stoichiometries at measured Q are a hypothetical state under "
            "frozen model inventory, not an observation of actual cell state of "
            "charge. Actual physical endpoint SOC cannot be inferred uniquely here."
        ),
        (
            "The uniform-state OCV calculation assumes homogeneous relaxed "
            "electrodes and the fitted OCP/entropic laws. It is not a simulation "
            "of the two-hour relaxation."
        ),
        (
            "Post-discharge voltage is still rising at two hours; equilibrium has "
            "not been established. Hysteresis, residual gradients, parameter "
            "applicability, active-capacity and initial-inventory discrepancies "
            "remain possible. The approximately -313 mV mismatch prioritizes an "
            "audit; it does not identify a unique cause or authorize fitting."
        ),
        (
            "OCV agreement at the start does not establish both initial "
            "stoichiometries or lithium inventory. The late voltage residual "
            "cannot be removed by one constant voltage offset."
        ),
        (
            "Measured-temperature forcing would test conditional "
            "temperature-trajectory sensitivity, jointly bypassing heat "
            "generation, heat capacity and cooling, with a surface-versus-volume "
            "proxy assumption. It does not isolate a thermal boundary error, and "
            "cannot count as forward temperature validation."
        ),
        (
            "Residual partitions and relaxation checks are exploratory diagnostics "
            "outside the frozen discharge scientific gate. No extrapolation, "
            "missing-tail score imputation, capacity/time stretching, threshold "
            "changes, exclusions or full-cohort reruns are made."
        ),
    ],
}

write_evidence_attribution(args.out, ["tec_validation", "oregan2022_parameters"])
OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
print(
    json.dumps(
        {
            "output": str(OUT),
            "all_consistency_checks": all(checks.values()),
            "checks": len(checks),
            "post_rest_ocv_residual_v": measured_end["uniform_state_minus_two_hour_rest_v"],
            "model_cutoff_mean_stoichiometries": {
                e: model_end["electrodes"][e]["inferred_mean_stoichiometry"]
                for e in ("negative", "positive")
            },
        },
        indent=2,
    )
)
