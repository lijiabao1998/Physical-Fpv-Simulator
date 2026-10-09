"""Verify saved low-rate results and compare with one pinned historical trajectory."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from run_stanford_k2_low_rate_model import digest, runtime_versions, source_digests, verify_inputs

from physical_fpv.contrast_persistence import time_at_charge
from physical_fpv.experimental_low_rate import (
    build,
    compare_meshes,
    empirical_report,
    physical_audit,
    prepare,
    validate_output_grid,
    verified,
    verify_endpoint,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
HIGH_MEMBERS = {
    "mesh120-timeseries.csv": "179d75db7c0ad638b7811feee9d1d4ecd49615848b5e2c81951671295dca710d",
    "input.json": "72548f736df9ed90d12c26b27603ccf3ca18681debb261ad1120e5c3d8ab3cbf",
    "forcing.csv": "c8a0ec7b33eaf61c890e4825dc23fccfc9149eddf92cd0030deb183ae43f1fb1",
}
HIGH_SOURCE_SHA = "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"


def require_reproduction(saved, recomputed):
    """Strict schema/verdict identity; roundoff allowance only for finite numbers."""
    if type(saved) is not type(recomputed):
        raise ValueError("Saved evidence type changed")
    if isinstance(saved, dict):
        if saved.keys() != recomputed.keys():
            raise ValueError("Saved evidence schema changed")
        for key in saved:
            require_reproduction(saved[key], recomputed[key])
    elif isinstance(saved, list):
        if len(saved) != len(recomputed):
            raise ValueError("Saved evidence length changed")
        for left, right in zip(saved, recomputed, strict=True):
            require_reproduction(left, right)
    elif isinstance(saved, float):
        tolerance = 256 * np.finfo(float).eps * max(1.0, abs(saved), abs(recomputed))
        if not np.isfinite([saved, recomputed]).all() or abs(saved - recomputed) > tolerance:
            raise ValueError("Saved numeric evidence does not reproduce")
    elif saved != recomputed:
        raise ValueError("Saved verdict or identity changed")


def historical_inputs():
    source = ROOT / "docs/benchmarks"
    content = verified(source / "stanford-k2-recovery-evidence.zip", ARCHIVE_SHA)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = {name: archive.read("stanford-k2-recovery/" + name) for name in HIGH_MEMBERS}
    if any(
        hashlib.sha256(data).hexdigest() != HIGH_MEMBERS[name] for name, data in members.items()
    ):
        raise ValueError("Historical member identity changed")
    rows = csv.DictReader(
        io.StringIO(
            gzip.decompress(
                verified(source / "stanford-k2-rest-records.csv.gz", HIGH_SOURCE_SHA)
            ).decode()
        )
    )
    observed = np.array(
        [
            [
                float(r["Step_Time(s)"]),
                -float(r["Current(A)"]),
                float(r["Voltage(V)"]),
                float(r["Surface_Temp(degC)"]) + 273.15,
            ]
            for r in rows
            if float(r["Step_Index"]) == 5
        ]
    )
    if len(observed) != 3436 or observed[0, 0] != 1.0003:
        raise ValueError("Historical measured support changed")
    model = np.genfromtxt(io.BytesIO(members["mesh120-timeseries.csv"]), delimiter=",", names=True)
    forcing = np.genfromtxt(io.BytesIO(members["forcing.csv"]), delimiter=",", names=True)
    from physical_fpv.current_profile import CurrentProfile

    profile = CurrentProfile(forcing["time_s"], forcing["positive_discharge_current_a"])
    return observed, model, profile, json.loads(members["input.json"])


def rate_points(prepared, low):
    high_observed, high, high_profile, high_input = historical_inputs()
    high_initial = float(high_profile.charge_integral_ah(high_observed[0, 0]))
    rows = []
    for q in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
        cases = {}
        for name, observed, time, voltage, temperature, capacity, missing in (
            (
                "low",
                prepared.observed,
                low["time_s"],
                low["voltage_v"],
                low["temperature_k"],
                low["capacity_ah"],
                prepared.initial_assumed_charge_ah,
            ),
            (
                "high",
                high_observed,
                high["time_s"],
                high["voltage_v"],
                high["temperature_k"],
                high["capacity_ah"],
                high_initial,
            ),
        ):
            t = time_at_charge(observed, q)
            measured = float(np.interp(t, observed[:, 0], observed[:, 2]))
            skin = float(np.interp(t, observed[:, 0], observed[:, 3]))
            record = {
                "time_s": t,
                "measured_voltage_v": measured,
                "measured_skin_k": skin,
                "model_supported": bool(time[0] <= t <= time[-1]),
            }
            if record["model_supported"]:
                predicted = float(np.interp(t, time, voltage))
                record.update(
                    model_voltage_v=predicted,
                    model_bulk_temperature_k=float(np.interp(t, time, temperature)),
                    voltage_error_v=predicted - measured,
                    model_charge_minus_conditioning_charge_ah=float(
                        np.interp(t, time, capacity) - missing - q
                    ),
                )
            else:
                record["unavailable_reason"] = "Charge-matched time outside model support"
            cases[name] = record
        measured_gap = cases["low"]["measured_voltage_v"] - cases["high"]["measured_voltage_v"]
        row = {
            "conditional_charge_ah": q,
            "cases": cases,
            "observed_low_minus_high_gap_v": measured_gap,
            "both_models_supported": all(c["model_supported"] for c in cases.values()),
        }
        if row["both_models_supported"]:
            model_gap = cases["low"]["model_voltage_v"] - cases["high"]["model_voltage_v"]
            difference = model_gap - measured_gap
            closure = difference - (
                cases["low"]["voltage_error_v"] - cases["high"]["voltage_error_v"]
            )
            if abs(closure) > 1e-12:
                raise ValueError("Rate-gap identity failed")
            row.update(
                model_low_minus_high_gap_v=model_gap,
                model_minus_observed_rate_gap_v=difference,
                identity_closure_v=closure,
            )
        rows.append(row)
    return {
        "points": rows,
        "historical_run_id": 37871885149,
        "historical_recorded_runtime_versions": {
            key: high_input.get(key + "_version") for key in ("python", "pybamm", "numpy")
        },
        "historical_source_commit": high_input["source_commit_sha"],
        "historical_archive_sha256": ARCHIVE_SHA,
        "historical_member_sha256": HIGH_MEMBERS,
        "historical_input_config_mesh": high_input["config"]["mesh_points"],
        "selected_historical_curve_mesh": 120,
        "high_initial_assumed_charge_excluded_ah": high_initial,
        "historical_current_profile_implementation_sha256": high_input["source_sha256"][
            "src/physical_fpv/current_profile.py"
        ],
        "rate_response_pass_threshold_defined": False,
        "independent_validation_established": False,
        "common_Ah_does_not_establish_common_SOC": True,
    }


def run(evidence):
    prepared = prepare(ROOT)
    manifest = verify_inputs(evidence.parent / "inputs")
    upload = json.loads((evidence.parent / "upload-receipt.json").read_text())
    if upload["manifest_sha256"] != digest(evidence.parent / "inputs/manifest.json"):
        raise ValueError("Durable input manifest identity changed")
    ledger = json.loads((evidence / "launch.json").read_text())
    if (
        ledger["status"] != "two_stages_complete_scientific_verdict_pending"
        or ledger["shared_wall_limit_s"] != 1200
        or ledger["worker_address_space_limit_bytes"] != 4_000_000_000
        or ledger["maximum_battery_dfns"] != 2
        or [stage["mesh"] for stage in ledger["stages"]] != [80, 120]
        or any(stage["exit_code"] != 0 for stage in ledger["stages"])
        or not 0 < ledger["elapsed_s"] <= 1200
        or ledger["source_commit"] != manifest["source_commit"]
        or ledger["source_commit"] != upload["source_commit"]
        or str(ledger["run_id"]) != str(manifest["run_id"])
        or str(ledger["run_id"]) != str(upload["run_id"])
    ):
        raise ValueError("Scientific execution was incomplete or exceeded reviewed scope")
    arrays, reports = {}, {}
    for mesh in (80, 120):
        directory = evidence / f"mesh{mesh}"
        report = json.loads((directory / "report.json").read_text())
        raw = (directory / "scalar-arrays.npz").read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != report["arrays_sha256"]
            or report["config"]["mesh_points"] != mesh
            or report["battery_dfns_solved"] != 1
            or report["source_commit"] != ledger["source_commit"]
            or report["source_sha256"] != source_digests()
            or report["parameter_fitting"] is not False
            or report["config"] != manifest["planned_configurations"][str(mesh)]
            or report["runtime_versions"] != manifest["runtime_versions"]
        ):
            raise ValueError("Saved result identity mismatch")
        with np.load(io.BytesIO(raw), allow_pickle=False) as packed:
            values = {name: packed[name] for name in packed.files}
        validate_output_grid(values["time_s"], prepared)
        if digest(directory / "final-state.npy") != report["final_state_sha256"]:
            raise ValueError("Retained final state identity changed")
        final_state = np.load(directory / "final-state.npy", allow_pickle=False)
        sim, outputs, rebuilt_config = build(prepared, mesh)
        if rebuilt_config != report["config"]:
            raise ValueError("Saved model construction does not reproduce")
        checks = verify_endpoint(sim, values, final_state, outputs)
        require_reproduction(
            report["output_receipt"],
            {
                "requested_grid_preserved": True,
                "true_endpoint_preserved": True,
                "stored_full_history_values": 0,
                "last_state_shape": [int(v) for v in final_state.shape],
                "endpoint_scalar_checks": checks,
            },
        )
        del sim
        audit = physical_audit(values, report["config"], prepared)
        require_reproduction(report["physical_audit"], audit)
        empirical = empirical_report(prepared, values, report["empirical"]["termination"], audit)
        require_reproduction(report["empirical"], empirical)
        arrays[mesh], reports[mesh] = values, report
    numerical = compare_meshes(arrays[80], arrays[120], reports[80], reports[120])
    result = {
        "numerical": numerical,
        "fine_empirical": reports[120]["empirical"],
        "rate_comparison": rate_points(prepared, arrays[120]),
        "conditional_protocol_gates_passed": bool(
            numerical["full_numerical_qualification_passed"]
            and reports[120]["empirical"]["electrical_gates_passed"]
            and all(reports[120]["empirical"]["thermal_proxy_gates"].values())
        ),
        "independent_validation_established": False,
        "historical_high_rate_voltage_rmse_v": 0.05500305419157363,
        "execution_runtime_versions": manifest["runtime_versions"],
        "verification_runtime_versions": runtime_versions(),
        "historical_high_rate_gate_passed": False,
        "new_fitting": False,
    }
    (evidence / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    report = run(args.evidence)
    print(json.dumps(report, indent=2, allow_nan=False))
