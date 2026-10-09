"""Verify archived k2 state accounting and evaluate OCP algebra; never solve or fit."""

import argparse
import gzip
import hashlib
import inspect
import io
import json
from pathlib import Path

import numpy as np
import pybamm

from physical_fpv.polarization import VOLTAGE_TERMS

SOURCE_ZIP_SHA256 = "450307f4b2669b46edb7a3a0a2e3d53619a12bb4f87e7e74e71ce47c117236c9"


def mean_on(time, values, start, stop):
    knots = np.unique(np.r_[start, time[(time > start) & (time < stop)], stop])
    return float(np.trapezoid(np.interp(knots, time, values), knots) / (stop - start))


def analyze(root=Path(".")):
    summary = json.loads((root / "docs/benchmarks/stanford-k2-state-summary.json").read_text())
    if summary["source_zip_sha256"] != SOURCE_ZIP_SHA256 or summary["source_run_id"] != 37881497526:
        raise ValueError("State-diagnostic source identity changed")
    compressed = (root / summary["scalar_csv"]).read_bytes()
    if hashlib.sha256(compressed).hexdigest() != summary["scalar_gzip_sha256"]:
        raise ValueError("Derived scalar archive changed")
    csv = gzip.decompress(compressed)
    if (
        hashlib.sha256(compressed).hexdigest() != summary["scalar_gzip_sha256"]
        or hashlib.sha256(csv).hexdigest() != summary["scalar_csv_sha256"]
    ):
        raise ValueError("Derived scalar archive changed")
    data = np.genfromtxt(io.BytesIO(csv), delimiter=",", names=True)
    records = summary["records"]
    result = records["empirical-report.json"]
    accounting = records["polarization.json"]
    if (
        summary["source_commit"] != "6d74c8d4a75ece4a1b8b3efafbfb127740f0b661"
        or records["outcome.json"]["scientific_solve_calls"] != 1
        or records["status.json"]["status"] != "completed"
        or not 0 < records["status.json"]["elapsed_s"] < 1200
        or records["external-exit.json"]["exit_code"] != 0
        or result["source_window_empirical_qualification_passed"] is not False
        or not np.isclose(result["voltage_rmse_v"], 0.05500305419157363, atol=1e-12, rtol=0)
    ):
        raise ValueError("Recorded execution identity or scientific failure changed")
    t, terminal = data["time_s"], data["terminal_voltage_v"]
    if len(t) != summary["scalar_rows"] or np.any(np.diff(t) <= 0):
        raise ValueError("Invalid native output clock")
    for key in data.dtype.names:
        if not np.isfinite(data[key]).all():
            raise ValueError("Nonfinite archived observable")
    reconstructed = np.zeros_like(t)
    for key, _, sign in VOLTAGE_TERMS:
        if not np.array_equal(data[f"{key}_signed_v"], sign * data[f"{key}_raw_v"]):
            raise ValueError("Signed voltage contribution was relabeled")
        reconstructed += data[f"{key}_signed_v"]
    closure = float(max(abs(reconstructed - terminal)))
    if closure > 1e-6 or not np.isclose(
        closure, accounting["voltage_reconstruction_max_error_v"], atol=1e-12, rtol=0
    ):
        raise ValueError("Voltage identity does not close")
    charge_errors = {}
    for electrode, direction in (("negative", -1), ("positive", 1)):
        capacity = accounting["accounting"]["fixed_active_capacity_ah"][electrode]
        initial = accounting["accounting"]["declared_initial_stoichiometry"][electrode]
        expected = initial + direction * data["capacity_ah"] / capacity
        charge_errors[electrode] = float(
            max(abs(data[f"{electrode}_volume_mean_stoichiometry"] - expected))
        )
        if charge_errors[electrode] > 1e-6:
            raise ValueError("Electrode inventory does not follow fixed-volume accounting")
    # Pure constituent-function evaluation at saved states. No new time integration.
    parameters = pybamm.ParameterValues("ORegan2022")
    function_file = Path(inspect.getfile(parameters["Negative electrode diffusivity [m2.s-1]"]))
    if (
        pybamm.__version__ != records["input.json"]["pybamm_version"]
        or hashlib.sha256(function_file.read_bytes()).hexdigest()
        != records["input.json"]["installed_parameter_source_sha256"]
    ):
        raise ValueError("Installed constituent functions differ from recorded diagnostic")
    q = pybamm.LithiumIonParameters()
    negative = pybamm.Vector(data["negative_volume_mean_stoichiometry"])
    positive = pybamm.Vector(data["positive_volume_mean_stoichiometry"])

    def ocv(temp):
        symbol = q.p.prim.U(positive, temp) - q.n.prim.U(negative, temp)
        return np.asarray(parameters.process_symbol(symbol).evaluate()).reshape(-1)

    actual_ocv = ocv(pybamm.Vector(data["bulk_temperature_k"]))
    reference_ocv = ocv(pybamm.Scalar(298.15))
    ocv_error = float(max(abs(actual_ocv - data["bulk_ocv_v"])))
    if ocv_error > 1e-6:
        raise ValueError("Static OCP evaluation does not reproduce exported bulk OCV")
    direct_thermal = actual_ocv - reference_ocv
    start, observed_stop = result["assumptions"]["observed_interval_s"]
    boundaries = np.linspace(start, observed_stop, 5)
    regimes = []
    for quarter, (a, b) in enumerate(zip(boundaries[:-1], boundaries[1:], strict=True), 1):
        stop = min(b, t[-1])
        if a >= stop:
            continue
        terms = {
            key: mean_on(t, data[f"{key}_signed_v"], a, stop)
            for key, _, _ in VOLTAGE_TERMS
            if "bulk_ocp" not in key
        }
        regimes.append(
            {
                "observed_duration_quarter": quarter,
                "interval_s": [float(a), float(stop)],
                "mean_signed_terms_v": terms,
                "mean_bulk_ocv_v": mean_on(t, data["bulk_ocv_v"], a, stop),
                "mean_terminal_v": mean_on(t, terminal, a, stop),
                "mean_direct_ocp_temperature_term_v": mean_on(t, direct_thermal, a, stop),
            }
        )
    late = 3000.0
    changes = {
        key: float(data[f"{key}_signed_v"][-1] - np.interp(late, t, data[f"{key}_signed_v"]))
        for key, _, _ in VOLTAGE_TERMS
        if "bulk_ocp" not in key
    }
    return {
        "source_run_id": summary["source_run_id"],
        "source_commit": summary["source_commit"],
        "source_zip_sha256": SOURCE_ZIP_SHA256,
        "scalar_gzip_sha256": summary["scalar_gzip_sha256"],
        "new_source_downloads": 0,
        "new_scientific_solves": 0,
        "fitting_performed": False,
        "voltage_identity_max_error_v": closure,
        "mean_inventory_max_errors": charge_errors,
        "ocp_algebra_reconstruction_error_v": ocv_error,
        "direct_temperature_ocp_diagnostic": {
            "definition": "Ubulk(saved states, saved T) minus Ubulk(same states, 298.15K)",
            "minimum_v": float(min(direct_thermal)),
            "maximum_v": float(max(direct_thermal)),
            "initial_v": float(direct_thermal[0]),
            "endpoint_v": float(direct_thermal[-1]),
            "indirect_temperature_effects_isolated": False,
            "not_a_resimulated_isothermal_counterfactual": True,
        },
        "quarter_model_accounting": regimes,
        "late_change_3000s_to_cutoff": {
            "bulk_ocv_change_v": float(
                data["bulk_ocv_v"][-1] - np.interp(late, t, data["bulk_ocv_v"])
            ),
            "terminal_change_v": float(terminal[-1] - np.interp(late, t, terminal)),
            "signed_term_changes_v": changes,
        },
        "scientific_voltage_rmse_v": result["voltage_rmse_v"],
        "scientific_empirical_pass": result["source_window_empirical_qualification_passed"],
        "unique_empirical_cause_identified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/k2-state-analysis.json"))
    args = parser.parse_args()
    result = analyze()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
