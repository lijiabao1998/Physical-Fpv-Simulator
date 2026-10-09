"""Scope evaluator changes on committed k2 knots/output times without a solve."""

import csv
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np

from physical_fpv.stanford_k2 import _profile


def audit(root=Path(".")):
    source = root / "docs/benchmarks/stanford-k2-rest-records.csv.gz"
    if (
        hashlib.sha256(source.read_bytes()).hexdigest()
        != "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"
    ):
        raise ValueError("Committed source rows changed")
    rows = list(csv.reader(io.StringIO(gzip.decompress(source.read_bytes()).decode())))[1:]
    discharge = np.array([[float(x) for x in row[2:]] for row in rows if float(row[4]) == 5])
    observed = np.column_stack(
        (discharge[:, 1], discharge[:, 4], discharge[:, 3], discharge[:, 5] + 273.15)
    )
    profile = _profile(observed)
    archive = root / "docs/benchmarks/stanford-k2-recovery-evidence.zip"
    if (
        hashlib.sha256(archive.read_bytes()).hexdigest()
        != "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
    ):
        raise ValueError("Historical arrays changed")
    with zipfile.ZipFile(archive) as zipped:
        inputs = json.loads(zipped.read("stanford-k2-recovery/input.json"))
        with np.load(io.BytesIO(zipped.read("stanford-k2-recovery/mesh120-arrays.npz"))) as saved:
            output_times = saved["time_s"].copy()
    if profile.fingerprint_sha256 != inputs["assumptions"]["current_profile_sha256"]:
        raise ValueError("Knot/content identity changed")
    knots, currents = profile.time_s, profile.current_a
    near = np.r_[np.nextafter(knots[1:-1], -np.inf), np.nextafter(knots[1:-1], np.inf)]
    results = {}
    for name, queries in {
        "source_and_assumption_knots": knots,
        "historical_mesh120_output_times": output_times,
        "adjacent_representable_internal_knot_times": near,
    }.items():
        index = np.minimum(np.searchsorted(knots, queries, side="right") - 1, len(knots) - 2)
        fraction = (queries - knots[index]) / (knots[index + 1] - knots[index])
        old = (1 - fraction) * currents[index] + fraction * currents[index + 1]
        new = profile.value_at(queries)
        difference = abs(new - old)
        results[name] = {
            "query_count": len(queries),
            "changed_values": int(np.count_nonzero(difference)),
            "max_absolute_difference_a": float(max(difference)),
            "max_relative_difference": float(max(difference / old)),
        }
    return {
        "source_record_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "historical_evidence_zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "historical_current_profile_source_sha256": inputs["source_sha256"][
            "src/physical_fpv/current_profile.py"
        ],
        "current_profile_source_sha256": hashlib.sha256(
            (root / "src/physical_fpv/current_profile.py").read_bytes()
        ).hexdigest(),
        "content_profile_sha256": profile.fingerprint_sha256,
        "k2_current_range_a": [profile.min_current_a, profile.max_current_a],
        "comparisons": results,
        "new_solver_runs": 0,
        "new_datasets": 0,
        "new_implementation_voltage_validation_established": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
