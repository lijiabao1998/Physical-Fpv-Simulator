"""Analytic checks of conditional charge alignment, not physical validation."""

import numpy as np
import pytest

from physical_fpv.low_rate_reference import below_intervals, charge_axis, compare, statistics


def observation(t=(1.0, 2.0, 3.0), current=-3600.0, voltage=(4.0, 3.0, 2.0)):
    return np.column_stack((t, np.full(3, current), voltage, np.full(3, 298.15)))


def model():
    return np.array(
        [
            [0.0, 0.0, 4.1, 4.2, 298.15],
            [1.0, 1.0, 3.9, 4.0, 298.15],
            [2.0, 2.0, 2.9, 3.0, 298.15],
            [3.0, 3.0, 1.9, 2.0, 298.15],
        ]
    )


def test_charge_units_and_missing_start_conventions():
    values = observation(current=-1800.0)
    np.testing.assert_array_equal(charge_axis(values), [0.0, 0.5, 1.0])
    np.testing.assert_array_equal(charge_axis(values, True), [0.5, 1.0, 1.5])


@pytest.mark.parametrize(
    "kind", ["positive", "zero", "nan", "duplicate", "reverse", "negative_time"]
)
def test_invalid_source_rejected_without_filtering(kind):
    values = observation()
    if kind == "positive":
        values[1, 1] = 1
    if kind == "zero":
        values[1, 1] = 0
    if kind == "nan":
        values[1, 2] = np.nan
    if kind == "duplicate":
        values[1, 0] = values[0, 0]
    if kind == "reverse":
        values[1, 0] = 0
    if kind == "negative_time":
        values[0, 0] = -1
    with pytest.raises(ValueError):
        charge_axis(values)


def test_charge_weighted_square_integral_and_sign_crossing():
    q = np.array([0.0, 1.0, 3.0])
    y = np.array([-1.0, 1.0, 1.0])
    result = statistics(q, y)
    assert result["mean_v"] == pytest.approx(2 / 3)
    assert result["rms_v"] == pytest.approx(np.sqrt(7 / 9))
    assert result["negative_charge_fraction"] == pytest.approx(1 / 6)
    assert below_intervals(q, y) == [[0.0, 0.5]]
    assert below_intervals(q, y, -0.5) == [[0.0, 0.25]]


def test_zero_plateaus_do_not_count_as_positive_or_negative():
    q = np.arange(4.0)
    y = np.array([-1.0, 0.0, 0.0, 1.0])
    result = statistics(q, y)
    assert result["negative_charge_fraction"] == pytest.approx(1 / 3)
    assert result["positive_charge_fraction"] == pytest.approx(1 / 3)
    assert result["zero_plateau_charge_fraction"] == pytest.approx(1 / 3)
    assert below_intervals(q, y) == [[0.0, 1.0]]


def test_both_alignments_preserve_identity_without_extrapolation():
    for mode, start in ((False, 0.0), (True, 1.0)):
        result, arrays = compare(observation(), observation(), model(), mode)
        assert result["common_charge_interval_ah"] == [start, start + 2]
        assert result["arithmetic_closure_max_v"] < 1e-12
        assert not result["absolute_soc_equivalence_established"]
        assert len(result["windows"]) == 5
        np.testing.assert_allclose(
            arrays[:, 5] + arrays[:, 6] - arrays[:, 7], arrays[:, 8], atol=1e-15
        )


def test_unequal_charge_support_clips_to_measured_overlap():
    result, _ = compare(observation(current=-1800), observation(), model())
    assert result["common_charge_interval_ah"] == [0.0, 1.0]
    assert result["source_support"]["high_rate"]["covered_charge_fraction"] == 0.5


def test_empty_overlap_and_model_extrapolation_rejected():
    altered = model()
    altered[:, 1] += 10
    with pytest.raises(ValueError, match="Empty"):
        compare(observation(), observation(), altered, True)
    altered = model()
    altered[:, 0] += 10
    with pytest.raises(ValueError, match="outside"):
        compare(observation(), observation(), altered)


def test_source_hash_changes_fail_closed(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "low_rate_check", "scripts/check_stanford_k2_low_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "altered.gz"
    path.write_bytes(b"altered")
    with pytest.raises(ValueError, match="hash"):
        module.read_verified(path, module.SOURCE_HASHES["stanford-k2-low-rate-discharge.csv.gz"])


def test_archived_comparison_reproduces_without_fit_solve_or_download(tmp_path, monkeypatch):
    import importlib.util
    import json
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("Conditional comparison may not solve or download")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "low_rate_check", "scripts/check_stanford_k2_low_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = module.ROOT / "docs/benchmarks"
    expected = json.loads((root / "stanford-k2-low-rate-comparison.json").read_text())
    actual = module.run(root, tmp_path)
    assert not actual["historical_1c_passed"]
    assert actual["source_gzip_sha256"] == expected["source_gzip_sha256"]
    for name, case in actual["scenarios"].items():
        target = expected["scenarios"][name]
        assert case["alignment"] == target["alignment"]
        assert not case["absolute_soc_equivalence_established"]
        assert case["arithmetic_closure_max_v"] < 1e-12
        for left, right in zip(case["windows"], target["windows"], strict=True):
            np.testing.assert_allclose(
                left["charge_interval_ah"], right["charge_interval_ah"], rtol=1e-13, atol=1e-14
            )
            for term in left["terms"]:
                for metric in left["terms"][term]:
                    assert left["terms"][term][metric] == pytest.approx(
                        right["terms"][term][metric], rel=1e-12, abs=1e-13
                    )
        np.testing.assert_allclose(
            case["upper_reference_violation_intervals_ah"],
            target["upper_reference_violation_intervals_ah"],
            rtol=1e-12,
            atol=1e-12,
        )


@pytest.mark.parametrize(
    "field",
    [
        "exact_duplicate_times",
        "clock_relation_max_deviation_s",
        "backwards_date_intervals",
        "max_relative_date_test_clock_discrepancy_s",
    ],
)
def test_normalizer_rejects_unqualified_clocks(field):
    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "low_rate_prepare", "scripts/prepare_stanford_k2_low_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inspection = json.loads(Path("docs/benchmarks/stanford-k2-low-rate-source.json").read_text())[
        "source_inspection"
    ]
    module.validate_clocks(inspection)
    phase = next(p for p in inspection["contiguous_steps"] if p["step"] == 5)
    if field in phase:
        phase[field] = 2
    else:
        inspection["measurement_clock_audit"][field] = 2
    with pytest.raises(ValueError):
        module.validate_clocks(inspection)
