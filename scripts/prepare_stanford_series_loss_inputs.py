"""Normalize authenticated archived trajectories; no new feasibility calculation."""

import csv
import gzip
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import openpyxl

from physical_fpv.stanford_data import HEADERS, inspect_records

ROOT = Path(__file__).resolve().parents[1]
K1_OUTPUT = "6c6e0c101e24266fe39b367b294751e06c0676fc59043303dbadfef8f0406ae8"
K1_INPUT = "c777b934ed13ed02aac194c045e7582b8032820e2706867517aa92911d2477a9"
K1_RAW = "b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6"
K2_OUTPUT = "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
K2_RECORDS = "513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError(f"Archived input identity changed: {path.name}")
    return data


def csv_array(data):
    return np.genfromtxt(io.BytesIO(data), delimiter=",", names=True)


def original_k1_rows():
    archive_bytes = verified(
        ROOT / "results/current-source-replay-receipts/current-source-k1-inputs-37887926852.zip",
        K1_INPUT,
    )
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        content = archive.read("files/data/stanford/raw/NMC_k1_1C_25degC.xlsx")
    if sha(content) != K1_RAW or not openpyxl.DEFUSEDXML:
        raise ValueError("k1 original identity/XML protection changed")
    workbook = openpyxl.load_workbook(
        io.BytesIO(content), read_only=True, data_only=True, keep_links=False
    )
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Expected one source sheet")
        stream = workbook.active.iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Source header mismatch")
        return list(stream)
    finally:
        workbook.close()


def original_k2_rows():
    content = verified(ROOT / "docs/benchmarks/stanford-k2-rest-records.csv.gz", K2_RECORDS)
    rows = csv.DictReader(io.StringIO(gzip.decompress(content).decode()))
    return [
        tuple([datetime.fromisoformat(r["Date_Time"]), *[float(r[k]) for k in HEADERS[1:]]])
        for r in rows
    ]


