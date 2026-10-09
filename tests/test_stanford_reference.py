import gzip
import hashlib
import io
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from physical_fpv.core import ModelConfig
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.stanford_reference import (
    CSV_HEADER,
    MAX_REFERENCE_BYTES,
    REFERENCE_INDEX,
    SOURCE_COMMIT_SHA,
    load_mesh80_reference,
)
from physical_fpv.thermal_benchmark import thermal_numerics

ROOT = Path(__file__).resolve().parents[1]


def write_reference(fixture, csv_raw=None):
    """Re-sign a bounded synthetic fixture to exercise checks after byte validation."""
    index = fixture.index
    if csv_raw is None:
        stream = io.StringIO()
        np.savetxt(stream, fixture.values, delimiter=",", header=CSV_HEADER, comments="")
        csv_raw = stream.getvalue().encode()
    compressed = gzip.compress(csv_raw, mtime=0)
    report_raw = (json.dumps(fixture.report, allow_nan=False) + "\n").encode()
    (fixture.root / index["csv_gzip_file"]).write_bytes(compressed)
    (fixture.root / index["report_file"]).write_bytes(report_raw)
    index.update(
        csv_gzip_sha256=hashlib.sha256(compressed).hexdigest(),
        csv_sha256=hashlib.sha256(csv_raw).hexdigest(),
        csv_uncompressed_bytes=len(csv_raw),
        report_sha256=hashlib.sha256(report_raw).hexdigest(),
    )
    (fixture.root / REFERENCE_INDEX).write_text(json.dumps(index))


@pytest.fixture
def reference(tmp_path):
    index = json.loads((ROOT / REFERENCE_INDEX).read_text())
    report = json.loads((ROOT / index["report_file"]).read_text())
    config = replace(ModelConfig(**report["model"]["config"]), current_a=5.0)
    profile = CurrentProfile([0, 6000], [5, 5])
    values = np.array(
        [
            [0, 4.1, 0, config.initial_temperature_k, 0.26],
            [1800, 3.5, 2.5, 303, 0.26],
            [3600, 2.5, 5, 306, 0.26],
        ]
    )
    model = report["model"]
    model.update(config=asdict(config), endpoint_time_s=3600, capacity_ah=5, cutoff_capacity_ah=5)
    model["current_protocol"].update(
        fingerprint_sha256=profile.fingerprint_sha256, current_range_a=[5, 5]
    )
    model["physical_audit"].update(lithium_inventory_relative_drift=0, charge_integral_error_ah=0)
    index["scope"] = "Synthetic unit-test fixture only; not new empirical evidence"
    (tmp_path / "docs/benchmarks").mkdir(parents=True)
    fixture = SimpleNamespace(
        root=tmp_path,
        index=index,
        report=report,
        config=config,
        profile=profile,
        values=values,
        fingerprint=model["parameter_fingerprint"],
    )
    write_reference(fixture)
    return fixture


def load(reference, **overrides):
    return load_mesh80_reference(
        reference.root,
        overrides.get("config", reference.config),
        overrides.get("profile", reference.profile),
        overrides.get("fingerprint", reference.fingerprint),
    )


def test_original_committed_evidence_retains_failed_empirical_result():
    index = json.loads((ROOT / REFERENCE_INDEX).read_text())
    compressed = (ROOT / index["csv_gzip_file"]).read_bytes()
    raw = gzip.decompress(compressed)
    report_raw = (ROOT / index["report_file"]).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == index["csv_gzip_sha256"]
    assert hashlib.sha256(raw).hexdigest() == index["csv_sha256"]
    assert hashlib.sha256(report_raw).hexdigest() == index["report_sha256"]
    assert len(raw) == index["csv_uncompressed_bytes"] == 498690
    assert np.loadtxt(io.BytesIO(raw), delimiter=",", skiprows=1).shape == (3989, 5)
    report = json.loads(report_raw)
    assert report["model"]["physical_audit"]["passed"] is True
    assert report["voltage_rmse_v"] == 0.19089933729045996
    assert report["empirical_thresholds"]["voltage_rmse_v"] == 0.05
    assert report["electrical_gates"]["voltage_rmse"] is False
    assert report["electrical_gates_passed"] is False


