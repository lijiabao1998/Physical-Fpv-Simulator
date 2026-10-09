"""Fixed-inventory/rest compatibility from archived source rows; no solve or fit."""

import argparse
import csv
import gzip
import hashlib
import inspect
import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pybamm

from physical_fpv.stanford_data import HEADERS, inspect_records

SOURCE_SHA256 = "20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086"
RECORDS_GZIP_SHA256 = "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
RECORDS_CSV_SHA256 = "6b29e5efb46d1e868b889204f8a274c2f156fd1cc16bfd93b5014a1b5b919aeb"


def verify_original_workbook(path):
    """Validate every archived row against already available original source bytes."""
    import openpyxl

    if (
        path.stat().st_size != 1802458
        or hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("Original workbook identity changed")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        stream = workbook.active.iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Original source columns changed")
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["excel_row", *HEADERS])
        for index, row in enumerate(stream, 2):
            writer.writerow([index, row[0].isoformat(), *row[1:]])
    finally:
        workbook.close()
    if hashlib.sha256(output.getvalue().encode()).hexdigest() != RECORDS_CSV_SHA256:
        raise ValueError("Archived records differ from original workbook")
    return True


def history_boundary(previous, following):
    """Record chronology without promoting file-order qualification to continuity."""
    end = datetime.fromisoformat(previous["end_naive_local"])
    start = datetime.fromisoformat(following["start_naive_local"])
    if end.tzinfo is not None or start.tzinfo is not None:
        raise ValueError("Expected original naive-local timestamps, not converted UTC")
    gap = (start - end).total_seconds()
    if gap <= 0:
        raise ValueError("Nonpositive boundary does not establish continuous state history")
    return {
        "previous_filename": previous["filename"],
        "previous_workbook_sha256": previous["source_sha256"],
        "previous_end_naive_local": previous["end_naive_local"],
        "following_filename": following["filename"],
        "following_workbook_sha256": following["source_sha256"],
        "following_start_naive_local": following["start_naive_local"],
        "timezone": "Unspecified in source; no UTC conversion",
        "unobserved_gap_s": gap,
        "unobserved_gap_hours": gap / 3600,
        "continuous_state_replay_allowed": False,
        "reason": "No current, temperature or state observations bridge the inter-file gap",
    }


def require_continuous_state_replay(previous, following):
    """Fail closed: ordered endpoint summaries cannot authorize state carry-over."""
    boundary = history_boundary(previous, following)
    raise ValueError(
        f"Unobserved inter-file gap ({boundary['unobserved_gap_s']} s): "
        "continuous state replay is not supported"
    )


def last_window(time, voltage, temperature, seconds=600):
    boundary = time[-1] - seconds
    if boundary < time[0]:
        raise ValueError("Rest does not cover the requested final window")
    index = int(np.searchsorted(time, boundary))
    return {
        "requested_window_s": seconds,
        "first_actual_sample_start_s": float(time[index]),
        "first_actual_sample_duration_s": float(time[-1] - time[index]),
        "endpoint_minus_first_actual_sample_v": float(voltage[-1] - voltage[index]),
        "endpoint_minus_interpolated_exact_window_v": float(
            voltage[-1] - np.interp(boundary, time, voltage)
        ),
        "observed_window_voltage_range_v": [
            float(min(voltage[index:])),
            float(max(voltage[index:])),
        ],
        "observed_window_temperature_change_c": float(temperature[-1] - temperature[index]),
        "equilibrium_established": False,
    }


def charge_between(groups, start_phase, end_phase, method):
    """Signed charge; explicit boundary conventions, never estimated uncertainty."""
    selected = list(range(start_phase + 1, end_phase + 1))
    within = sum(float(np.trapezoid(groups[p][:, 4], groups[p][:, 1]) / 3600) for p in selected)
    ledger = []
    for phase in selected:
        previous, current = groups[phase - 1][-1], groups[phase][0]
        gap = current[0] - previous[0]
        origin = current[0] - current[1]
        if not previous[0] <= origin <= current[0]:
            raise ValueError("Commanded origin does not lie inside the unobserved boundary gap")
        linear = gap * (previous[4] + current[4]) / 2 / 3600
        command_hold = ((origin - previous[0]) * previous[4] + current[1] * current[4]) / 3600
        ledger.append(
            {
                "next_phase": phase,
                "gap_s": float(gap),
                "inferred_command_origin_test_s": float(origin),
                "linear_bridge_ah": float(linear),
                "command_hold_ah": float(command_hold),
            }
        )
    if method == "observed_only":
        return within, ledger
    key = {"linear_bridge": "linear_bridge_ah", "command_hold": "command_hold_ah"}[method]
    return within + sum(x[key] for x in ledger), ledger


