"""First-discharge parsing of the attributed TEC/ORegan public thermal cohort."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from physical_fpv.data import Discharge

ARCHIVE_URL = (
    "https://zenodo.org/records/4864437/files/brosaplanella/TEC-reduced-model-v1.0.zip?download=1"
)
ARCHIVE_SHA256 = "3848d0eb1d70e4fc86cc77c272433053760b0bdfe25825ef652135edc43275b8"
ARCHIVE_MD5 = "f9306803d4a2e2a5e27ad9b43596fa12"
COHORT = {0.5: (785, 786, 787, 788), 1.0: (789, 790, 791, 792), 2.0: (793, 794, 795, 796)}


@dataclass(frozen=True)
class ThermalTrace:
    discharge: Discharge
    nominal_temperature_c: int
    initial_temperature_k: float
    initial_rest_voltage_v: float
    measured_energy_wh: float
    accumulator_energy_wh: float
    duplicate_count: int
    changed_duplicate_count: int
    original_discharge_rows: int
    changed_duplicate_fields: list[str]
    quality_flags: list[str]
    source_file: str
    initial_temperature_source: str
    ambient_sensor_status: str
    split: str


def verify_archive(content: bytes) -> str:
    sha = hashlib.sha256(content).hexdigest()
    if sha != ARCHIVE_SHA256:
        raise ValueError("Thermal archive SHA256 mismatch; refusing to parse")
    return sha


def fetch_thermal_data(path: Path) -> dict:
    if path.exists():
        content = path.read_bytes()
    else:
        request = urllib.request.Request(
            ARCHIVE_URL, headers={"User-Agent": "PhysicalFPVResearch/0.1"}
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            content = response.read(24_000_001)
        if len(content) > 24_000_000:
            raise ValueError("Unexpected thermal archive size")
    sha = verify_archive(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temp = path.with_suffix(".zip.tmp")
        temp.write_bytes(content)
        os.replace(temp, path)
    return {
        "url": ARCHIVE_URL,
        "sha256": sha,
        "bytes": len(content),
        "doi": "10.5281/zenodo.4864437",
        "license": "BSD-3-Clause (archive LICENSE)",
        "copyright": "Copyright (c) 2020, Ferran Brosa Planella",
    }


def parse_thermal_trace(
    content: bytes, cell: int, c_rate: float, temperature_c: int, source_file: str
) -> ThermalTrace:
    lines = content.decode("utf-8-sig").splitlines()
    header = [i for i, line in enumerate(lines) if line.startswith("Step,Status,Step Time,")]
    if len(header) != 1:
        raise ValueError("Missing thermal CSV header")
    reader = csv.DictReader(io.StringIO("\n".join(lines[header[0] :])))
    next(reader)  # Explicit raw units row, not a measurement.
    fields = reader.fieldnames or []
    required = {"Step Time", "Voltage", "Current", "AhAccu", "WhAccu", "Status", "Step"}
    if not required.issubset(fields):
        raise ValueError("Thermal measurement columns missing")
    if "LogTempMid" in fields:
        temperature_column = "LogTempMid"
        ambient_column = "LogTemp001" if "LogTemp001" in fields else None
    else:
        temperature_column = "LogTemp001"
        ambient_column = "LogTemp002" if "LogTemp002" in fields else None
    if temperature_column not in fields:
        raise ValueError("Cell temperature measurement missing")
    selected = []
    previous_zero = None
    for row in reader:
        if row["Status"] == "DCH":
            selected.append(row)
        elif selected:
            break  # First contiguous discharge only, never select a better later cycle.
        elif abs(float(row["Current"])) < 0.01:
            previous_zero = row
    if len(selected) < 10 or previous_zero is None:
        raise ValueError("Complete first discharge and its pre-discharge state are required")
    keys = ["Step Time", "Current", "Voltage", temperature_column, "AhAccu", "WhAccu"]
    if ambient_column:
        keys.append(ambient_column)
    values = np.array([[float(row[k]) for k in keys] for row in selected])
    if not np.isfinite(values).all() or np.any(np.diff(values[:, 0]) < 0):
        raise ValueError("Non-finite measurement or reversed discharge time")
    duplicates = 0
    changed = 0
    conflict_fields = set()
    dedup = []
    for row in values:
        if dedup and row[0] == dedup[-1][0]:
            duplicates += 1
            changed += int(not np.array_equal(row, dedup[-1]))
            conflict_fields.update(
                key
                for key, before, after in zip(keys, dedup[-1], row, strict=True)
                if before != after
            )
            dedup[-1] = row
        else:
            dedup.append(row)
    array = np.array(dedup)
    time, signed_current, voltage, temperature, ah, wh = array[:, :6].T
    current = -signed_current
    if not np.all(np.abs(current - c_rate * 5) < 0.1):
        raise ValueError("Not the declared constant-current first discharge")
    if time[0] > 0.1 or not 2.48 <= voltage[-1] <= 2.52 or time[-1] < 1000:
        raise ValueError("Incomplete first discharge or missing 2.5V endpoint")
    initial_temperature = float(previous_zero[temperature_column]) + 273.15
    flags = []
    if cell == 791:
        flags.append(
            "source excluded cell791; temperature anomaly retained; sensor/cell cause unverified"
        )
    if np.any((temperature < -10) | (temperature > 80)):
        flags.append("surface temperature outside broad measurement plausibility range")
    if abs(initial_temperature - (temperature_c + 273.15)) > 3:
        flags.append("pre-discharge temperature differs from nominal ambient by more than3K")
    ambient_status = "absent; nominal ambient used"
    chamber = np.full(len(time), temperature_c + 273.15)
    if ambient_column:
        ambient = array[:, 6]
        if np.all(ambient == 0) and temperature_c != 0:
            ambient_status = "constant-zero placeholder; nominal ambient used"
            flags.append(ambient_status)
        else:
            ambient_status = f"{ambient_column} recorded for diagnostics; nominal ambient used"
            chamber = ambient + 273.15
    energy = float(
        (np.trapezoid(current * voltage, time) + time[0] * current[0] * voltage[0]) / 3600
    )
    data = Discharge(
        str(cell),
        int(selected[0]["Step"]),
        c_rate * 5,
        time,
        current,
        voltage,
        temperature + 273.15,
        chamber,
        float(ah[0] - ah[-1]),
        hashlib.sha256(content).hexdigest(),
    )
    position = COHORT[c_rate].index(cell)
    split = (
        "development"
        if position == 0
        else ("implementation_check" if position == 1 else "reserved_reproduction_check")
    )
    return ThermalTrace(
        data,
        temperature_c,
        initial_temperature,
        float(previous_zero["Voltage"]),
        energy,
        float(wh[0] - wh[-1]),
        duplicates,
        changed,
        len(values),
        sorted(conflict_fields),
        flags,
        source_file,
        f"last zero-current {previous_zero['Status']} / {temperature_column}",
        ambient_status,
        split,
    )


def load_thermal_cohort(archive_path: Path) -> list[ThermalTrace]:
    content = archive_path.read_bytes()
    verify_archive(content)
    traces = []
    # Read only named CSVs; never extract paths or execute archive software.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        for temperature in (0, 10, 25):
            for c_rate, cells in COHORT.items():
                rate = f"{c_rate:g}".replace(".", "p")
                for cell in cells:
                    suffix = f"/data/{temperature}degC/Cell{cell}_{rate}C_{temperature}degC.csv"
                    matches = [name for name in names if name.endswith(suffix)]
                    if len(matches) != 1:
                        raise ValueError(f"Missing or ambiguous cohort file: {suffix}")
                    if archive.getinfo(matches[0]).file_size > 10_000_000:
                        raise ValueError("Unexpected decompressed CSV size")
                    traces.append(
                        parse_thermal_trace(
                            archive.read(matches[0]), cell, c_rate, temperature, matches[0]
                        )
                    )
    return traces


def inspect_cohort(traces: list[ThermalTrace]) -> dict:
    return {
        "files": len(traces),
        "unique_cells": len({t.discharge.cell for t in traces}),
        "duplicate_records": sum(t.duplicate_count for t in traces),
        "changed_duplicate_records": sum(t.changed_duplicate_count for t in traces),
        "cases": [
            {
                "cell": t.discharge.cell,
                "temperature_c": t.nominal_temperature_c,
                "c_rate": t.discharge.nominal_current_a / 5,
                "source": t.source_file,
                "sha256": t.discharge.source_sha256,
                "initial_temperature_k": t.initial_temperature_k,
                "surface_temperature_range_k": [
                    float(t.discharge.temperature_k.min()),
                    float(t.discharge.temperature_k.max()),
                ],
                "capacity_ah": t.discharge.measured_capacity_ah,
                "energy_wh": t.measured_energy_wh,
                "capacity_accumulator_error_ah": abs(
                    t.discharge.measured_capacity_ah - t.discharge.reported_capacity_ah
                ),
                "energy_accumulator_error_wh": abs(t.measured_energy_wh - t.accumulator_energy_wh),
                "duplicates": t.duplicate_count,
                "original_discharge_rows": t.original_discharge_rows,
                "normalized_discharge_rows": len(t.discharge.time_s),
                "changed_duplicate_fields": t.changed_duplicate_fields,
                "duplicate_policy": "keep last, first constant-current DCH block only",
                "quality_flags": t.quality_flags,
                "ambient_sensor": t.ambient_sensor_status,
            }
            for t in traces
        ],
    }


def save_cohort_inspection(archive: Path, output: Path) -> dict:
    report = inspect_cohort(load_thermal_cohort(archive))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