def test_trace_preserves_original_report_and_numerical_duck_type(reference, monkeypatch):
    def no_solve(*args, **kwargs):
        pytest.fail("Recorded evidence must not launch a new solve")

    monkeypatch.setattr("pybamm.Simulation.solve", no_solve)
    result = load(reference)
    assert result.empirical_report == reference.report
    for key, value in reference.report["model"].items():
        assert result.metadata()[key] == value
    provenance = result.metadata()["recorded_reference"]
    assert provenance["reused"] is True
    assert provenance["new_solve_performed"] is False
    assert provenance["source_commit_sha"] == SOURCE_COMMIT_SHA
    assert result.empirical_report["electrical_gates_passed"] is False
    np.testing.assert_array_equal(
        np.column_stack(
            (
                result.time_s,
                result.voltage_v,
                result.capacity_ah,
                result.temperature_k,
                result.lithium_mol,
            )
        ),
        reference.values,
    )
    assert thermal_numerics(result, result)["passed"]
    for unavailable in ("heating_w", "cooling_w", "heat_capacity_j_k", "current_protocol"):
        assert not hasattr(result, unavailable)


def test_returned_reports_and_arrays_cannot_mutate_verified_evidence(reference):
    result = load(reference)
    result.empirical_report["electrical_gates_passed"] = True
    result.physical_audit["passed"] = False
    result.metadata()["recorded_reference"]["reused"] = False
    assert result.empirical_report["electrical_gates_passed"] is False
    assert result.physical_audit["passed"] is True
    assert result.metadata()["recorded_reference"]["reused"] is True
    with pytest.raises(ValueError):
        result.time_s[0] = 10
    with pytest.raises(ValueError):
        result.voltage_v.flags.writeable = True
    result.time_s.resize((1, 3))
    assert result.time_s.shape == (3,)


@pytest.mark.parametrize("field", ["csv_gzip_file", "report_file"])
def test_byte_corruption_rejected_before_parsing(reference, field):
    path = reference.root / reference.index[field]
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load(reference)


@pytest.mark.parametrize("field", ["csv_sha256", "csv_gzip_sha256", "report_sha256"])
def test_wrong_expected_hash_is_rejected(reference, field):
    reference.index[field] = "0" * 64
    (reference.root / REFERENCE_INDEX).write_text(json.dumps(reference.index))
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load(reference)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit_sha", "0" * 40),
        ("ci_run_id", 1),
        ("artifact_zip_sha256", "0" * 64),
    ],
)
def test_other_source_run_cannot_be_relabelled_as_the_reference(reference, field, value):
    reference.index[field] = value
    write_reference(reference)
    with pytest.raises(ValueError, match="identity changed"):
        load(reference)


@pytest.mark.parametrize(
    "change",
    [
        {"mesh_points": 120},
        {"tolerance": 1e-8},
        {"sample_period_s": 10},
        {"heat_transfer_coefficient_w_m2_k": 14},
        {"initial_temperature_k": 298.15},
    ],
)
def test_changed_discretization_or_physics_requires_new_evidence(reference, change):
    with pytest.raises(ValueError, match="original mesh80 config"):
        load(reference, config=replace(reference.config, **change))


def test_wrong_physical_parameter_fingerprint_rejected(reference):
    with pytest.raises(ValueError, match="Physical parameters"):
        load(reference, fingerprint="0" * 64)


def test_wrong_forcing_rejected_even_with_the_same_mean_current(reference):
    profile = CurrentProfile([0, 6000], [4, 6])
    with pytest.raises(ValueError, match="Current-profile fingerprint"):
        load(reference, profile=profile)


