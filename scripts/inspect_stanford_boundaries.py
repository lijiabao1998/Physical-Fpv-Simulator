"""Inspect all six existing source cells and four boundaries, without network or model calls."""

import argparse
import hashlib
import io
import json
import os
import re
import resource
import signal
import time
from pathlib import Path

import openpyxl

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_boundaries import inspect_boundaries
from physical_fpv.stanford_data import HEADERS, validate_workbook_bytes

PROTOCOL = "docs/stanford-boundary-protocol.md"
MANIFEST = "data/stanford-manifest.json"
PROTOCOL_SHA256 = "519a4946e9b257d26ebdea94f9f29c394a916acd59b6ec56247f97a4f6f18e70"
MANIFEST_SHA256 = "94bde5dd872de039d145abf33f66fc81c38897b4666d68586f00c950478dc482"
SOURCE_FILES = (
    PROTOCOL,
    MANIFEST,
    "scripts/inspect_stanford_boundaries.py",
    "src/physical_fpv/stanford_boundaries.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/attribution.py",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
)
MAX_WALL_S = 120
MAX_ADDRESS_SPACE_BYTES = 4_000_000_000


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_digests():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCE_FILES}


def budget_stop(signum, frame):
    raise TimeoutError("Frozen 120-second local source verification/analysis budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-boundaries"))
    args = parser.parse_args()
    if any((args.out / name).exists() for name in ("input.json", "report.json")):
        parser.error("Preserve previous evidence; choose a new output directory")
    sources = source_digests()
    if sources[PROTOCOL] != PROTOCOL_SHA256 or sources[MANIFEST] != MANIFEST_SHA256:
        raise ValueError("Frozen protocol or manifest changed")
    manifest = json.loads(Path(MANIFEST).read_text())
    entries = sorted(manifest["files"], key=lambda e: e["filename"])
    expected = [f"NMC_k{i}_1C_25degC.xlsx" for i in range(1, 7)]
    if [e["filename"] for e in entries] != expected or sum(
        e["size"] for e in entries
    ) != 10_973_677:
        raise ValueError("Frozen selection changed")
    commit = os.environ.get("PHYSICAL_FPV_BOUNDARY_COMMIT")
    if commit is None or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Declare the frozen source commit in PHYSICAL_FPV_BOUNDARY_COMMIT")
    if not openpyxl.DEFUSEDXML:
        raise RuntimeError("Pinned defusedxml protection is required")
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = (
        MAX_ADDRESS_SPACE_BYTES
        if hard == resource.RLIM_INFINITY
        else min(hard, MAX_ADDRESS_SPACE_BYTES)
    )
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out / "input.json",
        {
            "caller_declared_frozen_source_commit": commit,
            "source_sha256": sources,
            "max_wall_s": MAX_WALL_S,
            "effective_max_address_space_bytes": limit,
            "new_download_bytes": 0,
            "new_model_solves": 0,
            "fitting_performed": False,
        },
    )
    cases, error, active_file = [], None, None
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, budget_stop)
    signal.setitimer(signal.ITIMER_REAL, MAX_WALL_S)
    try:
        for entry in entries:
            active_file = entry["filename"]
            content = (Path("data/stanford/raw") / active_file).read_bytes()
            integrity = validate_workbook_bytes(content, entry)
            book = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=True, keep_links=False
            )
            try:
                if len(book.worksheets) != 1:
                    raise ValueError("Expected one identified measurement sheet")
                rows = book.worksheets[0].iter_rows(values_only=True)
                if tuple(next(rows)) != HEADERS:
                    raise ValueError("Frozen source column names or units changed")
                records = list(rows)
            finally:
                book.close()
            analysis = inspect_boundaries(records)
            case = {
                "cell_id": active_file.split("_")[1],
                "source": integrity,
                "analysis": analysis,
            }
            cases.append(case)
            write_json(args.out / (Path(active_file).stem + ".json"), case)
            progress = {
                "active_filename": active_file,
                "completed_cells": len(cases),
                "source_rows": len(records),
                "elapsed_s": time.monotonic() - started,
            }
            write_json(args.out / "progress.json", progress)
            print(json.dumps(progress), flush=True)
            del records, content
        if source_digests() != sources:
            raise ValueError("Implementation changed during the frozen run")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "active_filename": active_file}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    report = {
        "dataset_doi": manifest["dataset_doi"],
        "authors": manifest["authors"],
        "license": manifest["license"],
        "caller_declared_frozen_source_commit": commit,
        "source_sha256": sources,
        "cases": cases,
        "complete": len(cases) == 6 and error is None,
        "inspected_cells": len(cases),
        "expected_cells": 6,
        "unavailable_sources": sorted(set(expected) - {c["source"]["filename"] for c in cases}),
        "error": error,
        "elapsed_s": time.monotonic() - started,
        "max_wall_s": MAX_WALL_S,
        "effective_max_address_space_bytes": limit,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "new_download_bytes": 0,
        "model_runs": 0,
        "fitting_performed": False,
        "true_ohmic_or_contact_resistance_identified": False,
        "fixed_resistance_component_excluded": False,
        "independent_predictive_validation_established": False,
        "prior_history_contrast": "Unresolved; three k6/5C downloads remain stopped",
        "interpretation": (
            "Apparent ratios at finite, unequal delays with changing state/relaxation. "
            "An arithmetic fixed-R-alone description is distinct from a fixed-R component. "
            "Unknown measurement uncertainty prevents statistical physical rejection."
        ),
        "case_report_sha256": {
            (Path(c["source"]["filename"]).stem + ".json"): hashlib.sha256(
                (args.out / (Path(c["source"]["filename"]).stem + ".json")).read_bytes()
            ).hexdigest()
            for c in cases
        },
    }
    write_json(args.out / "report.json", report)
    write_evidence_attribution(args.out, ["stanford2021"])
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "complete",
                    "inspected_cells",
                    "error",
                    "elapsed_s",
                    "new_download_bytes",
                    "model_runs",
                )
            }
        ),
        flush=True,
    )
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
