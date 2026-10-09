"""Acquire and inspect the predeclared external M50 pilot; no model is solved."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import openpyxl

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.stanford_data import (
    PROTOCOL_SHA256,
    fetch_pilot,
    inspect_pilot,
    validate_workbook_bytes,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/stanford-pilot"))
    args = parser.parse_args()
    if (
        hashlib.sha256(Path("docs/stanford-acquisition-protocol.md").read_bytes()).hexdigest()
        != PROTOCOL_SHA256
    ):
        raise ValueError("Acquisition selection protocol changed")
    manifest = json.loads(Path("data/stanford-manifest.json").read_text())
    raw = Path("data/stanford/raw")
    if args.fetch:
        fetch_pilot(manifest, raw)
    report, discharge = inspect_pilot(raw, manifest)
    spec = manifest["manufacturer_specification"]
    validate_workbook_bytes((raw / spec["filename"]).read_bytes(), spec)
    workbook = openpyxl.load_workbook(
        raw / spec["filename"], read_only=True, data_only=True, keep_links=False
    )
    try:
        rows = workbook.active.iter_rows(values_only=True)
        header = next(rows)
        candidates = [dict(zip(header, row, strict=True)) for row in rows if row[1] == "NMC"]
        if len(candidates) != 1 or candidates[0]["ESS_Model_Name"] != "INR21700-M50":
            raise ValueError("Exact-cell manufacturer specification is ambiguous")
        report["manufacturer_specification"] = candidates[0]
    finally:
        workbook.close()
    report["protocol_sha256"] = PROTOCOL_SHA256
    report["specification_source_sha256"] = spec["content_details"]["sha256_hash"]
    args.out.mkdir(parents=True, exist_ok=True)
    if discharge is not None:
        np.savetxt(
            args.out / "observed-discharge.csv",
            discharge,
            delimiter=",",
            comments="",
            header="commanded_step_time_s,raw_signed_current_a,voltage_v,surface_temperature_k",
        )
    write_evidence_attribution(args.out, ["stanford2021"])
    (args.out / "inspection.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "rows": report["measurement_rows"],
                "canonical_six_steps": report["canonical_six_step_sequence"],
                "discharge": report["discharge"],
                "model_runs": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
