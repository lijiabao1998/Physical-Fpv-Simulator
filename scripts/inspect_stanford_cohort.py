"""Bounded, frozen six-cell source comparison; no battery-model run or fit."""

import argparse
import hashlib
import itertools
import json
import os
import re
import signal
import time
import urllib.request
from pathlib import Path

import numpy as np
import openpyxl

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_cohort import compare_discharge_pair, summary_discharge
from physical_fpv.stanford_data import HEADERS, inspect_workbook, validate_workbook_bytes
from physical_fpv.stanford_transitions import inspect_transitions

PROTOCOL_SHA256 = "56e6fad6558bbe3863e016d7aeafb131f7229c579518b40f51bbfac52354d294"
MANIFEST_SHA256 = "94bde5dd872de039d145abf33f66fc81c38897b4666d68586f00c950478dc482"
PROTOCOL_FROZEN_COMMIT = "eae7d9e40a104421da938c069bdd7683b06ab062"
SOURCE_FILES = (
    "docs/stanford-cohort-protocol.md",
    "data/stanford-manifest.json",
    "scripts/inspect_stanford_cohort.py",
    "src/physical_fpv/stanford_cohort.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/stanford_transitions.py",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
)


def source_digests():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCE_FILES}


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def budget_stop(signum, frame):
    raise TimeoutError("Frozen600-second source acquisition/inspection budget exhausted")


def rest_diagnostic(rows):
    selected = [(i, r) for i, r in enumerate(rows, 2) if r[3] == 4]
    if not selected:
        return {"available": False, "reason": "No recorded phase4 rest"}
    values = np.array([r[1:] for _, r in selected], dtype=float)
    time_s, voltage, current, skin_c = values[:, 1], values[:, 3], values[:, 4], values[:, 5]
    result = {
        "available": True,
        "excel_rows_inclusive": [selected[0][0], selected[-1][0]],
        "recorded_interval_s": [float(time_s[0]), float(time_s[-1])],
        "observed_rest_duration_s": float(time_s[-1] - time_s[0]),
        "maximum_absolute_recorded_current_a": float(np.max(np.abs(current))),
        "final_voltage_v": float(voltage[-1]),
        "final_skin_temperature_c": float(skin_c[-1]),
        "equilibrium_established": False,
    }
    if len(time_s) < 2 or np.any(np.diff(time_s) <= 0):
        result.update(
            {
                "last_600s_voltage_drift_v": None,
                "drift_unavailable_reason": "Insufficient or ambiguous rest clock",
            }
        )
        return result
    start = max(time_s[0], time_s[-1] - 600)
    result.update(
        {
            "drift_interval_s": [float(start), float(time_s[-1])],
            "last_600s_voltage_drift_v": float(voltage[-1] - np.interp(start, time_s, voltage)),
            "signed_observed_rest_charge_ah": float(np.trapezoid(current, time_s) / 3600),
        }
    )
    return result


