"""Analytical examples for source-to-source metrics, without measured workbooks."""

import json
import math

import numpy as np
import pytest

from physical_fpv.stanford_cohort import compare_discharge_pair, summary_discharge


def trace(times, *, current=-5.0, voltage=4.0, skin=298.15):
    times = np.asarray(times, dtype=float)
    return np.column_stack(
        (times, *(np.broadcast_to(value, times.shape) for value in (current, voltage, skin)))
    )


def test_exact_ramp_integrals_keep_commanded_clock_and_signed_difference():
    # Difference is (t-10)/4 over [10,14]: mean 1/2, mean square 1/3.
    reference = trace([10, 10.3, 12.7, 14])
    candidate = trace([10, 10.2, 11.1, 13.6, 14], voltage=[4, 4.05, 4.275, 4.9, 5])
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    voltage = result["voltage_difference"]
    assert voltage["signed_time_mean_v"] == pytest.approx(0.5)
    assert voltage["rmse_v"] == pytest.approx(math.sqrt(1 / 3))
    assert voltage["max_absolute_v"] == 1
    assert voltage["first_max_absolute_step_time_s"] == 14
    assert voltage["signed_value_at_first_maximum_v"] == 1
    assert result["common_observed_interval_s"] == [10, 14]
    assert result["common_knot_count"] == 7
    assert result["reference_common_duration_fraction"] == 1
    assert result["candidate_common_duration_fraction"] == 1
    assert result["difference_convention"] == "candidate minus reference"


def test_candidate_only_knot_preserves_interior_peak_and_squared_integral():
    # An asymmetric triangular pulse has area 3, squared area 4 over width 3.
    reference = trace([2, 5])
    candidate = trace([2, 3, 5], voltage=[4, 6, 4], skin=[299.15, 297.15, 299.15])
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    voltage = result["voltage_difference"]
    assert voltage["signed_time_mean_v"] == pytest.approx(1)
    assert voltage["rmse_v"] == pytest.approx(math.sqrt(4 / 3))
    assert voltage["max_absolute_v"] == 2
    assert voltage["first_max_absolute_step_time_s"] == 3
    temperature = result["measured_skin_temperature_difference"]
    assert temperature["signed_time_mean_k"] == pytest.approx(0)
    assert temperature["rmse_k"] == pytest.approx(math.sqrt(1 / 3))
    assert temperature["max_absolute_k"] == 1
    assert temperature["first_max_absolute_step_time_s"] == 2


def test_reference_only_knot_contributes_and_negative_peak_keeps_its_sign():
    reference = trace([2, 3, 5], voltage=[4, 6, 4])
    candidate = trace([2, 5])
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    voltage = result["voltage_difference"]
    assert voltage["signed_time_mean_v"] == pytest.approx(-1)
    assert voltage["rmse_v"] == pytest.approx(math.sqrt(4 / 3))
    assert voltage["max_absolute_v"] == 2
    assert voltage["first_max_absolute_step_time_s"] == 3
    assert voltage["signed_value_at_first_maximum_v"] == -2


def test_unmatched_beginnings_and_endings_do_not_hide_full_observed_charge():
    # Reference i=-t has observed integral 48 As over [2,10]; candidate i=-3
    # has 21 As over [5,12]. Neither integral includes an invented [0,start].
    reference = trace([2, 4, 10], current=[-2, -4, -10], voltage=[4.2, 4.4, 5])
    candidate = trace([5, 9, 12], current=-3, voltage=[4.5, 4.9, 5.2])
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    assert result["common_observed_interval_s"] == [5, 10]
    assert result["common_observed_duration_s"] == 5
    assert result["reference_common_duration_fraction"] == pytest.approx(5 / 8)
    assert result["candidate_common_duration_fraction"] == pytest.approx(5 / 7)
    assert result["voltage_difference"]["rmse_v"] == pytest.approx(0, abs=1e-14)
    first, second = result["reference"], result["candidate"]
    assert first["first_observed_step_time_s"] == 2
    assert first["last_observed_step_time_s"] == 10
    assert second["first_observed_step_time_s"] == 5
    assert second["last_observed_step_time_s"] == 12
    assert first["observed_delivered_charge_ah"] == pytest.approx(48 / 3600)
    assert second["observed_delivered_charge_ah"] == pytest.approx(21 / 3600)
    assert first["raw_signed_current"] == {"time_mean_a": -6, "min_a": -10, "max_a": -2}
    assert second["raw_signed_current"] == {"time_mean_a": -3, "min_a": -3, "max_a": -3}
    # Common current difference is t-3 on [5,10], with mean square 67/3.
    current = result["raw_signed_current_difference"]
    assert current["signed_time_mean_a"] == pytest.approx(4.5)
    assert current["rmse_a"] == pytest.approx(math.sqrt(67 / 3))
    assert current["max_absolute_a"] == 7
    assert current["first_max_absolute_step_time_s"] == 10