def normalize(name, archive_path, archive_sha, prefix, rows, source_commit, expected_rmse):
    inspection, observed = inspect_records(rows)
    if not inspection["canonical_six_step_sequence"] or observed is None:
        raise ValueError("Qualified source phase sequence missing")
    if any(
        s["exact_duplicate_times"] or s["backwards_step_clock_intervals"]
        for s in inspection["contiguous_steps"]
    ):
        raise ValueError("Ambiguous source clock")
    elapsed_dates = np.array([(r[0] - rows[0][0]).total_seconds() for r in rows])
    elapsed_clock = np.array([r[1] - rows[0][1] for r in rows])
    discrepancy = float(np.max(np.abs(elapsed_dates - elapsed_clock)))
    if np.any(np.diff(elapsed_dates) <= 0) or discrepancy > 1:
        raise ValueError("Source date/test clock identity failed")
    if any(
        s["clock_relation_max_deviation_s"] > 0.01 or s["negative_step_clock_records"]
        for s in inspection["contiguous_steps"]
    ):
        raise ValueError("Source step origin is inconsistent")
    if any(
        s["current_a"]["min"] != 0 or s["current_a"]["max"] != 0
        for s in inspection["contiguous_steps"]
        if s["step"] in (1, 4, 6)
    ):
        raise ValueError("Expected recorded zero-current rest")
    inspection["measurement_clock_audit"] = {
        "max_relative_date_test_discrepancy_s": discrepancy,
        "strictly_increasing_dates": True,
        "timezone": "Unspecified source naive-local timestamps; no conversion",
    }
    archive_bytes = verified(archive_path, archive_sha)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        raw = {
            key: archive.read(prefix + key)
            for key in [
                "mesh120-timeseries.csv",
                "mesh120-residuals.csv",
                "forcing.csv",
                "input.json",
            ]
        }
        if name == "k1":
            exported = csv_array(archive.read("source-inspection/observed-discharge.csv"))
            exported_matrix = np.column_stack([exported[k] for k in exported.dtype.names])
            if not np.array_equal(exported_matrix, observed):
                raise ValueError("k1 exported observations differ from original workbook")
    model, recorded, forcing = [
        csv_array(raw[key])
        for key in ["mesh120-timeseries.csv", "mesh120-residuals.csv", "forcing.csv"]
    ]
    for trace in (model, recorded, forcing):
        if np.any(np.diff(trace["time_s"]) <= 0):
            raise ValueError("Archive clock is not strictly increasing")
    if np.any(observed[:, 1] >= 0):
        raise ValueError("Expected original negative discharge current")
    start, end = float(observed[0, 0]), min(float(observed[-1, 0]), float(model["time_s"][-1]))
    knots = np.unique(
        np.r_[
            start,
            end,
            *[
                t[(t > start) & (t < end)]
                for t in (model["time_s"], observed[:, 0], forcing["time_s"])
            ],
        ]
    )
    current = -np.interp(knots, observed[:, 0], observed[:, 1])
    used_current = np.interp(knots, forcing["time_s"], forcing["positive_discharge_current_a"])
    if not np.allclose(current, used_current, rtol=0, atol=1e-12):
        raise ValueError("Archived forcing differs from measured current")
    error = np.interp(knots, model["time_s"], model["voltage_v"]) - np.interp(
        knots, observed[:, 0], observed[:, 2]
    )
    if recorded["time_s"][0] != start or recorded["time_s"][-1] != end:
        raise ValueError("Original common interval changed")
    if not np.allclose(
        error, np.interp(knots, recorded["time_s"], recorded["voltage_error_v"]), rtol=0, atol=1e-12
    ):
        raise ValueError("Reconstructed residual differs from recorded comparison")
    dt = np.diff(knots)
    mse = float(
        np.sum(dt * (error[:-1] ** 2 + error[:-1] * error[1:] + error[1:] ** 2) / 3) / (end - start)
    )
    if abs(np.sqrt(mse) - expected_rmse) > 1e-12:
        raise ValueError("Published zero-correction RMSE does not reproduce")
    archived_input = json.loads(raw["input.json"])
    return {
        "time_s": knots.tolist(),
        "model_minus_observed_v": error.tolist(),
        "positive_observed_discharge_current_a": current.tolist(),
        "source_inspection": inspection,
        "provenance": {
            "archive_sha256": archive_sha,
            "source_commit": source_commit,
            "members_sha256": {k: sha(v) for k, v in raw.items()},
            "source_workbook_sha256": K1_RAW
            if name == "k1"
            else "20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086",
            "historical_evidence_only": name == "k2",
        },
        "conditioning": {
            "base_config_metadata": archived_input["config"],
            "evaluated_mesh_points": 120,
            "initial_concentrations_mol_m3": archived_input["initial_concentrations_mol_m3"],
            "assumptions": archived_input["assumptions"],
        },
        "observed_interval_s": [float(observed[0, 0]), float(observed[-1, 0])],
        "common_interval_s": [start, end],
        "original_model_event_s": float(model["time_s"][-1]),
        "observed_tail_beyond_model_s": float(observed[-1, 0] - end),
        "common_observed_duration_fraction": (end - start) / (observed[-1, 0] - start),
        "published_baseline_rmse_v": expected_rmse,
        "reproduced_baseline_rmse_v": float(np.sqrt(mse)),
        "voltage_correction_or_physical_parameter_update": False,
    }


def main():
    cells = {
        "k1": normalize(
            "k1",
            ROOT / "results/current-source-replay-receipts/"
            "current-source-k1-evidence-37887926852.zip",
            K1_OUTPUT,
            "current-source-replay/k1/",
            original_k1_rows(),
            "744794b02d44bcbfc702ad8e5c403782128d11b0",
            0.1914735217065252,
        ),
        "k2": normalize(
            "k2",
            ROOT / "docs/benchmarks/stanford-k2-recovery-evidence.zip",
            K2_OUTPUT,
            "stanford-k2-recovery/",
            original_k2_rows(),
            "50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84",
            0.0550030541916,
        ),
    }
    artifact = {
        "format": "fixed-trajectory-series-loss-input-v1",
        "cells": cells,
        "source_attribution": "Catenaro and Onori, DOI10.17632/kxsbr4x3j2.2, CC BY4.0",
        "normalizer_sha256": sha(Path(__file__).read_bytes()),
    }
    data = (json.dumps(artifact, separators=(",", ":")) + "\n").encode()
    path = ROOT / "docs/benchmarks/stanford-series-loss-inputs.json.gz"
    path.write_bytes(gzip.compress(data, mtime=0))
    print(
        json.dumps(
            {
                "path": str(path),
                "compressed_bytes": path.stat().st_size,
                "gzip_sha256": sha(path.read_bytes()),
                "json_sha256": sha(data),
                "knots": {k: len(c["time_s"]) for k, c in cells.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
