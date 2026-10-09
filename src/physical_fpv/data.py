"""Checksum-pinned, attributed real-cell data. Never execute downloaded content."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from physical_fpv.attribution import write_evidence_attribution

RECORD = "https://zenodo.org/records/4032561"
DOI = "10.5281/zenodo.4032561"
LICENSE = "CC-BY-4.0"
CHECKSUMS = {
    "02": "0bbf959cbfc367296ec69d7a74d2f5c1",
    "03": "a09cbd8eff0af55dfe9bc8728fa89908",
    "04": "f17615476283d2e15087165697ff9d7c",
}
SHA256 = {
    "02": "650e7f9ac5217b4db158047e50b6b464100b13f4859002421114edebca629b35",
    "03": "fcc13423786d6044f3ec41b1b278fb1d42ff55018666be743243f7c34b1b98cb",
    "04": "e1cbb60e79911824d5559f12db8e8ecdd4781d077a45f5b1ecbcf103aa271d9e",
}
STEPS = {7: 0.5, 12: 2.5, 17: 5.0, 22: 7.5}
COLUMNS = (
    "Step",
    "Step Time [s]",
    "Capacity [Ah]",
    "Current [A]",
    "Voltage [V]",
    "Md",
    "Temperature Cell [degC]",
    "Temperature Chamber [degC]",
)


@dataclass(frozen=True)
class Discharge:
    cell: str
    step: int
    nominal_current_a: float
    time_s: np.ndarray
    current_a: np.ndarray
    voltage_v: np.ndarray
    temperature_k: np.ndarray
    chamber_temperature_k: np.ndarray
    reported_capacity_ah: float
    source_sha256: str

    @property
    def measured_capacity_ah(self) -> float:
        # Logging starts ~0.03-0.04 s after the step. Account for that small first interval.
        return float(
            (np.trapezoid(self.current_a, self.time_s) + self.time_s[0] * self.current_a[0]) / 3600
        )


def verify_raw(content: bytes, cell: str) -> str:
    if cell not in CHECKSUMS:
        raise ValueError("Only benchmark cells 02, 03 and 04 are supported")
    if hashlib.md5(content, usedforsecurity=False).hexdigest() != CHECKSUMS[cell]:
        raise ValueError(f"Checksum mismatch for cell{cell}; data must not be used")
    sha256 = hashlib.sha256(content).hexdigest()
    if sha256 != SHA256[cell]:
        raise ValueError(f"SHA256 mismatch for cell{cell}; data must not be used")
    return sha256


def download_data(directory: Path) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for cell in CHECKSUMS:
        name = f"LGM50_cell{cell}.csv"
        path = directory / name
        url = f"{RECORD}/files/{name}?download=1"
        if path.exists():
            content = path.read_bytes()
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "PhysicalFPVResearch/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Unexpected file size; refusing download")
        sha = verify_raw(content, cell)
        if not path.exists():
            temporary = path.with_suffix(".csv.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)
        artifacts.append(
            {
                "file": name,
                "source": url,
                "doi": DOI,
                "license": LICENSE,
                "md5": CHECKSUMS[cell],
                "sha256": sha,
            }
        )
    (directory / "download-manifest.json").write_text(
        json.dumps(artifacts, indent=2) + "\n", encoding="utf-8"
    )
    write_evidence_attribution(directory, ["chen2020"])
    return artifacts


def load_discharges(path: Path, cell: str) -> list[Discharge]:
    content = path.read_bytes()
    sha = verify_raw(content, cell)
    lines = content.decode("utf-8-sig").splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith("Rec,Cycle P,")]
    if len(headers) != 1:
        raise ValueError("Missing or ambiguous Maccor data header")
    reader = csv.DictReader(io.StringIO("\n".join(lines[headers[0] :])))
    if not set(COLUMNS).issubset(reader.fieldnames or []):
        raise ValueError("Missing required columns with explicit units")
    rows = list(reader)
    traces = []
    for step, nominal in STEPS.items():
        selected = [r for r in rows if int(r["Step"]) == step and r["Md"] == "D"]
        if len(selected) < 10:
            raise ValueError(f"Missing complete discharge step {step}")
        values = np.array([[float(r[k]) for k in COLUMNS if k != "Md"] for r in selected])
        if not np.isfinite(values).all():
            raise ValueError("Non-finite measurement")
        time, capacity, current, voltage, temp, chamber = values[:, 1:].T
        if np.any(np.diff(time) <= 0) or time[0] < 0:
            raise ValueError("Discharge time must be strictly increasing; no silent deduplication")
        if np.any(np.abs(current - nominal) > 0.05):
            raise ValueError("Discharge is not the expected nominal constant-current protocol")
        if np.any((voltage < 2.45) | (voltage > 4.25)):
            raise ValueError("Measurement voltage out of protocol range")
        if not 2.49 <= voltage[-1] <= 2.51 or time[-1] < 1000:
            raise ValueError("Trace does not reach the expected complete 2.5 V cutoff")
        if np.any((temp < 0) | (temp > 80)) or np.any((chamber < 0) | (chamber > 80)):
            raise ValueError("Temperature unit or range invalid")
        traces.append(
            Discharge(
                cell,
                step,
                nominal,
                time,
                current,
                voltage,
                temp + 273.15,
                chamber + 273.15,
                float(capacity[-1]),
                sha,
            )
        )
    return traces