def test_shorter_trace_retains_duration_coverage_and_charge_difference():
    reference = trace([1, 2, 8, 11], current=-6)
    candidate = trace([1, 3, 4], current=-6)
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    assert result["voltage_difference"]["rmse_v"] == 0
    assert result["reference_common_duration_fraction"] == pytest.approx(0.3)
    assert result["candidate_common_duration_fraction"] == 1
    assert result["reference"]["observed_delivered_charge_ah"] == pytest.approx(60 / 3600)
    assert result["candidate"]["observed_delivered_charge_ah"] == pytest.approx(18 / 3600)
    assert result["voltage_difference"]["first_max_absolute_step_time_s"] == 1


def test_irregular_current_summary_is_time_weighted_not_sample_weighted():
    observed = trace([7, 8, 17], current=[-1, -3, -3])
    summary = summary_discharge(observed, "k6")
    assert summary["raw_signed_current"]["time_mean_a"] == pytest.approx(-2.9)
    assert summary["raw_signed_current"]["min_a"] == -3
    assert summary["raw_signed_current"]["max_a"] == -1
    assert summary["observed_delivered_charge_ah"] == pytest.approx(29 / 3600)
    assert summary["observed_duration_s"] == 10
    assert summary["measurement_rows"] == 3
    assert summary["cell_id"] == "k6"


def test_reports_are_json_serializable_and_do_not_mutate_the_source():
    reference = trace([2, 3, 7], current=[-3, -6, -2], voltage=[4, 3.8, 3])
    candidate = trace([3, 5, 9], current=[-6, -4, -5], voltage=[3.9, 3.6, 2.7])
    original_reference, original_candidate = reference.copy(), candidate.copy()
    result = compare_discharge_pair(reference, candidate, "k1", "k2")
    json.dumps(result, allow_nan=False)
    np.testing.assert_array_equal(reference, original_reference)
    np.testing.assert_array_equal(candidate, original_candidate)


@pytest.mark.parametrize("conflicting_values", [False, True])
def test_duplicate_source_times_are_rejected_without_deduplication(conflicting_values):
    observed = trace([1, 2, 2, 4])
    if conflicting_values:
        observed[2, 2] += 0.1
    with pytest.raises(ValueError, match="strictly increasing"):
        summary_discharge(observed, "k1")
    with pytest.raises(ValueError, match="strictly increasing"):
        compare_discharge_pair(trace([1, 4]), observed, "k1", "k2")


@pytest.mark.parametrize("times", [[1, 3, 2], [-1, 2, 4]])
def test_reversed_or_negative_commanded_times_are_rejected(times):
    with pytest.raises(ValueError, match="strictly increasing"):
        summary_discharge(trace(times), "k1")


@pytest.mark.parametrize("column", range(4))
@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_nonfinite_values_are_rejected_in_every_observed_column(column, bad_value):
    observed = trace([1, 2, 3])
    observed[1, column] = bad_value
    with pytest.raises(ValueError, match="finite"):
        compare_discharge_pair(observed, trace([1, 3]), "k1", "k2")


@pytest.mark.parametrize(
    "observed",
    [[], [1, -5, 4, 298.15], [[1, -5, 4, 298.15]], np.ones((3, 3)), trace([1, 2]).astype(str)],
)
def test_invalid_or_ambiguous_observed_schema_is_rejected(observed):
    with pytest.raises(ValueError, match="numerical rows"):
        summary_discharge(observed, "k1")


def test_masked_measurement_is_not_silently_used_as_observed_data():
    observed = np.ma.array(trace([1, 2]), mask=False)
    observed.mask[1, 2] = True
    with pytest.raises(ValueError, match="masked"):
        summary_discharge(observed, "k1")


@pytest.mark.parametrize("candidate_times", [[3, 4], [2, 4], [0, 1]])
def test_absent_or_single_instant_overlap_has_no_time_average(candidate_times):
    with pytest.raises(ValueError, match="positive-duration common interval"):
        compare_discharge_pair(trace([1, 2]), trace(candidate_times), "k1", "k2")


@pytest.mark.parametrize("current", [[-5, 1], [0, 0], [1, 2]])
def test_charge_or_rest_is_not_mislabeled_as_a_discharge(current):
    with pytest.raises(ValueError, match="signed discharge current"):
        summary_discharge(trace([1, 2], current=current), "k1")


def test_distinct_source_identifiers_are_required():
    with pytest.raises(ValueError, match="distinct cell identifiers"):
        compare_discharge_pair(trace([1, 2]), trace([1, 2]), "k1", "k1")
    with pytest.raises(ValueError, match="cell identifier"):
        summary_discharge(trace([1, 2]), " ")
