import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from physical_fpv.stanford_data import (
    fetch_pilot,
    inspect_pilot,
    inspect_records,
    inspect_workbook,
    validate_workbook_bytes,
)


def records():
    rows = []
    origin = datetime(2019, 9, 2)
    for step in range(1, 7):
        for local in (1.0006, 2.0006):
            time = step * 10 + local
            current = -5.0 if step == 5 else 1.625 if step in (2, 3) else 0.0
            rows.append((origin + timedelta(seconds=time), time, local, step, 4.0, current, 25.0))
    return rows


def test_missing_start_interval_is_preserved_not_zero_aligned():
    report, discharge = inspect_records(records())
    assert report["canonical_six_step_sequence"]
    assert discharge[0, 0] == 1.0006
    assert report["discharge"]["unobserved_initial_interval_s"] == 1.0006
    assert report["discharge"]["observed_discharge_charge_ah"] == pytest.approx(5 / 3600)
    assert report["discharge"][
        "protocol_inferred_initial_charge_if_constant_current_ah"
    ] == pytest.approx(5 * 1.0006 / 3600)
    assert np.all(discharge[:, 1] == -5)
    assert np.all(discharge[:, 3] == 298.15)
    assert report["model_runs"] == 0
    assert not report["independent_validation_established"]


def test_repeated_discharge_blocks_are_not_silently_selected():
    source = records()
    source += [(r[0] + timedelta(seconds=100), r[1] + 100, *r[2:]) for r in records()]
    report, discharge = inspect_records(source)
    assert not report["canonical_six_step_sequence"]
    assert discharge is None
    assert len(report["contiguous_steps"]) == 12


def test_conflicting_same_time_records_remain_visible():
    source = records()
    row = list(source[8])
    row[4] = 3.9
    source.insert(9, tuple(row))
    report, discharge = inspect_records(source)
    d = next(s for s in report["contiguous_steps"] if s["step"] == 5)
    assert d["exact_duplicate_times"] == 1
    assert d["duplicate_time_conflicts"] == 1
    assert len(discharge) == 3


def test_reversed_or_negative_step_clock_is_flagged_without_repair():
    source = records()
    row = list(source[9])
    row[2] = -1.0
    source[9] = tuple(row)
    report, discharge = inspect_records(source)
    d = next(s for s in report["contiguous_steps"] if s["step"] == 5)
    assert d["backwards_step_clock_intervals"] == 1
    assert d["negative_step_clock_records"] == 1
    assert discharge[1, 0] == -1.0


@pytest.mark.parametrize("change", ["clock", "nonfinite", "date"])
def test_invalid_source_semantics_are_rejected(change):
    source = records()
    row = list(source[3])
    if change == "clock":
        row[1] = 0
    elif change == "nonfinite":
        row[5] = float("nan")
    else:
        row[0] = 44000.0
    source[3] = tuple(row)
    with pytest.raises(ValueError):
        inspect_records(source)


def test_checksum_and_active_workbook_content_fail_closed():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("xl/vbaProject.bin", b"nonexecutable test marker")
    content = payload.getvalue()
    entry = {
        "filename": "test.xlsx",
        "size": len(content),
        "content_details": {"sha256_hash": hashlib.sha256(content).hexdigest()},
    }
    with pytest.raises(ValueError, match="macro"):
        validate_workbook_bytes(content, entry)
    with pytest.raises(ValueError, match="SHA256"):
        validate_workbook_bytes(content + b"changed", entry)


def test_transfer_budget_is_checked_before_any_network_access(tmp_path):
    entry = {"filename": "large.xlsx", "size": 2_000_000}
    with pytest.raises(ValueError, match="budget"):
        fetch_pilot({"files": [entry], "manufacturer_specification": {"size": 1}}, tmp_path)


def test_workbook_wall_clock_reversal_is_reported_even_when_test_clock_increases(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from physical_fpv.stanford_data import HEADERS

    source = records()
    row = list(source[1])
    row[0] = source[0][0] - timedelta(seconds=3)
    source[1] = tuple(row)
    path = tmp_path / "synthetic-clock-test.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(HEADERS)
    for row in source:
        workbook.active.append(row)
    workbook.save(path)
    workbook.close()
    entry = {
        "filename": path.name,
        "size": path.stat().st_size,
        "content_details": {"sha256_hash": hashlib.sha256(path.read_bytes()).hexdigest()},
    }
    metadata = {
        k: "synthetic test" for k in ("dataset_doi", "dataset_url", "license_url", "license")
    }
    metadata["authors"] = []
    report, _ = inspect_workbook(tmp_path, entry, metadata)
    audit = report["measurement_clock_audit"]
    assert audit["backwards_date_intervals"] == 1
    assert audit["first_backwards_date_excel_row_pairs"] == [[2, 3]]
    assert audit["max_relative_date_test_clock_discrepancy_s"] == pytest.approx(4)
    assert audit["date_test_clock_jumps_above_1s"] == 2


@pytest.mark.data
def test_real_pilot_has_six_steps_verified_sha_and_command_clock():
    pytest.importorskip("openpyxl")
    raw = Path("data/stanford/raw")
    if not (raw / "NMC_k1_1C_25degC.xlsx").exists():
        pytest.skip("Run python scripts/inspect_stanford_pilot.py --fetch")
    report, discharge = inspect_pilot(
        raw, json.loads(Path("data/stanford-manifest.json").read_text())
    )
    assert report["measurement_rows"] == 28669
    assert report["canonical_six_step_sequence"]
    assert len(discharge) == 3391
    assert report["discharge"]["recorded_current_a"] == pytest.approx(-5.000325, abs=1e-6)
    assert discharge[0, 0] == 1.0006
    assert discharge[-1, 0] == 3390.3968
    assert all(s["exact_duplicate_times"] == 0 for s in report["contiguous_steps"])
