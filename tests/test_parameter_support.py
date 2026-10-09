import copy
import json
from pathlib import Path

import pybamm
import pytest

from physical_fpv.parameter_support import (
    assess_surface_support,
    compare_fixed_functions,
    exchange_points,
)

ROOT = Path(__file__).resolve().parents[1]


def sources():
    manifest = json.loads((ROOT / "data/oregan-kinetics-manifest.json").read_text())
    return manifest, exchange_points(ROOT, manifest)


def model():
    evidence = json.loads(
        (ROOT / "docs/benchmarks/stanford-k1-v3-verified-evidence.json").read_text()
    )
    return evidence["report"]["cases"]["120"]["model"]


def test_released_units_and_fixed_functions_without_a_battery_solve(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A parameter audit must not construct a battery model")

    monkeypatch.setattr(pybamm, "Simulation", forbidden)
    monkeypatch.setattr(pybamm.lithium_ion, "DFN", forbidden)
    _, points = sources()
    assert len(points) == 80
    point = next(
        p
        for p in points
        if p["electrode"] == "negative"
        and p["temperature_k"] == 298.15
        and p["electrode_stoichiometry"] == 0.926
    )
    # Original CSV is0.068413806mA/cm2;1mA/cm2 is10A/m2.
    assert point["released_exchange_current_a_m2"] == pytest.approx(0.68413806)
    compared = compare_fixed_functions([point], pybamm.ParameterValues("ORegan2022"))
    assert compared["points"][0]["installed_exchange_current_a_m2"] == pytest.approx(
        1.4606357443772942
    )
    assert compared["fitting_performed"] is False


def test_byte_changes_to_measurements_are_rejected(tmp_path):
    manifest, _ = sources()
    member = copy.deepcopy(next(f for f in manifest["files"] if f["kind"] == "exchange_current"))
    content = (ROOT / member["path"]).read_bytes()
    (tmp_path / "changed.csv").write_bytes(content.replace(b"0.926", b"0.925"))
    member["path"] = "changed.csv"
    with pytest.raises(ValueError, match="bytes differ"):
        exchange_points(tmp_path, {"files": [member]})


def test_actual_surface_extrema_cross_both_sampled_envelopes():
    _, points = sources()
    result = assess_surface_support(model(), points)
    assert result["negative"]["below_sampled_stoichiometry"] is True
    assert result["negative"]["above_sampled_stoichiometry"] is False
    assert result["positive"]["below_sampled_stoichiometry"] is False
    assert result["positive"]["above_sampled_stoichiometry"] is True
    assert result["negative"]["crossing_times_s"] is None
    assert result["positive"]["fraction_of_trajectory_outside"] is None
    assert result["negative"]["full_cell_soc_mapping_established"] is False


def test_node_extrema_cannot_replace_missing_surface_measurements():
    _, points = sources()
    metadata = model()
    del metadata["physical_audit"]["concentration_bounds"]["negative"]["surface_min_mol_m3"]
    with pytest.raises(ValueError, match="surface concentration extrema are unavailable"):
        assess_surface_support(metadata, points)


def test_failed_physical_audit_is_not_promoted_by_support_check():
    _, points = sources()
    metadata = model()
    metadata["physical_audit"]["passed"] = False
    with pytest.raises(ValueError, match="physical audit did not pass"):
        assess_surface_support(metadata, points)


@pytest.mark.parametrize("value", [0, -1, float("nan")])
def test_invalid_concentration_scale_is_rejected(value):
    _, points = sources()
    metadata = model()
    metadata["physical_audit"]["concentration_bounds"]["negative"]["limit_mol_m3"] = value
    with pytest.raises(ValueError, match="maximum concentration"):
        assess_surface_support(metadata, points)
