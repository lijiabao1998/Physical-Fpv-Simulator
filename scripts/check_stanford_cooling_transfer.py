"""Check frozen k2 decay rates on saved k1; no fitting, download or DFN solve."""

import argparse
import csv
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import openpyxl

from physical_fpv.cooling_characterization import metrics, prediction, window
from physical_fpv.stanford_data import HEADERS, inspect_records, validate_workbook_bytes

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_HASH = "c777b934ed13ed02aac194c045e7582b8032820e2706867517aa92911d2477a9"
WORKBOOK_HASH = "b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6"
FROZEN_HASH = "a240791b72e63a1ac1625fecf9cc29f45bbdef2b6f5b26ec36b6a08cc634a782"
NORMALIZED_HASH = "9fc12883623a0d5fa47d4c13eed9a37edf40965f8fe0e965cc294772c32c1dc9"
MEMBER = "files/data/stanford/raw/NMC_k1_1C_25degC.xlsx"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen(path):
    if digest(path) != FROZEN_HASH:
        raise ValueError("Frozen k2 characterization identity mismatch")
    return json.loads(path.read_text())


def load_source(path):
    if digest(path) != ARCHIVE_HASH:
        raise ValueError("Previously verified archive identity mismatch")
    with zipfile.ZipFile(path) as archive:
        content = archive.read(MEMBER)
    validate_workbook_bytes(
        content,
        {
            "filename": "NMC_k1_1C_25degC.xlsx",
            "size": 1868963,
            "content_details": {"sha256_hash": WORKBOOK_HASH},
        },
    )
    if not openpyxl.DEFUSEDXML:
        raise RuntimeError("Pinned defusedxml support required")
    workbook = openpyxl.load_workbook(
        io.BytesIO(content), read_only=True, data_only=True, keep_links=False
    )
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Expected one measurement sheet")
        stream = workbook.active.iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Source header changed")
        rows = list(stream)
    finally:
        workbook.close()
    inspection, _ = inspect_records(rows)
    if not inspection["canonical_six_step_sequence"]:
        raise ValueError("Expected qualified six-step source")
    for step in inspection["contiguous_steps"]:
        if (
            step["backwards_step_clock_intervals"]
            or step["exact_duplicate_times"]
            or step["negative_step_clock_records"]
            or step["clock_relation_max_deviation_s"] > 0.01
        ):
            raise ValueError("Source step clock failed")
    dates = np.array([(r[0] - rows[0][0]).total_seconds() for r in rows])
    clocks = np.array([r[1] - rows[0][1] for r in rows])
    discrepancy = float(np.max(np.abs(dates - clocks)))
    if np.any(np.diff(dates) <= 0) or discrepancy > 1:
        raise ValueError("Source date/test clock failed")
    inspection["max_date_test_clock_discrepancy_s"] = discrepancy
    rests = {}
    for step in (4, 6):
        selected = [r for r in rows if r[3] == step]
        if not selected or any(r[5] != 0 for r in selected):
            raise ValueError("Cooling/rest baseline requires recorded zero external current")
        rests[step] = (np.array([r[2] for r in selected]), np.array([r[6] for r in selected]))
    return rests, inspection


def load_committed_source(path):
    if digest(path) != NORMALIZED_HASH:
        raise ValueError("Normalized source identity mismatch")
    artifact = json.loads(path.read_text())
    if artifact["source_workbook_sha256"] != WORKBOOK_HASH:
        raise ValueError("Normalized source provenance mismatch")
    rests = {}
    for step in (4, 6):
        record = artifact["rests"][str(step)]
        if record["all_recorded_currents_a"] != 0:
            raise ValueError("Expected zero recorded rest current")
        rests[step] = (np.asarray(record["step_time_s"]), np.asarray(record["skin_c"]))
    return rests, artifact["inspection"]


def transfer_metrics(time_s, skin_c, baseline, rate, prior_rate):
    anchor = float(window(time_s, skin_c, 60, 61)[1][0])
    if not np.isfinite([baseline, rate, prior_rate]).all() or rate <= 0 or prior_rate <= 0:
        raise ValueError("Expected finite positive frozen rates")
    if anchor <= baseline:
        raise ValueError("Cooling screen requires positive initial excess temperature")
    windows = {}
    difference = 0.0
    for name, start, end in [
        ("early_check", 60.0, 600.0),
        ("middle_check", 600.0, 1800.0),
        ("late_check", 1800.0, 3600.0),
    ]:
        windows[name] = {}
        for model, used_rate in [
            ("transferred_decay", rate),
            ("frozen_prior", prior_rate),
            ("persistence", 0.0),
        ]:
            m = metrics(time_s, skin_c, start, end, baseline, anchor, used_rate)
            check = metrics(time_s, skin_c, start, end, baseline, anchor, used_rate, order=32)
            difference = max(difference, abs(m["mse_k2"] - check["mse_k2"]))
            windows[name][model] = m
    if difference > 1e-10:
        raise ValueError("Independent quadrature check failed")
    return {
        "transferred_parameters": {
            "rate_per_s": rate,
            "tau_s": 1 / rate,
            "baseline_c": baseline,
            "anchor_temperature_c": anchor,
            "anchor_time_s": 60.0,
        },
        "k1_fitting_performed": False,
        "windows": windows,
        "quadrature_max_mse_difference_k2": difference,
        "improves_both_comparators_in_all_three_windows": all(
            w["transferred_decay"]["rmse_k"] < w[other]["rmse_k"]
            for w in windows.values()
            for other in ("frozen_prior", "persistence")
        ),
        "physical_parameter_identification": False,
    }


