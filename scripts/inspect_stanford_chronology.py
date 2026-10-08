"""Inspect the predeclared 15-file k1 history within a bounded acquisition budget."""

import argparse
import hashlib
import json
import signal
import time
import urllib.request
from pathlib import Path

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_chronology import summarize_chronology
from physical_fpv.stanford_data import inspect_workbook, validate_workbook_bytes

PROTOCOL_SHA256 = "1983cb1f458667b874caae4d39d62f4faafb42e3ead09a0400c939d6d59e47c3"
MANIFEST_SHA256 = "d0ba632f37af43e8359aa195f45b73960235c9ffafefeaa6ccdafe78be9037b3"


def stop_for_timeout(signum, frame):
    raise TimeoutError("Declared 600-second acquisition/inspection budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/stanford-chronology"))
    args = parser.parse_args()
    paths = {
        "docs/stanford-chronology-protocol.md": PROTOCOL_SHA256,
        "data/stanford-chronology-manifest.json": MANIFEST_SHA256,
    }
    for path, expected in paths.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen chronology protocol/manifest changed")
    manifest = json.loads(Path("data/stanford-chronology-manifest.json").read_text())
    if len(manifest["files"]) != 15 or sum(f["size"] for f in manifest["files"]) > 40_000_000:
        raise ValueError("Chronology acquisition exceeds declared count/byte budget")
    args.out.mkdir(parents=True, exist_ok=True)
    raw = Path("data/stanford/raw")
    raw.mkdir(parents=True, exist_ok=True)
    reports, downloads, error = [], [], None
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, stop_for_timeout)
    signal.setitimer(signal.ITIMER_REAL, 600)
    try:
        for entry in manifest["files"]:
            filename = entry["filename"]
            if Path(filename).name != filename:
                raise ValueError("Expected a plain source filename")
            path = raw / filename
            cached = path.exists()
            if cached:
                content = path.read_bytes()
            else:
                if not args.fetch:
                    raise FileNotFoundError(f"Missing {filename}; use --fetch for declared source")
                request = urllib.request.Request(
                    entry["content_details"]["download_url"],
                    headers={"User-Agent": "PhysicalFPVResearch/0.1"},
                )
                remaining = 600 - (time.monotonic() - started)
                with urllib.request.urlopen(
                    request, timeout=min(60, max(1, remaining))
                ) as response:
                    content = response.read(entry["size"] + 1)
            integrity = validate_workbook_bytes(content, entry)
            if not cached:
                temporary = path.with_suffix(".xlsx.tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
            downloads.append({**integrity, "already_cached": cached})
            report, _ = inspect_workbook(raw, entry, manifest)
            reports.append(report)
            (args.out / (path.stem + ".json")).write_text(
                json.dumps(report, indent=2, allow_nan=False) + "\n"
            )
            print(
                json.dumps(
                    {
                        "filename": filename,
                        "rows": report["measurement_rows"],
                        "completed_files": len(reports),
                        "elapsed_s": round(time.monotonic() - started, 3),
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    summary = summarize_chronology(reports, manifest)
    summary.update(
        {
            "protocol_sha256": PROTOCOL_SHA256,
            "manifest_sha256": MANIFEST_SHA256,
            "elapsed_s": time.monotonic() - started,
            "error": error,
            "verified_acquisitions": downloads,
            "newly_downloaded_bytes": sum(d["bytes"] for d in downloads if not d["already_cached"]),
        }
    )
    (args.out / "chronology.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    write_evidence_attribution(args.out, ["stanford2021"])
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "inspected_files",
                    "complete",
                    "recorded_order_qualified",
                    "provisional_earlier_files",
                    "provisional_earlier_high_rate_files",
                    "error",
                )
            }
        )
    )
    if error or not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
