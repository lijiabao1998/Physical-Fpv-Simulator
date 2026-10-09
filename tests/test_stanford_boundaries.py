"""Synthetic-only boundary checks; no workbook access, model solve or fit."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from physical_fpv.stanford_boundaries import inspect_boundaries


def records(*, resistance=0.125, cv_current=0.125, count=12):
    currents = (0.0, 2.0, cv_current, 0.0, -4.0, 0.0)
    delays = (0.25, 0.75, 1.5, 2.5, 1.25, 4.25)
    rows = []
    for step, (current, delay) in enumerate(zip(currents, delays, strict=True), 1):
        for index in range(count):
            step_time = delay + index * (index + 1) / 2
            test_time = (step - 1) * 1000 + step_time
            rows.append(
                (
                    datetime(2020, 1, 1) + timedelta(seconds=test_time),
                    test_time,
                    step_time,
                    step,
                    3.5 + resistance * current,
                    current,
                    25.0,
                )
            )
    return rows


def replace(rows, index, column, value):
    row = list(rows[index])
    row[column] = value
    rows[index] = tuple(row)


def boundary(report, name):
    return next(item for item in report["boundaries"] if item["id"] == name)


@pytest.mark.parametrize("resistance", [0.0, 0.125, 0.0387])
def test_pure_fixed_r_response_preserves_all_four_boundaries(resistance):
    report = inspect_boundaries(iter(records(resistance=resistance)))
    assert [item["steps"] for item in report["boundaries"]] == [[1, 2], [3, 4], [4, 5], [5, 6]]
    for item in report["boundaries"]:
        assert item["primary"] == item["delayed_comparisons"][0]
        assert item["primary"]["apparent_transient_ratio_ohm"] == pytest.approx(resistance)
        assert all(
            pair["apparent_transient_ratio_ohm"] == pytest.approx(resistance)
            for pair in item["delayed_comparisons"]
        )
    audit = report["fixed_r_alone_audit"]
    assert audit["all_four_ratios_available"]
    assert audit["all_four_ratios_equal_within_computational_tolerance"]
    assert audit["nonnegative_fixed_r_alone_arithmetic_compatible"]
    assert audit["finite_ratio_range_ohm"] == pytest.approx([resistance, resistance])
    assert audit["computational_absolute_tolerance_ohm"] == 1e-12
    assert audit["computational_relative_tolerance"] == 0
    assert "not measurement uncertainty" in audit["tolerance_interpretation"]
    assert not audit["fixed_r_alone_physical_falsification_established"]
    assert not audit["fixed_r_component_ruled_out"]
    assert not audit["component_resistance_bounds_established"]
    assert not audit["true_ohmic_or_contact_resistance_identified"]
    assert report["model_runs"] == 0
    assert not report["fitting_performed"]
    assert not report["parameter_corrections_performed"]
    json.dumps(report, allow_nan=False)


def test_internal_voltage_evolution_breaks_equal_ratio_arithmetic_but_does_not_exclude_component():
    rows = records()
    for index in range(60, 72):
        replace(rows, index, 4, rows[index][4] + 0.08 + 0.002 * (rows[index][2] - rows[60][2]))
    report = inspect_boundaries(rows)
    audit = report["fixed_r_alone_audit"]
    assert not audit["all_four_ratios_equal_within_computational_tolerance"]
    assert audit["finite_ratio_span_ohm"] == pytest.approx(0.02)
    assert audit["large_delta_current_ratio_span_ohm"] == pytest.approx(0.02)
    assert not audit["nonnegative_fixed_r_alone_arithmetic_compatible"]
    assert not audit["fixed_r_alone_physical_falsification_established"]
    assert not audit["fixed_r_component_ruled_out"]
    assert "unidentifiable" in audit["fixed_r_component"]
    assert "Unknown measurement uncertainty" in audit["physical_interpretation"]
    rest = report["final_rest_context"]
    assert rest["whole_observed_rest"]["direction"] == "rising"
    assert rest["whole_observed_rest"]["endpoint_secant_v_per_s"] == pytest.approx(0.002)
    assert rest["last_ten_samples"]["endpoint_secant_v_per_s"] == pytest.approx(0.002)


@pytest.mark.parametrize("cv_current", [0.125, 0.499, 0.5, 0.501])
def test_small_denominator_threshold_only_annotates_and_never_removes_cv_stop(cv_current):
    rows = records(cv_current=cv_current)
    replace(rows, 36, 4, rows[36][4] + 0.01)
    report = inspect_boundaries(rows)
    pair = boundary(report, "cv_stop")["primary"]
    assert len(report["boundaries"]) == 4
    assert pair["delta_current_a"] == -cv_current
    assert pair["apparent_transient_ratio_ohm"] == pytest.approx(
        pair["delta_voltage_v"] / -cv_current
    )
    assert pair["ill_conditioned"] is (cv_current < 0.5)
    assert bool(pair["warnings"]) is (cv_current < 0.5)
    assert pair["ratio_status"] == "finite"
    audit = report["fixed_r_alone_audit"]
    assert audit["finite_ratio_count"] == 4
    assert audit["large_delta_current_finite_ratio_count"] == (3 if cv_current < 0.5 else 4)
    assert audit["ill_conditioned_boundaries"] == (["cv_stop"] if cv_current < 0.5 else [])
    if cv_current < 0.5:
        assert audit["large_delta_current_ratio_range_ohm"] == [0.125, 0.125]
        assert audit["finite_ratio_span_ohm"] > 0


@pytest.mark.parametrize("voltage_change", [0.0, 0.01])
def test_zero_denominator_retains_samples_deltas_and_unavailable_ratio(voltage_change):
    rows = records(cv_current=0)
    replace(rows, 36, 4, rows[36][4] + voltage_change)
    report = inspect_boundaries(rows)
    pair = boundary(report, "cv_stop")["primary"]
    assert pair["apparent_transient_ratio_ohm"] is None
    assert pair["ratio_status"] == "undefined_zero_delta_current"
    assert pair["ill_conditioned"]
    assert pair["delta_voltage_v"] == pytest.approx(voltage_change)
    assert pair["delta_current_a"] == 0
    audit = report["fixed_r_alone_audit"]
    assert not audit["all_four_ratios_available"]
    assert audit["finite_ratio_count"] == 3
    assert audit["unavailable_ratio_boundaries"] == ["cv_stop"]
    assert audit["all_four_ratios_equal_within_computational_tolerance"] is None
    assert audit["nonnegative_fixed_r_alone_arithmetic_compatible"] is None
    assert len(audit["primary_ratios"]) == len(report["boundaries"]) == 4
    json.dumps(report, allow_nan=False)


def test_all_unavailable_ratios_have_no_span_or_arithmetic_conclusion():
    rows = records()
    for index in range(len(rows)):
        replace(rows, index, 5, 0.0)
    report = inspect_boundaries(rows)
    audit = report["fixed_r_alone_audit"]
    assert audit["finite_ratio_range_ohm"] is None
    assert audit["finite_ratio_span_ohm"] is None
    assert audit["large_delta_current_ratio_range_ohm"] is None
    assert audit["all_four_ratios_equal_within_computational_tolerance"] is None
    assert len(audit["unavailable_ratio_boundaries"]) == 4


def test_nonuniform_delays_keep_individual_actual_samples_and_signed_changes():
    rows = records()
    for index in range(60, 72):
        replace(rows, index, 4, rows[index][4] + rows[index][2] / 1000)
        replace(rows, index, 6, 24.0 + (rows[index][2] - rows[60][2]) / 100)
    report = inspect_boundaries(rows)
    pairs = boundary(report, "discharge_stop")["delayed_comparisons"]
    assert len(pairs) == 10
    assert [pair["post_recorded_step_time_s"] for pair in pairs] == [row[2] for row in rows[60:70]]
    assert [pair["post_elapsed_since_inferred_commanded_origin_s"] for pair in pairs] == [
        row[2] for row in rows[60:70]
    ]
    assert pairs[0]["sample_gap_s"] != pairs[0]["post_recorded_step_time_s"]
    for pair, row in zip(pairs, rows[60:70], strict=True):
        assert pair["pre_sample"]["excel_row"] == 61
        assert pair["test_time_bracket_s"] == [rows[59][1], row[1]]
        assert pair["delta_voltage_v"] == row[4] - rows[59][4]
        assert pair["delta_current_a"] == 4
        assert pair["delta_skin_temperature_c"] == row[6] - rows[59][6]
        assert pair["apparent_transient_ratio_ohm"] == (row[4] - rows[59][4]) / 4
    expected_current_changes = [2, -0.125, -4, 4]
    for item, delta_i in zip(report["boundaries"], expected_current_changes, strict=True):
        assert item["primary"]["delta_current_a"] == delta_i
        assert item["primary"]["delta_voltage_v"] * delta_i > 0
        assert not item["primary"]["ratio_is_intrinsic_resistance"]
    assert pairs[0]["delta_skin_temperature_c"] == -1


def test_negative_ratios_and_mixed_signs_stay_visible():
    rows = records()
    replace(rows, 48, 4, rows[47][4] + 0.1)
    report = inspect_boundaries(rows)
    assert boundary(report, "discharge_start")["primary"]["apparent_transient_ratio_ohm"] < 0
    audit = report["fixed_r_alone_audit"]
    assert audit["finite_ratio_range_ohm"][0] < 0 < audit["finite_ratio_range_ohm"][1]
    assert not audit["all_four_ratios_nonnegative"]
    assert not audit["nonnegative_fixed_r_alone_arithmetic_compatible"]
    assert not audit["fixed_r_component_ruled_out"]
    negative = inspect_boundaries(records(resistance=-0.125))["fixed_r_alone_audit"]
    assert negative["all_four_ratios_equal_within_computational_tolerance"]
    assert not negative["nonnegative_fixed_r_alone_arithmetic_compatible"]


def test_pre_phase_charge_is_time_weighted_and_covers_only_observed_intervals():
    rows = records()
    first, last = rows[24], rows[35]
    duration = last[1] - first[1]
    for index in range(24, 36):
        replace(rows, index, 5, 0.1 + (rows[index][1] - first[1]) * 0.01)
    report = inspect_boundaries(rows)
    phase = boundary(report, "cv_stop")["pre_phase_context"]
    expected_mean = 0.1 + duration * 0.01 / 2
    assert phase["observed_duration_s"] == duration
    assert phase["current_a"]["time_weighted_mean"] == pytest.approx(expected_mean)
    assert phase["signed_observed_charge_ah"] == pytest.approx(expected_mean * duration / 3600)
    assert phase["unobserved_initial_interval_s"] == first[2]
    assert phase["current_a"]["time_weighted_mean"] != pytest.approx(
        sum(row[5] for row in rows[24:36]) / 12
    )
    discharge = boundary(report, "discharge_stop")["pre_phase_context"]
    assert discharge["signed_observed_charge_ah"] == pytest.approx(-4 * duration / 3600)


def test_source_windows_and_provenance_are_exact_and_input_is_unchanged():
    rows = records(count=32)
    original = copy.deepcopy(rows)
    report = inspect_boundaries(rows)
    assert report["measurement_rows"] == len(rows)
    assert report["audited_excel_rows_inclusive"] == [2, len(rows) + 1]
    assert "source_samples" not in report
    for item in report["boundaries"]:
        before, after = item["steps"]
        expected_pre = list(range(before * 32 - 10 + 2, before * 32 + 2))
        expected_post = list(range((after - 1) * 32 + 2, (after - 1) * 32 + 12))
        assert [r["excel_row"] for r in item["last_ten_pre_samples"]] == expected_pre
        assert [r["excel_row"] for r in item["first_ten_post_samples"]] == expected_post
        assert item["primary"]["excel_row_pair"] == [expected_pre[-1], expected_post[0]]
        for sample in item["last_ten_pre_samples"] + item["first_ten_post_samples"]:
            source = rows[sample["excel_row"] - 2]
            assert sample["date_naive_local"] == source[0].isoformat()
            assert [
                sample[key]
                for key in (
                    "test_time_s",
                    "step_time_s",
                    "step",
                    "voltage_v",
                    "current_a",
                    "skin_temperature_c",
                )
            ] == list(source[1:])
    report["boundaries"][0]["primary"]["pre_sample"]["voltage_v"] = 999
    assert rows == original


@pytest.mark.parametrize("count", [1, 2, 9])
def test_short_phases_return_only_available_actual_samples(count):
    report = inspect_boundaries(records(count=count))
    assert all(len(item["delayed_comparisons"]) == count for item in report["boundaries"])
    assert all(len(item["last_ten_pre_samples"]) == count for item in report["boundaries"])
    if count == 1:
        assert report["contiguous_steps"][0]["current_a"]["time_weighted_mean"] is None
        assert report["final_rest_context"]["whole_observed_rest"]["direction"] == "unavailable"


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_test",
        "duplicate_across_steps",
        "reversed_test",
        "reversed_date",
        "date_drift",
        "negative_step_time",
        "reversed_step_time",
        "step_origin_drift",
        "missing_phase",
        "repeated_phase",
        "extra_phase",
        "nonintegral_step",
        "nan",
        "infinity",
        "bad_date",
        "aware_date",
        "bad_schema",
        "boolean_measurement",
        "empty",
    ],
)
def test_schema_sequence_and_clock_corruption_fail_without_repair(problem):
    rows = records()
    if problem == "duplicate_test":
        replace(rows, 2, 1, rows[1][1])
    elif problem == "duplicate_across_steps":
        replace(rows, 12, 1, rows[11][1])
    elif problem == "reversed_test":
        replace(rows, 2, 1, rows[1][1] - 1)
    elif problem == "reversed_date":
        replace(rows, 2, 0, rows[1][0] - timedelta(seconds=1))
    elif problem == "date_drift":
        replace(rows, 5, 0, rows[5][0] + timedelta(seconds=1.01))
    elif problem == "negative_step_time":
        replace(rows, 0, 2, -0.1)
    elif problem == "reversed_step_time":
        replace(rows, 2, 2, rows[1][2] - 0.1)
    elif problem == "step_origin_drift":
        replace(rows, 5, 2, rows[5][2] + 1.01)
    elif problem == "missing_phase":
        rows = [row for row in rows if row[3] != 3]
    elif problem == "repeated_phase":
        replace(rows, 15, 3, 1)
    elif problem == "extra_phase":
        replace(rows, -1, 3, 7)
    elif problem == "nonintegral_step":
        replace(rows, 0, 3, 1.5)
    elif problem == "nan":
        replace(rows, 17, 4, float("nan"))
    elif problem == "infinity":
        replace(rows, 17, 6, float("inf"))
    elif problem == "bad_date":
        replace(rows, 0, 0, "2020-01-01")
    elif problem == "aware_date":
        replace(rows, 0, 0, rows[0][0].replace(tzinfo=UTC))
    elif problem == "bad_schema":
        rows[0] = rows[0][:-1]
    elif problem == "boolean_measurement":
        replace(rows, 0, 5, False)
    else:
        rows = []
    with pytest.raises(ValueError):
        inspect_boundaries(rows)


def test_all_rows_are_audited_even_outside_exported_boundary_windows():
    rows = records(count=32)
    replace(rows, 32 + 16, 6, float("nan"))
    with pytest.raises(ValueError, match="Nonfinite"):
        inspect_boundaries(rows)


def test_one_second_clock_tolerance_is_inclusive_and_origin_is_median_relative():
    rows = records()
    replace(rows, 1, 0, rows[0][0])  # Nondecreasing dates may repeat at coarse resolution.
    replace(rows, 2, 0, rows[2][0] + timedelta(seconds=1))
    replace(rows, 2, 2, rows[2][2] + 1)
    replace(rows, 3, 2, rows[3][2] - 1)
    report = inspect_boundaries(rows)
    assert report["clock_audit"]["max_relative_date_test_clock_discrepancy_s"] == 1
    phase = report["contiguous_steps"][0]
    assert phase["clock_relation_max_deviation_s"] == 1
    assert phase["inferred_origin_range_test_time_s"] == [-1, 1]


def test_reported_origin_uses_all_step_rows_and_preserves_native_sample_delay():
    rows = records()
    replace(rows, 60, 2, rows[60][2] + 0.5)
    report = inspect_boundaries(rows)
    pair = boundary(report, "discharge_stop")["primary"]
    assert pair["next_commanded_step_origin_test_time_s"] == 5000
    assert pair["post_elapsed_since_inferred_commanded_origin_s"] == 4.25
    assert pair["post_recorded_step_time_s"] == 4.75
    assert pair["post_sample"]["step_time_s"] == rows[60][2]
