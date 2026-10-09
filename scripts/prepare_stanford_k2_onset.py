"""Preserve exact rest/onset support from the checksum-pinned cached low-rate file."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import openpyxl

from physical_fpv.onset_response import qualify_phase
from physical_fpv.stanford_data import HEADERS, inspect_workbook

ROOT = Path(__file__).resolve().parents[1]
FILENAME = "NMC_k2_0_05C_25degC.xlsx"


def prepare(raw_dir, out):
    manifest = json.loads((ROOT / "data/stanford-k2-k6-history-manifest.json").read_text())
    entry = next(e for e in manifest["files"] if e["filename"] == FILENAME)
    inspection, _ = inspect_workbook(raw_dir, entry, manifest)
    if not inspection["canonical_six_step_sequence"]:
        raise ValueError("Noncanonical phase sequence")
    workbook = openpyxl.load_workbook(
        raw_dir / FILENAME, read_only=True, data_only=True, keep_links=False
    )
    stream = workbook.worksheets[0].iter_rows(values_only=True)
    assert tuple(next(stream)) == HEADERS
    rows = list(enumerate(stream, start=2))
    workbook.close()
    rest = qualify_phase(rows, 4)
    discharge = qualify_phase(rows, 5)
    last = next(i for i, (_, r) in enumerate(discharge) if r[2] >= 10)
    chosen = rest + discharge[: last + 1]
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["excel_row", *HEADERS])
    for index, row in chosen:
        writer.writerow([index, row[0].isoformat(), *row[1:]])
    raw = text.getvalue().encode()
    packed = gzip.compress(raw, mtime=0)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "stanford-k2-low-rate-onset-records.csv.gz"
    path.write_bytes(packed)
    report = {
        "original_source": inspection["source"],
        "dataset_doi": manifest["dataset_doi"],
        "license": manifest["license"],
        "authors": manifest["authors"],
        "source_inspection": inspection,
        "qualified_phase_rows": {"rest": len(rest), "discharge": len(discharge)},
        "persisted_phase_rows": {"rest": len(rest), "discharge": last + 1},
        "selection": (
            "Every rest row and initial discharge through first sample at/after10s; "
            "all source phases4/5 qualified before slicing"
        ),
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_sha256": hashlib.sha256(packed).hexdigest(),
        "gzip_bytes": len(packed),
        "normalizer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "stanford-k2-onset-source.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = prepare(args.raw_dir, args.out)
    print(json.dumps({k: v for k, v in r.items() if k != "source_inspection"}, indent=2))