def test_runtime_pybamm_version_must_match(reference, monkeypatch):
    monkeypatch.setattr("physical_fpv.stanford_reference.pybamm.__version__", "wrong-version")
    with pytest.raises(ValueError, match="PyBaMM version"):
        load(reference)


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda r: r.update(source_sha256="0" * 64), "measurement source"),
        (lambda r: r["model"].update(termination="final time"), "voltage cutoff"),
        (lambda r: r["model"]["physical_audit"].update(passed=False), "physical audits"),
        (
            lambda r: r["model"]["physical_audit"]["thermal_energy_balance"].update(passed=False),
            "physical audits",
        ),
        (
            lambda r: r["model"]["physical_audit"]["concentration_bounds"]["negative"].update(
                passed=False
            ),
            "physical audits",
        ),
        (
            lambda r: r["model"]["current_protocol"].update(integration_schedule="all_knots"),
            "schedule",
        ),
    ],
)
def test_invalid_original_evidence_rejected(reference, mutation, message):
    mutation(reference.report)
    write_reference(reference)
    with pytest.raises(ValueError, match=message):
        load(reference)


@pytest.mark.parametrize(
    "row,column,value,message",
    [
        (1, 0, 0, "increase strictly"),
        (1, 1, float("nan"), "nonfinite"),
        (0, 3, 290, "initial temperature"),
        (1, 2, 2.6, "current integration"),
        (1, 4, 0.27, "lithium conservation"),
        (2, 1, 2.6, "voltage cutoff"),
        (2, 2, 5.1, "endpoint differs"),
    ],
)
def test_actual_csv_must_support_recorded_physical_claims(reference, row, column, value, message):
    reference.values[row, column] = value
    write_reference(reference)
    with pytest.raises(ValueError, match=message):
        load(reference)


def test_recomputed_physical_audit_must_match_original_report(reference):
    reference.report["model"]["physical_audit"]["charge_integral_error_ah"] = 0.5e-6
    write_reference(reference)
    with pytest.raises(ValueError, match="differs from its original physical audit"):
        load(reference)


def test_csv_schema_is_exact(reference):
    raw = gzip.decompress((reference.root / reference.index["csv_gzip_file"]).read_bytes())
    write_reference(reference, raw.replace(b"lithium_inventory_mol", b"invented_heating_w"))
    with pytest.raises(ValueError, match="header"):
        load(reference)


def test_gzip_inflation_is_bounded_even_if_declared_size_lies(reference):
    raw = b"0" * (MAX_REFERENCE_BYTES + 1)
    write_reference(reference, raw)
    reference.index["csv_uncompressed_bytes"] = 1
    (reference.root / REFERENCE_INDEX).write_text(json.dumps(reference.index))
    with pytest.raises(ValueError, match="bounded declaration"):
        load(reference)


def test_malformed_gzip_with_matching_hash_still_rejected(reference):
    path = reference.root / reference.index["csv_gzip_file"]
    compressed = path.read_bytes()[:-5]
    path.write_bytes(compressed)
    reference.index["csv_gzip_sha256"] = hashlib.sha256(compressed).hexdigest()
    (reference.root / REFERENCE_INDEX).write_text(json.dumps(reference.index))
    with pytest.raises(ValueError, match="incomplete Stanford mesh80 reference"):
        load(reference)


def test_reference_path_cannot_escape_benchmark_directory(reference):
    reference.index["report_file"] = "../unrelated.json"
    (reference.root / REFERENCE_INDEX).write_text(json.dumps(reference.index))
    with pytest.raises(ValueError, match="inside docs/benchmarks"):
        load(reference)


def test_missing_reference_does_not_fall_back_to_a_solve(reference):
    (reference.root / reference.index["csv_gzip_file"]).unlink()
    with pytest.raises(ValueError, match="incomplete Stanford mesh80 reference"):
        load(reference)
