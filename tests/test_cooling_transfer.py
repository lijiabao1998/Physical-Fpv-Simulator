"""No-refit cross-cell transfer and archived source contracts."""

import importlib.util
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
    assert actual["scenarios"] == expected["scenarios"]
    assert actual["prediction_csv_sha256"] == expected["prediction_csv_sha256"]
    assert not actual["original_workbook_rechecked"]
    assert not actual["blind_validation"]
    assert not any(
        c["improves_both_comparators_in_all_three_windows"] for c in actual["scenarios"].values()
    )
