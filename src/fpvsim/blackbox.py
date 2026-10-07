"""Virtual Blackbox: the flight log.

Like a Betaflight Blackbox log it records what the flight controller saw and
did (sticks, setpoint, raw and filtered gyro, P/I/D/F terms, motor outputs,
motor rpm telemetry, battery voltage and current). Because this is a
simulation it also records the true state, the physical motor and rotor
values, and model-validity monitors, so a log can explain *why* a flight went
wrong, not only *that* it did.

CSV columns use the "name [unit]" header convention of sysid.read_csv. PID
terms are in Betaflight's PID-sum scale (1000 = full motor range).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import units


@dataclass
class FlightLog:
    rate: float  # Hz
    columns: dict[str, list[float]] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def define(self, name: str, unit: str) -> None:
        if not units.is_known(unit):
            raise ValueError(f"unknown unit {unit!r} for log column {name!r}")
        self.columns[name] = []
        self.units[name] = unit

    def append(self, row: dict[str, float]) -> None:
        for name, value in row.items():
            self.columns[name].append(value)

    def __getitem__(self, name: str) -> np.ndarray:
        return np.asarray(self.columns[name], dtype=float)

    def __contains__(self, name: str) -> bool:
        return name in self.columns

    def si(self, name: str) -> np.ndarray:
        unit = self.units[name]
        return np.array([units.to_si(v, unit) for v in self.columns[name]])

    def __len__(self) -> int:
        return len(next(iter(self.columns.values()), []))

    @property
    def time(self) -> np.ndarray:
        return self["time"]

    def write_csv(self, path: Path) -> None:
        names = list(self.columns)
        with path.open("w", newline="") as f:
            f.write("# fpvsim flight log; meta: " + json.dumps(self.meta, ensure_ascii=False) + "\n")
            writer = csv.writer(f)
            writer.writerow([f"{n} [{self.units[n]}]" for n in names])
            for row in zip(*(self.columns[n] for n in names)):
                writer.writerow([f"{v:.6g}" for v in row])

    @classmethod
    def read_csv(cls, path: Path) -> "FlightLog":
        with Path(path).open(newline="") as f:
            first = f.readline()
            meta = json.loads(first.split("meta: ", 1)[1]) if first.startswith("#") else {}
            if not first.startswith("#"):
                f.seek(0)
            reader = csv.reader(f)
            header = next(reader)
            rows = [list(map(float, r)) for r in reader if r]
        log = cls(rate=float(meta.get("log_rate_hz", 0.0)), meta=meta)
        data = np.array(rows).T
        for i, cell in enumerate(header):
            name, unit = cell.rsplit(" [", 1)
            log.columns[name] = data[i].tolist()
            log.units[name] = unit.rstrip("]")
        if not log.rate and len(log) > 1:
            log.rate = 1.0 / float(np.median(np.diff(log["time"])))
        return log
