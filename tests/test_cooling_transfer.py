"""No-refit cross-cell transfer and archived source contracts."""

import hashlib
import importlib.util
import io
import math
from pathlib import Path

import numpy as np
import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "cooling_transfer", "scripts/check_stanford_cooling_transfer.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_frozen_rate_is_not_optimized_for_new_cell(monkeypatch):
    import physical_fpv.cooling_characterization as cooling

    def forbidden(*args, **kwargs):
        raise AssertionError("Transfer must not refit")

    monkeypatch.setattr(cooling, "fit_decay", forbidden)
    t = np.arange(0.0, 3602)
    y = 24 + 8 * np.exp(-(t - 60) / 700)
    result = module().transfer_metrics(t, y, 24, 1 / 400, 1 / 760)
    assert result["transferred_parameters"]["rate_per_s"] == 1 / 400
    assert not result["k1_fitting_performed"]
    assert not result["improves_both_comparators_in_all_three_windows"]
    assert result["windows"]["late_check"]["transferred_decay"]["rmse_k"] > 0


def test_synthetic_transfer_detects_better_prediction():
    t = np.arange(0.0, 3602)
    y = 24 + 8 * np.exp(-(t - 60) / 400)
    result = module().transfer_metrics(t, y, 24, 1 / 400, 1 / 760)
    assert result["improves_both_comparators_in_all_three_windows"]
    assert not result["physical_parameter_identification"]
    assert all(w["transferred_decay"]["rmse_k"] < 1e-5 for w in result["windows"].values())


@pytest.mark.parametrize("rate", [0, -1, np.nan])
def test_invalid_transferred_rate_rejected(rate):
    with pytest.raises(ValueError):
        module().transfer_metrics([60, 3600], [32, 24], 24, rate, 1 / 760)


def test_frozen_fit_and_normalized_source_are_immutable(tmp_path):
    m = module()
    bad = tmp_path / "bad.json"
    bad.write_text("{}\n")
    with pytest.raises(ValueError, match="Frozen"):
        m.load_frozen(bad)
    with pytest.raises(ValueError, match="Normalized"):
        m.load_committed_source(bad)
    with pytest.raises(ValueError, match="archive"):
        m.load_source(bad)


def test_committed_source_and_fixed_fit_identity():
    m = module()
    frozen = m.load_frozen(Path("docs/benchmarks/stanford-k2-cooling.json"))
    rests, inspection = m.load_committed_source(
        Path("docs/benchmarks/stanford-k1-cooling-source.json")
    )
    assert frozen["scenarios"]["nominal_25c"]["fit"]["tau_s"] == 345.2559103125735
    assert inspection["canonical_six_step_sequence"]
    assert all(np.all(np.diff(t) > 0) and len(t) == len(y) for t, y in rests.values())
    assert set(rests) == {4, 6}


def test_saved_transfer_reproduces_from_repo_without_fit_solve_or_download(tmp_path, monkeypatch):
    import json
    import urllib.request

    import pybamm

    import physical_fpv.cooling_characterization as cooling

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved-data transfer cannot fit, solve or download")

    monkeypatch.setattr(cooling, "fit_decay", forbidden)
    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    m = module()
    expected = json.loads(
        (m.ROOT / "docs/benchmarks/stanford-k1-cooling-transfer.json").read_text()
    )
    actual = m.run(
        m.ROOT / "docs/benchmarks/stanford-k1-cooling-source.json",
        m.ROOT / "docs/benchmarks/stanford-k2-cooling.json",
        tmp_path,
    )
    assert_reproduced_metrics(actual["scenarios"], expected["scenarios"])
    assert expected["prediction_csv_sha256"] == (
        "7d8d7ee64206573fd9ad693ea5ba16fef08baa47545b8b6d42570359a50375a2"
    )
    assert_prediction_reproduction(
        tmp_path / "stanford-k1-cooling-transfer-predictions.csv",
        m.ROOT / "docs/benchmarks/stanford-k1-cooling-transfer-predictions.csv",
        actual["prediction_csv_sha256"],
        expected["prediction_csv_sha256"],
    )
    assert not actual["original_workbook_rechecked"]
    assert not actual["blind_validation"]
    assert not any(
        c["improves_both_comparators_in_all_three_windows"] for c in actual["scenarios"].values()
    )