def run(source_path, frozen_path, out, archive_path=None):
    started = time.monotonic()
    frozen = load_frozen(frozen_path)
    rests, inspection = load_committed_source(source_path)
    if archive_path is not None:
        original_rests, original_inspection = load_source(archive_path)
        for step in (4, 6):
            for normalized, original in zip(rests[step], original_rests[step], strict=True):
                if not np.array_equal(normalized, original):
                    raise ValueError("Normalized source differs from original workbook")
        if inspection != original_inspection:
            raise ValueError("Normalized inspection differs from original source")
    t, y = rests[6]
    pt, py = rests[4]
    bt, by = window(pt, py, pt[-1] - 600, pt[-1])
    skin_baseline = float(np.trapezoid(by, bt) / 600)
    cases = {}
    for name, baseline in [("nominal_25c", 25.0), ("preceding_rest_skin_proxy", skin_baseline)]:
        rate = frozen["scenarios"][name]["fit"]["rate_per_s"]
        cases[name] = transfer_metrics(t, y, baseline, rate, frozen["prior"]["rate_per_s"])
    result = {
        "protocol": "docs/stanford-cooling-transfer-protocol.md",
        "source_archive_sha256": ARCHIVE_HASH,
        "normalized_source_sha256": NORMALIZED_HASH,
        "original_workbook_rechecked": archive_path is not None,
        "source_member": MEMBER,
        "source_workbook_sha256": WORKBOOK_HASH,
        "source_workbook_bytes": 1868963,
        "frozen_k2_characterization_sha256": FROZEN_HASH,
        "frozen_k2_commit": "0fb5624e90e670e2e1b21143de84a7d6a1ee13f1",
        "hashes": {
            str(p.relative_to(ROOT)): digest(p)
            for p in [
                Path(__file__),
                source_path,
                ROOT / "docs/stanford-cooling-transfer-protocol.md",
                ROOT / "src/physical_fpv/cooling_characterization.py",
                ROOT / "src/physical_fpv/stanford_data.py",
            ]
        },
        "k1_inspection": inspection,
        "pre_rest_skin_baseline_c": skin_baseline,
        "baseline_interval_s": [float(bt[0]), float(bt[-1])],
        "recorded_post_rest_endpoint_skin_c": [float(y[0]), float(y[-1])],
        "previously_viewed_cell": True,
        "blind_validation": False,
        "cross_cell_check_excluded_from_k2_rate_calibration": True,
        "new_downloads": 0,
        "new_electrochemical_solves": 0,
        "k1_fitting_performed": False,
        "independent_thermal_validation": False,
        "physical_parameter_update": False,
        "source_attribution": "Catenaro and Onori, DOI10.17632/kxsbr4x3j2.2, CC BY4.0",
        "prior": frozen["prior"],
        "scenarios": cases,
    }
    out.mkdir(parents=True, exist_ok=True)
    q = np.unique(np.r_[60, t[(t > 60) & (t < 3600)], 3600])
    columns, names = [q, np.interp(q, t, y)], ["step_time_s", "measured_skin_c"]
    for name, case in cases.items():
        c = case["transferred_parameters"]
        for kind, rate in [("transfer", c["rate_per_s"]), ("prior", frozen["prior"]["rate_per_s"])]:
            columns.append(prediction(q, c["baseline_c"], c["anchor_temperature_c"], rate))
            names.append(name + "_" + kind + "_c")
    csv_path = out / "stanford-k1-cooling-transfer-predictions.csv"
    with csv_path.open("w") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(names)
        writer.writerows(zip(*columns, strict=True))
    result["prediction_csv_sha256"] = digest(csv_path)
    result["elapsed_s"] = time.monotonic() - started
    if result["elapsed_s"] > 60:
        raise ValueError("Exceeded60s analysis budget")
    (out / "stanford-k1-cooling-transfer.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-zip", type=Path, help="Optional original archive identity recheck")
    parser.add_argument(
        "--source", type=Path, default=ROOT / "docs/benchmarks/stanford-k1-cooling-source.json"
    )
    parser.add_argument(
        "--frozen", type=Path, default=ROOT / "docs/benchmarks/stanford-k2-cooling.json"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "docs/benchmarks")
    args = parser.parse_args()
    report = run(args.source, args.frozen, args.out, args.input_zip)
    print(
        json.dumps(
            {
                "elapsed_s": report["elapsed_s"],
                "scenario_improvement": {
                    name: c["improves_both_comparators_in_all_three_windows"]
                    for name, c in report["scenarios"].items()
                },
            },
            indent=2,
        )
    )
