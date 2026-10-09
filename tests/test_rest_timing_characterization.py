"""Immutable rest timing, supported brackets and no scientific reinterpretation."""

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
module = importlib.import_module("characterize_stanford_k2_rest_timing")


@pytest.fixture
def low_rows():
    return module.read_rows(module.LOW_RECORDS.read_bytes())


def test_saved_characterization_reproduces_without_download_or_solve(monkeypatch):
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("No download or battery solve")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    result = module.analyze()
    saved = json.loads((module.BASE / "stanford-k2-rest-timing-result.json").read_text())
    assert result == saved
    assert result["identified_resistance"] is False
    assert result["independent_experimental_validation"] is False
    for case in result["cases"].values():
        for point in case["points"]:
            assert 0 <= point["upper_weight"] <= 1
            assert abs(point["identity_closure_v"]) <= 1e-12
            assert float(point["lower_source_row"]["Step_Time(s)"]) <= point["nominal_rest_time_s"]
            assert point["nominal_rest_time_s"] <= float(point["upper_source_row"]["Step_Time(s)"])


@pytest.mark.parametrize("query", [0.0, 3601.0, float("nan")])
def test_no_extrapolation(low_rows, query):
    with pytest.raises(ValueError, match="outside"):
        module.interpolate(low_rows[1:], query)


@pytest.mark.parametrize(
    "field,value,match", [("Current(A)", "0.1", "nonzero"), ("Voltage(V)", "nan", "Nonfinite")]
)
def test_invalid_rest_measurement_rejected(low_rows, field, value, match):
    rows = copy.deepcopy(low_rows)
    rows[50][field] = value
    with pytest.raises(ValueError, match=match):
        module.characterize(rows, module.protocol())


def test_duplicate_clock_rejected(low_rows):
    low_rows[50]["Step_Time(s)"] = low_rows[49]["Step_Time(s)"]
    with pytest.raises(ValueError, match="Nonmonotone"):
        module.characterize(low_rows, module.protocol())


def test_changed_records_cannot_self_authorize_with_receipt(tmp_path, monkeypatch):
    receipt = json.loads(module.LOW_RECEIPT.read_text())
    raw = module.LOW_RECORDS.read_bytes() + b"extra"
    target = tmp_path / "changed.gz"
    target.write_bytes(raw)
    receipt["records_gzip_sha256"] = module.digest(raw)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setattr(module, "LOW_RECORDS", target)
    monkeypatch.setattr(module, "LOW_RECEIPT", receipt_path)
    with pytest.raises(ValueError, match="identity changed"):
        module.analyze()


def test_frozen_queries_cannot_change(tmp_path, monkeypatch):
    path = tmp_path / "protocol.json"
    spec = module.protocol()
    spec["queries_nominal_rest_s"] = [1, 2]
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(module, "PROTOCOL", path)
    with pytest.raises(ValueError, match="Frozen"):
        module.protocol()
