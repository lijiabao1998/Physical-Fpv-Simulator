"""Reacquire only the frozen k2 workbook for the explicit October 9 recovery."""

import hashlib
import json
import signal
import urllib.request
from pathlib import Path

from physical_fpv.stanford_data import validate_workbook_bytes

FILENAME = "NMC_k2_1C_25degC.xlsx"
SIZE = 1_802_458
SHA256 = "20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086"
URL = (
    "https://data.mendeley.com/public-files/datasets/kxsbr4x3j2/files/"
    "0c5e4899-e558-4c82-9535-fa8eda79c746/file_downloaded"
)


def select_source(manifest):
    entries = [e for e in manifest["files"] if e["filename"] == FILENAME]
    if len(entries) != 1:
        raise ValueError("Exactly one frozen k2 source is required")
    entry = entries[0]
    if (
        entry["size"] != SIZE
        or entry["content_details"]["sha256_hash"] != SHA256
        or entry["content_details"]["download_url"] != URL
        or manifest["dataset_doi"] != "10.17632/kxsbr4x3j2.2"
        or manifest["license"] != "CC-BY-4.0"
    ):
        raise ValueError("Frozen source identity or license changed")
    return entry


def acquire(root=Path(".")):
    manifest = json.loads((root / "data/stanford-manifest.json").read_text())
    entry = select_source(manifest)
    out = root / "results/stanford-k2-recovery-acquisition"
    out.mkdir(parents=True, exist_ok=True)
    path = root / "data/stanford/raw" / FILENAME
    receipt = {
        "status": "started",
        "source": entry,
        "dataset_doi": manifest["dataset_doi"],
        "authors": manifest["authors"],
        "license": manifest["license"],
        "license_url": manifest["license_url"],
        "original_bytes_unchanged": True,
        "attempted_downloads": 0,
        "k6_downloads": 0,
        "retry_enabled": False,
    }
    receipt_path = out / "receipt.json"

    def save():
        temporary = receipt_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        temporary.replace(receipt_path)

    def expired(signum, frame):
        raise TimeoutError("Recovery acquisition exceeded its 90-second total deadline")

    save()
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 90)
    try:
        if path.exists():
            content = path.read_bytes()
        else:
            receipt["attempted_downloads"] = 1
            save()
            request = urllib.request.Request(URL, headers={"User-Agent": "PhysicalFPVResearch/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read(SIZE + 1)
        receipt["validation"] = validate_workbook_bytes(content, entry)
        receipt["actual_sha256"] = hashlib.sha256(content).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".xlsx.tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
        receipt["status"] = "verified"
    except Exception as exc:
        receipt.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        save()
    return receipt


if __name__ == "__main__":
    print(json.dumps(acquire(), indent=2))