def assert_reproduced_metrics(actual, expected):
    """Allow only binary64 arithmetic noise; metadata and verdicts stay exact."""
    assert type(actual) is type(expected)
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_reproduced_metrics(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected, strict=True):
            assert_reproduced_metrics(left, right)
    elif isinstance(expected, float):
        # 64 binary64 eps: a roundoff budget, not a physical acceptance gate.
        assert math.isfinite(actual) and math.isfinite(expected)
        assert abs(actual - expected) <= 64 * np.finfo(float).eps * max(1.0, abs(expected))
    else:
        assert actual == expected


def test_metric_reproduction_allows_roundoff_but_rejects_material_changes():
    original = {"rmse_k": 0.777508290544055, "gate": False, "window": [60.0, 600.0]}
    rounded = {**original, "rmse_k": math.nextafter(original["rmse_k"], math.inf)}
    assert_reproduced_metrics(rounded, original)
    for changed in (
        {**original, "rmse_k": original["rmse_k"] + 1e-10},
        {**original, "rmse_k": float("nan")},
        {**original, "gate": True},
        {**original, "gate": 0},
        {**original, "extra": 1},
        {**original, "window": [60.0]},
    ):
        with pytest.raises(AssertionError):
            assert_reproduced_metrics(changed, original)


def assert_prediction_reproduction(actual_path, expected_path, actual_digest, expected_digest):
    """Immutable bytes keep exact identity; recomputed math has a roundoff budget."""
    actual_bytes, expected_bytes = actual_path.read_bytes(), expected_path.read_bytes()
    assert hashlib.sha256(actual_bytes).hexdigest() == actual_digest
    assert hashlib.sha256(expected_bytes).hexdigest() == expected_digest
    assert actual_bytes.splitlines()[0] == expected_bytes.splitlines()[0]
    actual = np.loadtxt(io.BytesIO(actual_bytes), delimiter=",", skiprows=1, ndmin=2)
    expected = np.loadtxt(io.BytesIO(expected_bytes), delimiter=",", skiprows=1, ndmin=2)
    assert actual.shape == expected.shape and expected.shape[1] >= 3
    assert np.isfinite(actual).all() and np.isfinite(expected).all()
    # Clocks and measured temperatures originate in identical pinned input arrays.
    assert np.array_equal(actual[:, :2], expected[:, :2])
    limit = 64 * np.finfo(float).eps * np.maximum(1.0, abs(expected[:, 2:]))
    assert np.all(abs(actual[:, 2:] - expected[:, 2:]) <= limit)


def test_prediction_reproduction_distinguishes_byte_identity_from_math(tmp_path):
    expected = tmp_path / "expected.csv"
    actual = tmp_path / "actual.csv"
    original = np.array([[60.0, 30.0, 29.0, 28.0], [61.0, 29.9, 28.9, 27.9]])

    def write(path, data, header="time,measured,predicted,prior"):
        np.savetxt(path, data, delimiter=",", header=header, comments="")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    expected_digest = write(expected, original)
    rounded = original.copy()
    rounded[0, 2] = np.nextafter(rounded[0, 2], np.inf)
    actual_digest = write(actual, rounded)
    assert actual_digest != expected_digest
    assert_prediction_reproduction(actual, expected, actual_digest, expected_digest)
    for kind in ("prediction", "measured", "clock", "nonfinite", "rows", "header", "digest"):
        changed = original.copy()
        header = "time,measured,predicted,prior"
        if kind == "prediction":
            changed[0, 2] += 1e-10
        if kind == "measured":
            changed[0, 1] += 1e-12
        if kind == "clock":
            changed[0, 0] += 1e-12
        if kind == "nonfinite":
            changed[0, 2] = np.nan
        if kind == "rows":
            changed = changed[:1]
        if kind == "header":
            header = "time,measured,prior,predicted"
        actual_digest = write(actual, changed, header)
        if kind == "digest":
            actual_digest = "0" * 64
        with pytest.raises(AssertionError):
            assert_prediction_reproduction(actual, expected, actual_digest, expected_digest)