def protocol_details(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        rows = book.worksheets[0].iter_rows(values_only=True)
        if tuple(next(rows)) != HEADERS:
            raise ValueError("Source schema changed between inspections")
        records = list(rows)
    finally:
        book.close()
    rest = rest_diagnostic(records)
    try:
        detail = inspect_transitions(records)
        blocks = detail["blocks"]
        transitions = {
            "recorded_steps": detail["recorded_steps"],
            "post_discharge_rest_recorded": detail["post_discharge_rest_recorded"],
            "preceding_cc_end": blocks[1]["last"],
            "preceding_cv_end": blocks[2]["last"],
            "rest_to_discharge": detail["rest_to_discharge"],
            "first_ten_loaded_samples": blocks[4]["first_ten_samples"],
            "sampling_interpretation": detail["interpretation"],
        }
        error = None
    except ValueError as exc:
        transitions, error = None, {"type": type(exc).__name__, "message": str(exc)}
    return {"pre_discharge_rest": rest, "transitions": transitions, "transition_error": error}


def pairwise_reports(observations):
    pairs, unavailable = [], []
    for a, b in itertools.combinations([f"k{i}" for i in range(1, 7)], 2):
        if a not in observations or b not in observations:
            unavailable.append(
                {
                    "reference_id": a,
                    "candidate_id": b,
                    "reason": "Missing or unqualified source discharge",
                }
            )
            continue
        try:
            pairs.append(compare_discharge_pair(observations[a], observations[b], a, b))
        except ValueError as exc:
            unavailable.append({"reference_id": a, "candidate_id": b, "reason": str(exc)})
    return pairs, unavailable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/stanford-cohort"))
    args = parser.parse_args()
    if any((args.out / name).exists() for name in ("input.json", "report.json")):
        parser.error("Preserve prior attempt evidence; choose a new output directory")
    sources = source_digests()
    if (
        sources["docs/stanford-cohort-protocol.md"] != PROTOCOL_SHA256
        or sources["data/stanford-manifest.json"] != MANIFEST_SHA256
    ):
        raise ValueError("Frozen protocol or source selection changed")
    manifest = json.loads(Path("data/stanford-manifest.json").read_text())
    entries = sorted(manifest["files"], key=lambda e: e["filename"])
    expected = [f"NMC_k{i}_1C_25degC.xlsx" for i in range(1, 7)]
    if [e["filename"] for e in entries] != expected or sum(
        e["size"] for e in entries[1:]
    ) != 9_104_714:
        raise ValueError("Frozen six-cell file or byte selection changed")
    if not openpyxl.DEFUSEDXML:
        raise RuntimeError("Pinned defusedxml protection is required")
    implementation_commit = os.environ.get("PHYSICAL_FPV_COHORT_COMMIT")
    if implementation_commit is not None and not re.fullmatch(
        r"[0-9a-f]{40}", implementation_commit
    ):
        raise ValueError("Caller-declared implementation commit is malformed")
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out / "input.json",
        {
            "protocol_frozen_commit": PROTOCOL_FROZEN_COMMIT,
            "caller_declared_implementation_commit": implementation_commit,
            "source_sha256": sources,
            "max_wall_s": 600,
            "max_new_download_bytes": 10_000_000,
            "new_model_solves": 0,
            "fitting_performed": False,
        },
    )
    raw = Path("data/stanford/raw")
    cases, observations, error, downloaded = [], {}, None, 0
    pairs, unavailable = [], []
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, budget_stop)
    signal.setitimer(signal.ITIMER_REAL, 600)
    active_file = None
    try:
        for entry in entries:
            active_file = entry["filename"]
            cell_id = active_file.split("_")[1]
            path = raw / active_file
            cached = path.exists()
            if cached:
                content = path.read_bytes()
            else:
                if cell_id == "k1" or not args.fetch:
                    raise FileNotFoundError(f"Required cached source is unavailable: {active_file}")
                if downloaded + entry["size"] + 1 > 10_000_000:
                    raise ValueError("Acquisition would exceed the frozen transfer budget")
                remaining = 600 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Frozen acquisition budget exhausted")
                request = urllib.request.Request(
                    entry["content_details"]["download_url"],
                    headers={"User-Agent": "PhysicalFPVResearch/0.1"},
                )
                with urllib.request.urlopen(request, timeout=min(60, remaining)) as response:
                    content = response.read(entry["size"] + 1)
                downloaded += len(content)
            integrity = validate_workbook_bytes(content, entry)
            if not cached:
                temporary = path.with_suffix(".xlsx.tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
            inspected, observed = inspect_workbook(raw, entry, manifest)
            if observed is None:
                raise ValueError("No unique contiguous discharge exists in the source")
            details = protocol_details(path)
            quality_flags = []
            clock = inspected["measurement_clock_audit"]
            if (
                clock["backwards_date_intervals"]
                or clock["max_relative_date_test_clock_discrepancy_s"] > 1
            ):
                quality_flags.append("date_test_clock_inconsistent")
            if details["transition_error"]:
                quality_flags.append("transition_protocol_unqualified")
            try:
                summary = summary_discharge(observed, cell_id)
                metric_error = None
                if "date_test_clock_inconsistent" in quality_flags:
                    metric_error = {
                        "type": "ClockQualificationError",
                        "message": "Inconsistent clocks; source retained and pairing disabled",
                    }
                    quality_flags.append("discharge_comparison_unqualified")
                else:
                    observations[cell_id] = observed
            except ValueError as exc:
                summary = None
                metric_error = {"type": type(exc).__name__, "message": str(exc)}
                quality_flags.append("discharge_comparison_unqualified")
            case = {
                "cell_id": cell_id,
                "integrity": integrity,
                "already_cached": cached,
                "source_inspection": inspected,
                "observed_discharge": summary,
                "discharge_metric_error": metric_error,
                "protocol_details": details,
                "quality_flags": quality_flags,
                "manufacturing_batch": "unverified",
                "history_eligibility": (
                    "Published k1 history: only nominal25C/0.05C precedes this record; "
                    "unrecorded history unknown"
                    if cell_id == "k1"
                    else "Prior high-rate exposure and freshness unresolved; "
                    "only this one workbook inspected"
                ),
            }
            csv_path = args.out / f"{cell_id}-observed.csv"
            np.savetxt(
                csv_path,
                observed,
                delimiter=",",
                comments="",
                header="time_s,raw_signed_current_a,measured_voltage_v,measured_skin_temperature_k",
            )
            case["observed_csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            cases.append(case)
            write_json(args.out / f"{cell_id}-inspection.json", case)
            print(
                json.dumps(
                    {
                        "cell": cell_id,
                        "completed_files": len(cases),
                        "new_downloaded_bytes": downloaded,
                        "elapsed_s": time.monotonic() - started,
                        "quality_flags": quality_flags,
                    }
                ),
                flush=True,
            )
        active_file = None
        pairs, unavailable = pairwise_reports(observations)
    except Exception as exc:
        error = {"filename": active_file, "type": type(exc).__name__, "message": str(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    if source_digests() != sources:
        raise RuntimeError("Comparison implementation or frozen inputs changed during inspection")
    if error is not None and not pairs:
        unavailable = [
            {
                "reference_id": a,
                "candidate_id": b,
                "reason": "Inspection/analysis attempt incomplete",
            }
            for a, b in itertools.combinations([f"k{i}" for i in range(1, 7)], 2)
        ]
    report = {
        "scope": (
            "All-six source-to-source diagnostic; "
            "no additional model error or physical cause established"
        ),
        "input": json.loads((args.out / "input.json").read_text()),
        "all_sources_inspected": len(cases) == 6 and error is None,
        "all_pairwise_metrics_available": len(pairs) == 15,
        "elapsed_s": time.monotonic() - started,
        "new_downloaded_bytes": downloaded,
        "error": error,
        "cases": cases,
        "pairwise_comparisons": pairs,
        "unavailable_pairs": unavailable,
        "measurement_uncertainty": {
            "voltage_v": None,
            "current_a": None,
            "temperature_k": None,
            "clock_s": None,
            "reason": "No campaign calibration uncertainty available; precision is not uncertainty",
        },
        "manufacturing_batch_identity_established": False,
        "history_eligibility_for_k2_to_k6_established": False,
        "new_model_solves": 0,
        "fitting_performed": False,
        "model_parameters_or_acceptance_gates_changed": False,
    }
    write_json(args.out / "report.json", report)
    write_evidence_attribution(args.out, ["stanford2021"])
    if not report["all_sources_inspected"] or not report["all_pairwise_metrics_available"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
