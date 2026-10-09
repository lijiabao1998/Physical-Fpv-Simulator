"""Recover complete rest and loaded support from a verified cached k1 source archive."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

import openpyxl

from physical_fpv.onset_response import qualify_phase
from physical_fpv.stanford_data import HEADERS, inspect_records, validate_workbook_bytes

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = "c777b934ed13ed02aac194c045e7582b8032820e2706867517aa92911d2477a9"
EVIDENCE_SHA = "6c6e0c101e24266fe39b367b294751e06c0676fc59043303dbadfef8f0406ae8"
WORKBOOK_SHA = "b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6"
MEMBER = "files/data/stanford/raw/NMC_k1_1C_25degC.xlsx"


def prepare(input_archive, evidence_archive, out):
    packed = input_archive.read_bytes()
    if hashlib.sha256(packed).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Input archive hash changed")
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        raw = archive.read(MEMBER)
    integrity = validate_workbook_bytes(
        raw,
        {
            "filename": "NMC_k1_1C_25degC.xlsx",
            "size": 1868963,
            "content_details": {"sha256_hash": WORKBOOK_SHA},
        },
    )
    if not openpyxl.DEFUSEDXML:
        raise ValueError("Safe XML parser required")
    workbook = openpyxl.load_workbook(
        io.BytesIO(raw), read_only=True, data_only=True, keep_links=False
    )
    if len(workbook.worksheets) != 1:
        raise ValueError("Unexpected measurement sheet count")
    stream = workbook.worksheets[0].iter_rows(values_only=True)
    if tuple(next(stream)) != HEADERS:
        raise ValueError("Unexpected source schema")
    records = list(stream)
    workbook.close()
    inspection, _ = inspect_records(records)
    if not inspection["canonical_six_step_sequence"]:
        raise ValueError("Noncanonical phases")
    rows = list(enumerate(records, start=2))
    rest = qualify_phase(rows, 4)
    load = qualify_phase(rows, 5)
    selected = rest + load
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["excel_row", *HEADERS])
    for index, row in selected:
        writer.writerow([index, row[0].isoformat(), *row[1:]])
    content = text.getvalue().encode()
    compressed = gzip.compress(content, mtime=0)
    evidence = evidence_archive.read_bytes()
    if hashlib.sha256(evidence).hexdigest() != EVIDENCE_SHA:
        raise ValueError("Evidence archive hash changed")
    with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
        model_input = json.loads(archive.read("current-source-replay/k1/input.json"))
    full_audits = {}
    for name, selected in (("rest", rest), ("discharge", load)):
        initial = selected[0][1]
        origins = [r[1] - r[2] for _, r in selected]
        full_audits[name] = {
            "rows_checked": len(selected),
            "max_relative_date_test_discrepancy_s": max(
                abs((r[0] - initial[0]).total_seconds() - (r[1] - initial[1])) for _, r in selected
            ),
            "max_command_origin_deviation_s": max(abs(v - origins[0]) for v in origins),
            "strictly_increasing_dates_test_and_step_clocks": True,
        }
    report = {
        "source": integrity,
        "input_archive_sha256": ARCHIVE_SHA,
        "evidence_archive_sha256": EVIDENCE_SHA,
        "dataset_doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "source_inspection": inspection,
        "full_phase_clock_audits": full_audits,
        "qualified_phase_rows": {"rest": len(rest), "discharge": len(load)},
        "persisted_phase_rows": {"rest": len(rest), "discharge": len(load)},
        "selection": (
            "All phase4 rest and phase5 discharge rows; every original phase4/5 row qualified"
        ),
        "csv_sha256": hashlib.sha256(content).hexdigest(),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        "gzip_bytes": len(compressed),
        "model_input_receipt": model_input,
        "normalizer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "stanford-k1-discharge-records.csv.gz").write_bytes(compressed)
    (out / "stanford-contrast-persistence-source.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_archive", type=Path)
    parser.add_argument("evidence_archive", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    r = prepare(args.input_archive, args.evidence_archive, args.out)
    print(
        json.dumps(
            {k: v for k, v in r.items() if k not in ("source_inspection", "model_input_receipt")},
            indent=2,
        )
    )
