"""Inspect all 15 already-pinned k1 source files; no download, fitting or battery solve."""

import argparse
import hashlib
import json
import re
import signal
import time
from pathlib import Path

import openpyxl

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_data import HEADERS, validate_workbook_bytes
from physical_fpv.stanford_transitions import inspect_transitions

MANIFEST_SHA256 = "d0ba632f37af43e8359aa195f45b73960235c9ffafefeaa6ccdafe78be9037b3"


def stop(signum, frame):
    raise TimeoutError("600-second source-inspection budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-transitions"))
    args = parser.parse_args()
    manifest_path = Path("data/stanford-chronology-manifest.json")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Pinned 15-file source selection changed")
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["files"]) != 15 or sum(f["size"] for f in manifest["files"]) > 40_000_000:
        raise ValueError("Declared source byte/count budget changed")
    if not openpyxl.DEFUSEDXML:
        raise RuntimeError("Pinned defusedxml protection is required")
    args.out.mkdir(parents=True, exist_ok=True)
    reports, error = [], None
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, 600)
    try:
        for entry in manifest["files"]:
            if Path(entry["filename"]).name != entry["filename"]:
                raise ValueError("Expected a plain source filename")
            path = Path("data/stanford/raw") / entry["filename"]
            integrity = validate_workbook_bytes(path.read_bytes(), entry)
            workbook = openpyxl.load_workbook(
                path, read_only=True, data_only=True, keep_links=False
            )
            try:
                if len(workbook.worksheets) != 1:
                    raise ValueError("Expected one source worksheet")
                rows = workbook.worksheets[0].iter_rows(values_only=True)
                if tuple(next(rows)) != HEADERS:
                    raise ValueError("Source column units/schema changed")
                result = inspect_transitions(rows)
            finally:
                workbook.close()
            result["source"] = integrity
            label = re.fullmatch(r"NMC_k1_(0_05|1|2|3|5)C_(05|25|35)degC.xlsx", path.name)
            if label is None:
                raise ValueError("Unexpected source rate/temperature label")
            result["nominal_rate_label_c"] = float(label[1].replace("_", "."))
            result["nominal_chamber_label_celsius"] = int(label[2])
            reports.append(result)
            (args.out / (path.stem + ".json")).write_text(
                json.dumps(result, indent=2, allow_nan=False) + "\n"
            )
            print(
                json.dumps(
                    {
                        "completed": len(reports),
                        "filename": path.name,
                        "elapsed_s": time.monotonic() - started,
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    reports.sort(
        key=lambda r: (r["blocks"][0]["first"]["date_naive_local"], r["source"]["filename"])
    )
    preceding_high_rates = []
    for case in reports:
        case["recorded_earlier_high_rate_files"] = preceding_high_rates.copy()
        if case["nominal_rate_label_c"] >= 2:
            preceding_high_rates.append(case["source"]["filename"])
    report = {
        "scope": (
            "Exploratory measurement-boundary inspection of the same k1 cell; "
            "no independent cohort or new model validation"
        ),
        "selection": (
            "All 15 files of the preexisting frozen k1 chronology manifest; no error-based subset"
        ),
        "complete": len(reports) == 15 and error is None,
        "error": error,
        "elapsed_s": time.monotonic() - started,
        "wall_budget_s": 600,
        "manifest_sha256": MANIFEST_SHA256,
        "implementation_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (
                "src/physical_fpv/stanford_transitions.py",
                "scripts/inspect_stanford_transitions.py",
            )
        },
        "dataset_doi": manifest["dataset_doi"],
        "license": manifest["license"],
        "authors": manifest["authors"],
        "chronological_cases": reports,
        "fitting_performed": False,
        "new_model_solves": 0,
        "new_downloaded_bytes": 0,
        "history_warning": (
            "Same cell measured repeatedly. Earlier nominal rates >=2C are explicitly listed; "
            "unrecorded exposure is unknown. Source chronology is context, "
            "not a controlled causal comparison."
        ),
        "measurement_uncertainty": {
            "voltage_standard_uncertainty_v": None,
            "current_standard_uncertainty_a": None,
            "ratio_standard_uncertainty_ohm": None,
            "sampling_clock_uncertainty_s": None,
            "note": (
                "Campaign channel calibration and timing uncertainty are unavailable. "
                "Displayed precision and conflicting advertised instrument resolution are "
                "not measurement uncertainty; no confidence bands are invented."
            ),
        },
        "protocol_comparison_limits": (
            "Rest duration, adjacent CV endpoint, temperatures, exact sample gap and first ten "
            "loaded samples are retained for each file. The first commanded-step interval is "
            "unobserved, so actual current ramp and instantaneous impedance are unresolved. "
            "No time realignment or SOC normalization makes these a matched pulse experiment."
        ),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    write_evidence_attribution(args.out, ["stanford2021"])
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
