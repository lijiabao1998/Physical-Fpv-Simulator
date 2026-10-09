"""Run the frozen cached-data cooling screen; no DFN solve or download."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
from pathlib import Path

import numpy as np
import pybamm

from physical_fpv.cooling_characterization import fit_decay, metrics, prediction, window

SOURCE_HASH = "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
WORKBOOK_HASH = "20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086"
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rests(path):
    if digest(path) != SOURCE_HASH:
        raise ValueError("Archived source hash mismatch")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
    result = {}
    for step in (4, 6):
        selected = [r for r in rows if float(r["Step_Index"]) == step]
        if not selected or any(float(r["Current(A)"]) != 0 for r in selected):
            raise ValueError("Required rest must contain only recorded zero current")
        result[step] = (
            np.array([float(r["Step_Time(s)"]) for r in selected]),
            np.array([float(r["Surface_Temp(degC)"]) for r in selected]),
        )
    return result


def run(source, out):
    started = time.monotonic()
    rests = load_rests(source)
    t, y = rests[6]
    pre_t, pre_y = rests[4]
    bt, by = window(pre_t, pre_y, pre_t[-1] - 600, pre_t[-1])
    pre_baseline = float(np.trapezoid(by, bt) / 600)
    p = pybamm.ParameterValues("ORegan2022")
    heat_capacity = float(
        p.evaluate(pybamm.ThermalParameters().rho_c_p_eff(pybamm.Scalar(298.15)))
        * p["Cell volume [m3]"]
    )
    area = float(p["Cell cooling surface area [m2]"])
    prior_rate = 15 * area / heat_capacity
    cases = {}
    max_quadrature_difference = 0.0
    for name, baseline in [("nominal_25c", 25.0), ("preceding_rest_skin_proxy", pre_baseline)]:
        fit = fit_decay(t, y, baseline)
        anchor = fit["anchor_temperature_c"]
        checks = {}
        calibration_end = fit["calibration"]["interval_s"][1]
        check_start = float(t[t >= 600][0])
        for label, start, end in [
            ("calibration", 60.0, calibration_end),
            ("early_check", check_start, 1800.0),
            ("late_check", 1800.0, 3600.0),
        ]:
            checks[label] = {}
            for model, rate in [
                ("fitted_decay", fit["rate_per_s"]),
                ("frozen_prior", prior_rate),
                ("persistence", 0.0),
            ]:
                m = metrics(t, y, start, end, baseline, anchor, rate)
                independent = metrics(t, y, start, end, baseline, anchor, rate, order=32)
                difference = abs(m["mse_k2"] - independent["mse_k2"])
                max_quadrature_difference = max(max_quadrature_difference, difference)
                if difference > 1e-10:
                    raise ValueError("Quadrature agreement target failed")
                checks[label][model] = m
        improves = all(
            checks[w]["fitted_decay"]["rmse_k"] < checks[w][c]["rmse_k"]
            for w in ("early_check", "late_check")
            for c in ("frozen_prior", "persistence")
        )
        cases[name] = {
            "fit": fit,
            "calibration_check_gap_s": check_start - calibration_end,
            "windows": checks,
            "improves_both_comparators_in_both_check_windows": improves,
            "eligible_for_further_study_only": improves and not fit["boundary_optimum"],
            "physical_parameter_update_authorized_by_result": False,
        }
    result = {
        "protocol": "docs/stanford-k2-cooling-protocol.md",
        "hashes": {
            str(path.relative_to(ROOT)): digest(path)
            for path in [
                source,
                ROOT / "docs/stanford-k2-cooling-protocol.md",
                Path(__file__),
                ROOT / "src/physical_fpv/cooling_characterization.py",
            ]
        },
        "workbook_sha256": WORKBOOK_HASH,
        "source_attribution": "Catenaro and Onori, DOI10.17632/kxsbr4x3j2.2, CC BY4.0",
        "analyst_previewed_tail": True,
        "blind_validation": False,
        "check_windows_excluded_from_objective": True,
        "new_downloads": 0,
        "new_electrochemical_solves": 0,
        "independent_thermal_validation": False,
        "voltage_gate_changed": False,
        "historical_k2_voltage_rmse_mv": 55.0030541916,
        "historical_k2_voltage_rmse_gate_mv": 50.0,
        "prior": {
            "h_w_m2_k": 15.0,
            "cooling_area_m2": area,
            "heat_capacity_j_k_at_298_15k": heat_capacity,
            "rate_per_s": prior_rate,
            "tau_s": 1 / prior_rate,
            "pybamm_version": pybamm.__version__,
            "meaning": "Frozen constant-capacity zero-heat-source analytic approximation",
        },
        "pre_rest_baseline_interval_s": [float(bt[0]), float(bt[-1])],
        "pre_rest_skin_baseline_c": pre_baseline,
        "initial_60s_skin_range_c": [float(np.min(y[t <= 60])), float(np.max(y[t <= 60]))],
        "recorded_final_temperature_c": float(y[-1]),
        "nominal_25c_final_error_strict_lower_bound_k": float(25 - y[-1]),
        "nominal_25c_prediction_can_cross_below_asymptote": False,
        "quadrature_8_vs_32_max_mse_difference_k2": max_quadrature_difference,
        "scenarios": cases,
    }
    out.mkdir(parents=True, exist_ok=True)
    q = np.unique(np.r_[60.0, t[(t > 60) & (t < 3600)], 3600.0])
    columns = [q, np.interp(q, t, y)]
    names = ["step_time_s", "measured_skin_c"]
    for name, case in cases.items():
        f = case["fit"]
        for kind, rate in [("fit", f["rate_per_s"]), ("prior", prior_rate)]:
            columns.append(prediction(q, f["baseline_c"], f["anchor_temperature_c"], rate))
            names.append(name + "_" + kind + "_c")
    np.savetxt(
        out / "stanford-k2-cooling-predictions.csv",
        np.column_stack(columns),
        delimiter=",",
        header=",".join(names),
        comments="",
        fmt="%.12g",
    )
    result["prediction_csv_sha256"] = digest(out / "stanford-k2-cooling-predictions.csv")
    result["elapsed_s"] = time.monotonic() - started
    if result["elapsed_s"] > 60:
        raise ValueError("Analysis exceeded 60-second protocol budget")
    (out / "stanford-k2-cooling.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "docs/benchmarks/stanford-k2-rest-records.csv.gz"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    report = run(args.source, args.out)
    print(
        json.dumps(
            {
                "elapsed_s": report["elapsed_s"],
                "scenarios": {
                    name: {
                        "tau_s": c["fit"]["tau_s"],
                        "eligible": c["eligible_for_further_study_only"],
                    }
                    for name, c in report["scenarios"].items()
                },
            },
            indent=2,
        )
    )
