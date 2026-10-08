"""Run the frozen k2/k6 source-history test within its acquisition/CPU budget."""

import argparse
import hashlib
import json
import os
import re
import resource
import signal
import time
import urllib.request
from pathlib import Path

import openpyxl

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_data import inspect_workbook, validate_workbook_bytes
from physical_fpv.stanford_history import aggregate_selected_histories

PROTOCOL = "docs/stanford-k2-k6-history-protocol.md"
MANIFEST = "data/stanford-k2-k6-history-manifest.json"
PROTOCOL_SHA256 = "2267b1c7f5da54f9bf1fb7314e8b4e46a764230c647a50c16da9b35f33bd4de2"
MANIFEST_SHA256 = "079b92508bba9e62ceabe3bb602fc358835d2abf799ea079ab0c0bc95e3f0cff"
SOURCE_FILES = (
    PROTOCOL,
    MANIFEST,
    "scripts/inspect_stanford_selected_history.py",
    "src/physical_fpv/stanford_history.py",
    "src/physical_fpv/stanford_chronology.py",
    "src/physical_fpv/stanford_data.py",
    "src/physical_fpv/attribution.py",
    "requirements-lock.txt",
    "requirements-data-lock.txt",
)
MAX_WALL_S = 600
MAX_NEW_BYTES = 80_000_000
MAX_ADDRESS_SPACE_BYTES = 4_000_000_000


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_digests():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCE_FILES}


def budget_stop(signum, frame):
    raise TimeoutError("Frozen 600-second acquisition/inspection/classification budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k2-k6-history"))
    args = parser.parse_args()
    if any((args.out / name).exists() for name in ("input.json", "report.json")):
        parser.error("Preserve previous evidence; choose a new output directory")
    sources = source_digests()
    if sources[PROTOCOL] != PROTOCOL_SHA256 or sources[MANIFEST] != MANIFEST_SHA256:
        raise ValueError("Frozen protocol or manifest changed")
    manifest = json.loads(Path(MANIFEST).read_text())
    expected = {
        f"NMC_{cell}_{rate}C_{temp}degC.xlsx"
        for cell in ("k2", "k6")
        for rate in ("0_05", "1", "2", "3", "5")
        for temp in ("05", "25", "35")
    }
    entries = sorted(manifest["files"], key=lambda e: e["filename"])
    if (
        len(entries) != 30
        or {e["filename"] for e in entries} != expected
        or sum(e["size"] for e in entries) != 69_170_148
    ):
        raise ValueError("Frozen selection changed")
    commit = os.environ.get("PHYSICAL_FPV_HISTORY_COMMIT")
    if commit is None or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Declare the frozen source commit in PHYSICAL_FPV_HISTORY_COMMIT")
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
    raw = Path("data/stanford/raw")
    raw.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out / "input.json",
        {
            "caller_declared_frozen_source_commit": commit,
            "source_sha256": sources,
            "max_wall_s": MAX_WALL_S,
            "max_new_download_bytes": MAX_NEW_BYTES,
            "effective_max_address_space_bytes": limit,
            "new_model_solves": 0,
            "fitting_performed": False,
        },
    )
    reports, acquisitions = [], []
    error, summary, active_file = None, None, None
    downloaded = 0
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, budget_stop)
    signal.setitimer(signal.ITIMER_REAL, MAX_WALL_S)
    try:
        for entry in entries:
            active_file = entry["filename"]
            path = raw / active_file
            cached = path.exists()
            if cached:
                content = path.read_bytes()
            else:
                if not args.fetch:
                    raise FileNotFoundError(
                        f"Missing source: {active_file}; explicit --fetch required"
                    )
                if downloaded + entry["size"] + 1 > MAX_NEW_BYTES:
                    raise ValueError("Next response would exceed the frozen transfer budget")
                remaining = MAX_WALL_S - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Frozen acquisition budget exhausted")
                request = urllib.request.Request(
                    entry["content_details"]["download_url"],
                    headers={"User-Agent": "PhysicalFPVResearch/0.1"},
                )
                chunks, received = [], 0
                with urllib.request.urlopen(request, timeout=min(60, remaining)) as response:
                    while received <= entry["size"]:
                        chunk = response.read(min(65_536, entry["size"] + 1 - received))
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        received += len(chunk)
                        chunks.append(chunk)
                content = b"".join(chunks)
            integrity = validate_workbook_bytes(content, entry)
            if not cached:
                temporary = path.with_suffix(".xlsx.tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
            acquisitions.append({**integrity, "already_cached": cached})
            del content
            inspected, _ = inspect_workbook(raw, entry, manifest)
            reports.append(inspected)
            write_json(args.out / (path.stem + ".json"), inspected)
            progress = {
                "active_filename": active_file,
                "completed_files": len(reports),
                "rows": inspected["measurement_rows"],
                "new_response_body_bytes": downloaded,
                "elapsed_s": time.monotonic() - started,
            }
            write_json(args.out / "progress.json", progress)
            print(json.dumps(progress), flush=True)
        summary = aggregate_selected_histories(reports, manifest)
        if source_digests() != sources:
            raise ValueError("Implementation changed during the frozen run")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "active_filename": active_file}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    if error:
        # Preserve partial evidence, without starting an unbounded second analysis.
        summary = {
            "recorded_premise_status": "unresolved",
            "recorded_premise_holds": None,
            "full_histories_qualified": False,
            "inspected_files": len(reports),
            "expected_files": len(entries),
            "missing_files": sorted(expected - {r["source"]["filename"] for r in reports}),
            "interpretation": "Incomplete or failed run cannot establish absent exposure",
        }
    summary.update(
        {
            "caller_declared_frozen_source_commit": commit,
            "source_sha256": sources,
            "elapsed_s": time.monotonic() - started,
            "error": error,
            "verified_acquisitions": acquisitions,
            "new_response_body_bytes": downloaded,
            "max_wall_s": MAX_WALL_S,
            "max_new_download_bytes": MAX_NEW_BYTES,
            "effective_max_address_space_bytes": limit,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "model_runs": 0,
            "fitting_performed": False,
            "inspection_report_sha256": {
                (Path(r["source"]["filename"]).stem + ".json"): hashlib.sha256(
                    (args.out / (Path(r["source"]["filename"]).stem + ".json")).read_bytes()
                ).hexdigest()
                for r in reports
            },
        }
    )
    write_json(args.out / "report.json", summary)
    write_evidence_attribution(args.out, ["stanford2021"])
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "inspected_files",
                    "full_histories_qualified",
                    "recorded_premise_status",
                    "error",
                )
            }
        ),
        flush=True,
    )
    if error or not summary["full_histories_qualified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