def uniform_ocv(parameters, means, temperature):
    if not all(0 < v < 1 for v in means.values()):
        raise ValueError(
            "Hypothetical uniform inventory lies outside physical stoichiometry bounds"
        )
    q = pybamm.LithiumIonParameters()
    temp = pybamm.Scalar(temperature)
    value = q.p.prim.U(pybamm.Scalar(means["positive"]), temp) - q.n.prim.U(
        pybamm.Scalar(means["negative"]), temp
    )
    return float(parameters.process_symbol(value).evaluate())


def audit(root=Path(".")):
    path = root / "docs/benchmarks/stanford-k2-rest-records.csv.gz"
    packed = path.read_bytes()
    if hashlib.sha256(packed).hexdigest() != RECORDS_GZIP_SHA256:
        raise ValueError("Frozen source-row archive changed")
    plain = gzip.decompress(packed)
    if hashlib.sha256(plain).hexdigest() != RECORDS_CSV_SHA256:
        raise ValueError("Frozen source rows changed")
    reader = csv.reader(io.StringIO(plain.decode()))
    if next(reader) != ["excel_row", *HEADERS]:
        raise ValueError("Archived source schema changed")
    rows = []
    for expected_row, values in enumerate(reader, 2):
        if int(values[0]) != expected_row:
            raise ValueError("Source Excel rows were omitted or reordered")
        rows.append((datetime.fromisoformat(values[1]), *(float(v) for v in values[2:])))
    if len(rows) != 27826:
        raise ValueError("Source row count changed")
    inspection, _ = inspect_records(rows)
    if not inspection["canonical_six_step_sequence"]:
        raise ValueError("Six-phase source protocol is not intact")
    all_numeric = np.array([r[1:] for r in rows])
    groups = {phase: all_numeric[all_numeric[:, 2] == phase] for phase in range(1, 7)}
    phases = {}
    for phase, array in groups.items():
        t, v, current, temp = array[:, 1], array[:, 3], array[:, 4], array[:, 5]
        phases[str(phase)] = {
            "rows": len(t),
            "step_interval_s": [float(t[0]), float(t[-1])],
            "first_voltage_v": float(v[0]),
            "last_voltage_v": float(v[-1]),
            "first_skin_c": float(temp[0]),
            "last_skin_c": float(temp[-1]),
            "recorded_current_range_a": [float(min(current)), float(max(current))],
            "within_observed_phase_signed_charge_ah": float(np.trapezoid(current, t) / 3600),
        }
        if phase in (1, 4, 6):
            if np.any(current != 0):
                raise ValueError("Selected rest has nonzero recorded current")
            phases[str(phase)]["last_window"] = last_window(t, v, temp)
    state_path = root / "docs/benchmarks/stanford-k2-state-summary.json"
    state = json.loads(state_path.read_text())["records"]
    accounting = state["polarization.json"]["accounting"]
    capacities = accounting["fixed_active_capacity_ah"]
    initial = accounting["declared_initial_stoichiometry"]
    parameters = pybamm.ParameterValues("ORegan2022")
    function_file = Path(inspect.getfile(parameters["Negative electrode diffusivity [m2.s-1]"]))
    if (
        pybamm.__version__ != state["input.json"]["pybamm_version"]
        or hashlib.sha256(function_file.read_bytes()).hexdigest()
        != state["input.json"]["installed_parameter_source_sha256"]
    ):
        raise ValueError("Installed constituent functions differ from saved diagnostic")
    independent_capacity = {}
    for electrode in ("negative", "positive"):
        title = electrode.capitalize()
        published_mean = (
            parameters[f"Initial concentration in {electrode} electrode [mol.m-3]"]
            / parameters[f"Maximum concentration in {electrode} electrode [mol.m-3]"]
        )
        if abs(initial[electrode] - published_mean) > 1e-12:
            raise ValueError("Initial mean was changed from the published value")
        value = (
            float(pybamm.constants.F.value)
            / 3600
            * parameters[f"Maximum concentration in {electrode} electrode [mol.m-3]"]
            * parameters[f"{title} electrode active material volume fraction"]
            * parameters[f"{title} electrode thickness [m]"]
            * parameters["Electrode height [m]"]
            * parameters["Electrode width [m]"]
            * parameters["Number of electrodes connected in parallel to make a cell"]
        )
        independent_capacity[electrode] = float(value)
        if abs(value - capacities[electrode]) > 1e-12:
            raise ValueError("Published geometry/active capacity differs from saved diagnostic")
    methods = {}
    for method in ("observed_only", "linear_bridge", "command_hold"):
        charge, charge_gaps = charge_between(groups, 1, 4, method)
        discharge_signed, discharge_gaps = charge_between(groups, 4, 6, method)
        methods[method] = {
            "charge_ah": charge,
            "discharge_ah": -discharge_signed,
            "net_cycle_charge_ah": charge + discharge_signed,
            "charge_gap_ledger": charge_gaps,
            "discharge_gap_ledger": discharge_gaps,
        }
    observed_discharge = -phases["5"]["within_observed_phase_signed_charge_ah"]
    frozen_initial = -groups[5][0, 4] * groups[5][0, 1] / 3600
    methods["frozen_discharge_convention"] = {
        "charge_ah": methods["observed_only"]["charge_ah"],
        "discharge_ah": observed_discharge + frozen_initial,
        "initial_unmeasured_discharge_ah": float(frozen_initial),
        "charge_uses_observed_only": True,
    }
    comparisons = {}
    for method, values in methods.items():
        by_phase = {}
        for phase, charge in [(1, values["charge_ah"]), (4, 0), (6, values["discharge_ah"])]:
            means = {
                "negative": initial["negative"] - charge / capacities["negative"],
                "positive": initial["positive"] + charge / capacities["positive"],
            }
            temperature = phases[str(phase)]["last_skin_c"] + 273.15
            measured = phases[str(phase)]["last_voltage_v"]
            predicted = uniform_ocv(parameters, means, temperature)
            fixed_t = uniform_ocv(parameters, means, 298.15)
            by_phase[str(phase)] = {
                "reference_removed_charge_ah": charge,
                "hypothetical_uniform_means": means,
                "endpoint_skin_temperature_k": temperature,
                "measured_finite_rest_v": measured,
                "hypothetical_ocv_at_skin_t_v": predicted,
                "hypothetical_ocv_at_298_15k_v": fixed_t,
                "static_minus_measured_v": predicted - measured,
                "temperature_convention_difference_v": predicted - fixed_t,
                "outside_related_kinetic_sample_envelopes": {
                    "negative": not 0.1585 <= means["negative"] <= 1,
                    "positive": not 0.2598 <= means["positive"] <= 0.8499,
                },
                "ocp_transferability_at_this_state_independently_qualified": False,
                "solved_rest_state": False,
            }
        comparisons[method] = by_phase
    history_path = root / "docs/benchmarks/stanford-k2-k6-history-partial.json"
    history = json.loads(history_path.read_text())["saved_report_analysis"]["histories"]["k2"]
    low_rate = next(
        x for x in history["ordered_intervals"] if x["filename"] == "NMC_k2_0_05C_25degC.xlsx"
    )
    target = next(x for x in history["ordered_intervals"] if x["source_sha256"] == SOURCE_SHA256)
    boundary = history_boundary(low_rate, target)
    low_steps = {p["step"]: p for p in low_rate["contiguous_steps"]}
    return {
        "source_workbook_sha256": SOURCE_SHA256,
        "state_summary_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
        "installed_parameter_source_sha256": hashlib.sha256(function_file.read_bytes()).hexdigest(),
        "source_workbook_bytes": 1802458,
        "record_archive_sha256": RECORDS_GZIP_SHA256,
        "source_attribution": {
            "authors": ["Edoardo Catenaro", "Simona Onori"],
            "doi": "10.17632/kxsbr4x3j2.2",
            "license": "CC BY 4.0",
            "transformation": (
                "all original numeric values and naive dates serialized to CSV; "
                "Excel row index added"
            ),
        },
        "source_rows": len(rows),
        "phase_records": phases,
        "charge_conventions": methods,
        "fixed_active_capacities_ah": independent_capacity,
        "rest_comparisons": comparisons,
        "existing_lower_rate_evidence": {
            "source_summary_sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
            "filename": low_rate["filename"],
            "workbook_sha256": low_rate["source_sha256"],
            "prior_inspection_source_integrity_qualified": low_rate["source_integrity_qualified"],
            "nominal_rate_c": low_rate["nominal_rate_c"],
            "observed_discharge_ah": -low_steps[5]["signed_observed_charge_ah"],
            "last_post_rest_voltage_v": low_steps[6]["endpoint_voltage_v"][-1],
            "post_rest_observed_duration_s": low_steps[6]["observed_duration_s"],
            "raw_low_rate_workbook_reread_in_this_audit": False,
            "same_soc_as_1c_endpoint_established": False,
            "equilibrium_or_independent_electrode_inventory_established": False,
        },
        "inter_file_history_boundary": boundary,
        "new_model_solves": 0,
        "new_source_downloads": 0,
        "fitting_performed": False,
        "backward_accounting_assumptions": [
            "100% intercalation coulombic efficiency",
            "no side reactions or lithium loss",
            "fixed active material and capacities",
            "published means anchored at pre-discharge",
            "uniform-state OCP at skin-temperature proxy",
        ],
        "hypothesis_outcome": (
            "conditional joint rest/inventory/OCP incompatibility; "
            "unique cause and statistical falsification unresolved"
        ),
        "equilibrium_established": False,
        "measurement_uncertainty_supplied": False,
        "existing_discharge_rmse_v": 0.05500305419157363,
        "existing_empirical_pass": False,
        "new_dynamic_solve_recommended_now": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/k2-rest-inventory.json"))
    parser.add_argument("--verify-workbook", type=Path)
    args = parser.parse_args()
    if args.verify_workbook:
        verify_original_workbook(args.verify_workbook)
    result = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["rest_comparisons"], indent=2))


if __name__ == "__main__":
    main()
