"""Checked reuse of the completed Stanford mesh80 trace, including its empirical failure.

The recording contains five observables, not the original spatial states or heat
flows. Its original concentration and heat-balance audits are retained as recorded
evidence; only charge integration and lithium conservation can be checked again.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import zlib
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pybamm

from physical_fpv.core import ModelConfig
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.stanford_benchmark import (
    PROTOCOL_SHA256,
    SCHEDULING_ADDENDUM_SHA256,
    SOURCE_SHA256,
)

REFERENCE_INDEX = "docs/benchmarks/stanford-k1-mesh80-reference.json"
SOURCE_COMMIT_SHA = "be1cb751d78ea92ee0486966f3a5e66687797e63"
CI_RUN_ID = 37729197529
ARTIFACT_ZIP_SHA256 = "f644dd2e9436fdff281919a6ae0de5259864b62251cc7e3979dac7a9f699eb89"
MAX_REFERENCE_BYTES = 1_000_000
CSV_HEADER = "time_s,voltage_v,capacity_ah,temperature_k,lithium_inventory_mol"


@dataclass(frozen=True, slots=True)
class RecordedNumericalTrace:
    """The available observables only; this object never represents a new solve."""

    config: ModelConfig
    _columns: tuple[bytes, ...] = field(repr=False)
    _report: dict = field(repr=False)
    _provenance: dict = field(repr=False)

    @property
    def time_s(self) -> np.ndarray:
        return np.frombuffer(self._columns[0], dtype="<f8")

    @property
    def voltage_v(self) -> np.ndarray:
        return np.frombuffer(self._columns[1], dtype="<f8")

    @property
    def capacity_ah(self) -> np.ndarray:
        return np.frombuffer(self._columns[2], dtype="<f8")

    @property
    def temperature_k(self) -> np.ndarray:
        return np.frombuffer(self._columns[3], dtype="<f8")

    @property
    def lithium_mol(self) -> np.ndarray:
        return np.frombuffer(self._columns[4], dtype="<f8")

    @property
    def physical_audit(self) -> dict:
        return deepcopy(self._report["model"]["physical_audit"])

    @property
    def termination(self) -> str:
        return self._report["model"]["termination"]

    @property
    def parameter_fingerprint(self) -> str:
        return self._report["model"]["parameter_fingerprint"]

    @property
    def empirical_report(self) -> dict:
        """Return the original report without recomputing or relabelling its gates."""
        return deepcopy(self._report)

    def metadata(self) -> dict:
        metadata = deepcopy(self._report["model"])
        metadata["recorded_reference"] = deepcopy(self._provenance)
        return metadata


def _read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(MAX_REFERENCE_BYTES + 1)
    if len(value) > MAX_REFERENCE_BYTES:
        raise ValueError("Reference file exceeds the 1 MB limit")
    return value


def _json_object(raw: bytes) -> dict:
    def reject_nonfinite(value):
        raise ValueError(f"Nonfinite reference JSON value: {value}")

    value = json.loads(raw, parse_constant=reject_nonfinite)
    if not isinstance(value, dict):
        raise ValueError("Reference JSON must contain an object")
    return value


def _reference_file(root: Path, name: str) -> Path:
    if not isinstance(name, str):
        raise ValueError("Invalid reference file path")
    path = (root / name).resolve()
    if not path.is_relative_to((root / "docs/benchmarks").resolve()):
        raise ValueError("Reference files must remain inside docs/benchmarks")
    return path


def _check_hash(raw: bytes, expected: str, label: str) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Reference {label} SHA256 mismatch")


def _validate_report(report, config, profile, fingerprint):
    model = report["model"]
    if config.mesh_points != 80 or model["config"] != asdict(config):
        raise ValueError("Reference requires exactly the original mesh80 config")
    if config.model != "DFN" or config.parameter_set != "ORegan2022" or config.thermal != "lumped":
        raise ValueError("Reference is only for the Stanford ORegan2022 lumped DFN pilot")
    if model["parameter_set"] != config.parameter_set:
        raise ValueError("Reference parameter-set label differs from config")
    if model["pybamm_version"] != pybamm.__version__:
        raise ValueError("PyBaMM version differs from the reference")
    if model["parameter_fingerprint"] != fingerprint:
        raise ValueError("Physical parameters or initial/boundary state differ from the reference")
    protocol = model["current_protocol"]
    if protocol["fingerprint_sha256"] != profile.fingerprint_sha256:
        raise ValueError("Current-profile fingerprint differs from the reference")
    if (
        protocol["integration_schedule"] != "adaptive"
        or protocol["solver_stops_at_profile_knots"] is not False
        or protocol["implicit_extrapolation"] is not False
        or protocol["profile_end_time_s"] != profile.end_time_s
        or protocol["current_range_a"] != [profile.min_current_a, profile.max_current_a]
    ):
        raise ValueError("Current-profile schedule or coverage differs from the reference")
    if report["source_sha256"] != SOURCE_SHA256:
        raise ValueError("Stanford measurement source SHA256 differs from the reference")
    if (
        report["protocol_sha256"] != PROTOCOL_SHA256
        or report["scheduling_addendum_sha256"] != SCHEDULING_ADDENDUM_SHA256
        or report["fitting_performed"] is not False
    ):
        raise ValueError("Reference does not use the frozen no-fit pilot protocol")
    if (
        model["termination"] != "event: Minimum voltage [V]"
        or model["voltage_cutoff_reached"] is not True
    ):
        raise ValueError("Reference did not terminate at the voltage cutoff")
    audit = model["physical_audit"]
    if (
        audit["passed"] is not True
        or audit["thermal_energy_balance"]["passed"] is not True
        or any(
            audit["concentration_bounds"][e]["passed"] is not True for e in ("negative", "positive")
        )
        or audit["electrolyte_min_mol_m3"] <= 0
        or audit["charge_integral_error_ah"] > 1e-6
        or audit["lithium_inventory_relative_drift"] > 1e-6
    ):
        raise ValueError("Original reference physical audits did not all pass")
    # Empirical gates deliberately do not appear here. A failed measured-voltage
    # comparison is valid numerical evidence and must remain a failed comparison.


def _validate_columns(values, report, config, profile):
    if values.ndim != 2 or values.shape[1] != 5 or len(values) < 2:
        raise ValueError("Reference CSV must contain at least two five-column rows")
    if not np.isfinite(values).all():
        raise ValueError("Reference CSV contains nonfinite observables")
    time, voltage, capacity, temperature, lithium = values.T
    if time[0] != 0 or np.any(np.diff(time) <= 0):
        raise ValueError("Reference time must start at zero and increase strictly")
    profile.require_coverage(float(time[-1]))
    if np.any(lithium <= 0) or np.any(capacity < 0) or np.any(np.diff(capacity) < 0):
        raise ValueError("Reference capacity or lithium inventory is invalid")
    if np.any((temperature <= 0) | (temperature >= config.max_temperature_k)):
        raise ValueError("Reference temperature leaves the configured envelope")
    initial_temperature = config.initial_temperature_k or config.ambient_temperature_k
    if not np.isclose(temperature[0], initial_temperature, rtol=0, atol=1e-10):
        raise ValueError("Reference initial temperature differs from config")
    cutoff = pybamm.ParameterValues(config.parameter_set)["Lower voltage cut-off [V]"]
    if not np.isclose(voltage[-1], cutoff, rtol=0, atol=1e-6) or np.any(voltage < cutoff - 1e-6):
        raise ValueError("Reference CSV does not reach the valid voltage cutoff")
    model = report["model"]
    for actual, recorded in (
        (time[-1], model["endpoint_time_s"]),
        (capacity[-1], model["capacity_ah"]),
        (capacity[-1], model["cutoff_capacity_ah"]),
    ):
        if not np.isclose(actual, recorded, rtol=0, atol=1e-10):
            raise ValueError("Reference CSV endpoint differs from the original report")
    charge_error = float(np.max(np.abs(capacity - profile.charge_integral_ah(time))))
    drift = float(np.max(np.abs(lithium - lithium[0])) / lithium[0])
    if charge_error > 1e-6 or drift > 1e-6:
        raise ValueError("Reference CSV fails current integration or lithium conservation")
    audit = model["physical_audit"]
    if not np.isclose(charge_error, audit["charge_integral_error_ah"], rtol=0, atol=1e-12):
        raise ValueError("Reference charge integral differs from its original physical audit")
    if not np.isclose(drift, audit["lithium_inventory_relative_drift"], rtol=0, atol=1e-12):
        raise ValueError("Reference lithium conservation differs from its original physical audit")
    return {"charge_integral_error_ah": charge_error, "lithium_inventory_relative_drift": drift}


def load_mesh80_reference(
    root: Path,
    config: ModelConfig,
    current_profile: CurrentProfile,
    expected_parameter_fingerprint: str,
) -> RecordedNumericalTrace:
    """Validate frozen bytes and their compatibility without running a simulation.

    ``root`` is the repository root. ``expected_parameter_fingerprint`` is the
    same combined physical-parameter/current-profile fingerprint used by simulate.
    Missing, corrupt, or incompatible evidence raises ValueError; there is no
    fallback solve and empirical failure never blocks reuse.
    """
    if not isinstance(current_profile, CurrentProfile):
        raise TypeError("Expected an immutable CurrentProfile")
    config.validate()
    root = Path(root).resolve()
    try:
        index = _json_object(_read_bounded(root / REFERENCE_INDEX))
        if (
            index["source_commit_sha"] != SOURCE_COMMIT_SHA
            or index["ci_run_id"] != CI_RUN_ID
            or index["artifact_zip_sha256"] != ARTIFACT_ZIP_SHA256
        ):
            raise ValueError("Reference source commit, CI run, or artifact identity changed")
        size = index["csv_uncompressed_bytes"]
        if type(size) is not int or not 0 < size <= MAX_REFERENCE_BYTES:
            raise ValueError("Reference declared CSV size exceeds the 1 MB limit")
        compressed = _read_bounded(_reference_file(root, index["csv_gzip_file"]))
        report_raw = _read_bounded(_reference_file(root, index["report_file"]))
        _check_hash(compressed, index["csv_gzip_sha256"], "gzip")
        _check_hash(report_raw, index["report_sha256"], "report")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            csv_raw = stream.read(MAX_REFERENCE_BYTES + 1)
        if len(csv_raw) > MAX_REFERENCE_BYTES or len(csv_raw) != size:
            raise ValueError("Reference uncompressed CSV size differs from the bounded declaration")
        _check_hash(csv_raw, index["csv_sha256"], "CSV")
        report = _json_object(report_raw)
        _validate_report(report, config, current_profile, expected_parameter_fingerprint)
        header, _, _ = csv_raw.partition(b"\n")
        if header.decode("ascii") != CSV_HEADER:
            raise ValueError("Reference CSV header differs from the five recorded observables")
        values = np.loadtxt(io.BytesIO(csv_raw), delimiter=",", skiprows=1, ndmin=2)
        rechecked = _validate_columns(values, report, config, current_profile)
    except (OSError, EOFError, KeyError, TypeError, UnicodeError, zlib.error) as exc:
        raise ValueError(f"Invalid or incomplete Stanford mesh80 reference: {exc}") from exc
    provenance = {
        **index,
        "reused": True,
        "new_solve_performed": False,
        "rechecked_from_recorded_observables": rechecked,
        "spatial_and_heat_audits": (
            "original source report; unavailable raw states were not rebuilt"
        ),
        "empirical_result": "original report retained without changing thresholds or gate labels",
    }
    return RecordedNumericalTrace(
        config,
        tuple(np.asarray(column, dtype="<f8").tobytes() for column in values.T),
        report,
        provenance,
    )
