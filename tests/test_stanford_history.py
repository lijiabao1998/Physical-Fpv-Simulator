"""Synthetic published campaigns only; these tests read no new raw histories."""

import copy
import hashlib
import json
from datetime import datetime, timedelta

import pytest

from physical_fpv.stanford_chronology import summarize_chronology
from physical_fpv.stanford_history import aggregate_selected_histories


def campaign_fixture(*, k2_prior=False, k6_prior=True):
    reports, entries = [], []
    for cell, prior in (("k2", k2_prior), ("k6", k6_prior)):
        names = [
            f"NMC_{cell}_{rate}C_{temp}degC.xlsx"
            for rate in ("0_05", "1", "2", "3", "5")
            for temp in ("05", "25", "35")
        ]
        if prior:
            names.insert(0, names.pop(6))
        for index, filename in enumerate(names):
            digest = hashlib.sha256(filename.encode()).hexdigest()
            entries.append(
                {"filename": filename, "content_details": {"sha256_hash": digest}, "size": 123}
            )
            start = datetime(2019, 1, 1) + timedelta(days=index)
            steps = []
            for phase in range(1, 6):
                first, last = (phase - 1) * 11 + 1, phase * 11
                current = -10.04 if phase == 5 else 1.2 if phase in (2, 3) else 0
                steps.append(
                    {
                        "step": phase,
                        "measurement_rows": 2,
                        "measurement_dates_naive_local": [
                            (start + timedelta(seconds=t)).isoformat() for t in (first, last)
                        ],
                        "test_time_range_s": [first, last],
                        "commanded_step_time_range_s": [1, 11],
                        "backwards_step_clock_intervals": 0,
                        "negative_step_clock_records": 0,
                        "clock_relation_max_deviation_s": 0,
                        "exact_duplicate_times": 0,
                        "duplicate_time_conflicts": 0,
                        "current_a": {
                            "min": current,
                            "max": current,
                            "time_weighted_mean": current,
                        },
                        "signed_observed_charge_ah": current * 10 / 3600,
                        "surface_temperature_c": {"initial": 25, "final": 71, "min": 25, "max": 71},
                        "endpoint_voltage_v": [4.1, 3.02],
                    }
                )
            reports.append(
                {
                    "source": {"filename": filename, "sha256": digest, "bytes": 123},
                    "measurement_clock_audit": {
                        "backwards_date_intervals": 0,
                        "max_relative_date_test_clock_discrepancy_s": 0,
                    },
                    "measurement_rows": 10,
                    "canonical_six_step_sequence": False,
                    "contiguous_steps": steps,
                }
            )
    return reports, {
        "dataset_doi": "synthetic-only",
        "license": "fixture",
        "authors": ["Synthetic fixture"],
        "files": entries,
        "target_filenames": {cell: f"NMC_{cell}_1C_25degC.xlsx" for cell in ("k2", "k6")},
    }


def report_named(reports, filename):
    return next(report for report in reports if report["source"]["filename"] == filename)


def move_start(report, new_start):
    old_start = datetime.fromisoformat(
        report["contiguous_steps"][0]["measurement_dates_naive_local"][0]
    )
    shift = new_start - old_start
    for step in report["contiguous_steps"]:
        step["measurement_dates_naive_local"] = [
            (datetime.fromisoformat(t) + shift).isoformat()
            for t in step["measurement_dates_naive_local"]
        ]


@pytest.mark.parametrize(
    ("k2_prior", "k6_prior", "status", "holds"),
    [
        (False, True, "holds", True),
        (True, True, "false", False),
        (False, False, "false", False),
        (True, False, "false", False),
    ],
)
def test_recorded_premise_requires_the_exact_two_cell_contrast(k2_prior, k6_prior, status, holds):
    reports, manifest = campaign_fixture(k2_prior=k2_prior, k6_prior=k6_prior)
    result = aggregate_selected_histories(list(reversed(reports)), manifest)
    assert result["full_histories_qualified"]
    assert result["recorded_premise_status"] == status
    assert result["recorded_premise_holds"] is holds
    assert result["histories"]["k2"]["recorded_prior_high_rate_exposure"] is k2_prior
    assert result["histories"]["k6"]["recorded_prior_high_rate_exposure"] is k6_prior
    assert result["model_runs"] == 0
    assert not result["fitting_performed"]
    assert not result["causation_established"]
    assert not result["damage_established"]
    assert not result["fresh_target_established"]
    assert not result["independent_validation_established"]
    assert "k3-k5 remain unqualified" in result["other_cells_history"]
    assert result["nominal_high_rate_threshold_c"] == 2
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("target_missing", [False, True])
def test_missing_file_is_unknown_exposure_even_when_observed_subset_has_no_high_rate(
    target_missing,
):
    reports, manifest = campaign_fixture(k2_prior=False, k6_prior=False)
    filename = "NMC_k2_1C_25degC.xlsx" if target_missing else "NMC_k2_2C_05degC.xlsx"
    reports.remove(report_named(reports, filename))
    result = aggregate_selected_histories(reports, manifest)
    history = result["histories"]["k2"]
    assert result["recorded_premise_status"] == "unresolved"
    assert result["recorded_premise_holds"] is None
    assert not result["full_histories_qualified"]
    assert history["missing_files"] == [filename]
    assert history["qualified_earlier_high_rate_files"] is None
    assert history["recorded_prior_high_rate_exposure"] is None
    if target_missing:
        assert "missing_target_workbook" in history["history_unresolved_reasons"]
        assert all(i["relation_to_target"] == "unresolved" for i in history["ordered_intervals"])


@pytest.mark.parametrize("problem", ["missing_mapping", "wrong_nominal", "incomplete_manifest"])
def test_manifest_cannot_shrink_the_campaign_or_substitute_the_target(problem):
    reports, manifest = campaign_fixture()
    if problem == "missing_mapping":
        del manifest["target_filenames"]["k2"]
    elif problem == "wrong_nominal":
        manifest["target_filenames"]["k2"] = "NMC_k2_1C_05degC.xlsx"
    else:
        filename = "NMC_k2_5C_35degC.xlsx"
        manifest["files"] = [entry for entry in manifest["files"] if entry["filename"] != filename]
        reports.remove(report_named(reports, filename))
    result = aggregate_selected_histories(reports, manifest)
    assert result["recorded_premise_status"] == "unresolved"
    assert result["histories"]["k2"]["recorded_prior_high_rate_exposure"] is None


@pytest.mark.parametrize(
    "problem",
    [
        "missing_date_audit",
        "null_date_audit",
        "missing_phases",
        "null_phases",
        "backwards_date",
        "date_drift",
        "missing_step_audit",
        "duplicate_time",
        "duplicate_conflict",
        "missing_duplicate_audit",
        "duplicate_across_phases",
        "backwards_step",
        "negative_step",
        "step_drift",
        "reversed_step_endpoints",
        "reversed_test_endpoints",
        "missing_test_range",
        "invalid_date",
        "aware_date",
        "reversed_dates",
        "hash_mismatch",
        "missing_hash",
        "wrong_bytes",
        "missing_phase",
    ],
)
def test_invalid_or_absent_support_is_unresolved(problem):
    reports, manifest = campaign_fixture()
    report = report_named(reports, "NMC_k2_5C_35degC.xlsx")
    step = report["contiguous_steps"][0]
    if problem == "missing_date_audit":
        del report["measurement_clock_audit"]
    elif problem == "null_date_audit":
        report["measurement_clock_audit"] = None
    elif problem == "missing_phases":
        del report["contiguous_steps"]
    elif problem == "null_phases":
        report["contiguous_steps"] = None
    elif problem == "backwards_date":
        report["measurement_clock_audit"]["backwards_date_intervals"] = 1
    elif problem == "date_drift":
        report["measurement_clock_audit"]["max_relative_date_test_clock_discrepancy_s"] = 1.01
    elif problem == "missing_step_audit":
        del step["backwards_step_clock_intervals"]
    elif problem == "duplicate_time":
        step["exact_duplicate_times"] = 1
    elif problem == "duplicate_conflict":
        step["duplicate_time_conflicts"] = 1
    elif problem == "missing_duplicate_audit":
        del step["exact_duplicate_times"]
    elif problem == "duplicate_across_phases":
        report["contiguous_steps"][1]["test_time_range_s"][0] = step["test_time_range_s"][-1]
    elif problem == "backwards_step":
        step["backwards_step_clock_intervals"] = 1
    elif problem == "negative_step":
        step["negative_step_clock_records"] = 1
    elif problem == "step_drift":
        step["clock_relation_max_deviation_s"] = 1.01
    elif problem == "reversed_step_endpoints":
        step["commanded_step_time_range_s"].reverse()
    elif problem == "reversed_test_endpoints":
        step["test_time_range_s"].reverse()
    elif problem == "missing_test_range":
        del step["test_time_range_s"]
    elif problem == "invalid_date":
        step["measurement_dates_naive_local"][0] = "not a source date"
    elif problem == "aware_date":
        step["measurement_dates_naive_local"][0] += "+00:00"
    elif problem == "reversed_dates":
        step["measurement_dates_naive_local"].reverse()
    elif problem == "hash_mismatch":
        report["source"]["sha256"] = "0" * 64
    elif problem == "missing_hash":
        del report["source"]["sha256"]
    elif problem == "wrong_bytes":
        report["source"]["bytes"] = 1
    else:
        report["contiguous_steps"].pop(2)
    result = aggregate_selected_histories(reports, manifest)
    history = result["histories"]["k2"]
    assert result["recorded_premise_status"] == "unresolved"
    assert result["recorded_premise_holds"] is None
    assert not history["history_qualified"]
    assert history["history_unresolved_reasons"]
    assert history["recorded_prior_high_rate_exposure"] is None
    assert history["qualified_earlier_high_rate_files"] is None


@pytest.mark.parametrize("at_target", [False, True])
def test_any_same_cell_overlap_prevents_qualification(at_target):
    reports, manifest = campaign_fixture()
    first = report_named(reports, "NMC_k2_3C_05degC.xlsx")
    second = report_named(reports, f"NMC_k2_{'1C_25' if at_target else '5C_35'}degC.xlsx")
    start = datetime.fromisoformat(
        second["contiguous_steps"][0]["measurement_dates_naive_local"][0]
    )
    move_start(first, start + timedelta(seconds=5))
    result = aggregate_selected_histories(reports, manifest)
    history = result["histories"]["k2"]
    assert result["recorded_premise_status"] == "unresolved"
    assert len(history["overlaps"]) == 1
    assert "same_cell_workbook_intervals_overlap" in history["history_unresolved_reasons"]
    if at_target:
        interval = next(
            i for i in history["ordered_intervals"] if i["filename"] == first["source"]["filename"]
        )
        assert interval["relation_to_target"] == "overlapping target"


@pytest.mark.parametrize("before", [False, True])
def test_touching_target_boundaries_are_never_strictly_before_or_after(before):
    reports, manifest = campaign_fixture()
    candidate = report_named(reports, "NMC_k6_2C_05degC.xlsx")
    target = report_named(reports, "NMC_k6_1C_25degC.xlsx")
    first = datetime.fromisoformat(
        target["contiguous_steps"][0]["measurement_dates_naive_local"][0]
    )
    last = datetime.fromisoformat(
        target["contiguous_steps"][-1]["measurement_dates_naive_local"][-1]
    )
    move_start(candidate, first - (last - first) if before else last)
    result = aggregate_selected_histories(reports, manifest)
    history = result["histories"]["k6"]
    interval = next(
        i for i in history["ordered_intervals"] if i["filename"] == candidate["source"]["filename"]
    )
    assert interval["relation_to_target"] == "overlapping target"
    assert not history["overlaps"]
    assert len(history["touching_boundaries"]) == 1
    assert result["recorded_premise_status"] == "unresolved"
    assert history["recorded_prior_high_rate_exposure"] is None


def test_cross_cell_concurrent_tests_are_not_same_cell_overlaps():
    reports, manifest = campaign_fixture(k2_prior=False, k6_prior=False)
    result = aggregate_selected_histories(reports, manifest)
    assert result["full_histories_qualified"]
    assert all(not h["overlaps"] for h in result["histories"].values())


@pytest.mark.parametrize("problem", ["duplicate_report", "unselected_report", "cross_cell_target"])
def test_mixed_or_counterfeit_source_selections_are_rejected(problem):
    reports, manifest = campaign_fixture()
    if problem == "duplicate_report":
        reports.append(copy.deepcopy(reports[0]))
    elif problem == "unselected_report":
        reports[0]["source"]["filename"] = reports[0]["source"]["filename"].replace("k2", "k3")
    else:
        manifest["target_filenames"]["k2"] = manifest["target_filenames"]["k6"]
    with pytest.raises(ValueError, match="Duplicate|unselected|cross-cell"):
        aggregate_selected_histories(reports, manifest)


def test_single_cell_api_requires_explicit_cell_and_keeps_real_names():
    reports, manifest = campaign_fixture()
    selected = [entry for entry in manifest["files"] if "_k2_" in entry["filename"]]
    single = {**manifest, "files": selected, "target_filename": manifest["target_filenames"]["k2"]}
    selected_reports = [report for report in reports if "_k2_" in report["source"]["filename"]]
    with pytest.raises(ValueError, match="cross-cell"):
        summarize_chronology(selected_reports, single)
    result = summarize_chronology(selected_reports, single, cell_id="k2")
    assert result["history_qualified"]
    assert all("_k2_" in i["filename"] for i in result["ordered_intervals"])
    with pytest.raises(ValueError, match="unselected"):
        summarize_chronology(reports, single, cell_id="k2")


def test_preserves_five_source_phases_every_endpoint_and_all_temporal_relations():
    reports, manifest = campaign_fixture()
    original_reports, original_manifest = copy.deepcopy(reports), copy.deepcopy(manifest)
    result = aggregate_selected_histories(reports, manifest)
    history = result["histories"]["k6"]
    assert history["history_qualified"]
    assert {i["relation_to_target"] for i in history["ordered_intervals"]} == {
        "target",
        "recorded before target",
        "recorded after target",
    }
    for interval in history["ordered_intervals"]:
        source = report_named(reports, interval["filename"])
        assert interval["source_sha256"] == source["source"]["sha256"]
        assert interval["contiguous_steps"] == source["contiguous_steps"]
        assert interval["source_step_sequence"] == [1, 2, 3, 4, 5]
        assert not interval["canonical_six_step_sequence"]
        assert not interval["final_rest_recorded"]
        discharge = source["contiguous_steps"][-1]
        assert interval["end_naive_local"] == discharge["measurement_dates_naive_local"][-1]
        assert (
            interval["discharges"][0]["observed_charge_ah"]
            == -discharge["signed_observed_charge_ah"]
        )
        assert interval["discharges"][0]["endpoint_voltage_v"] == [4.1, 3.02]
        assert interval["discharges"][0]["surface_temperature_c"]["max"] == 71
        assert interval["discharges"][0]["current_a"]["time_weighted_mean"] == -10.04
    assert reports == original_reports
    assert manifest == original_manifest
    # Even editing the returned phase data cannot mutate the input evidence.
    history["ordered_intervals"][0]["contiguous_steps"][0]["step"] = 99
    assert reports == original_reports


def test_source_step_gate_is_separate_from_legacy_date_order_flag():
    reports, manifest = campaign_fixture()
    for report in reports:
        del report["contiguous_steps"][0]["negative_step_clock_records"]
    result = aggregate_selected_histories(reports, manifest)
    assert all(h["recorded_order_qualified"] for h in result["histories"].values())
    assert not result["full_histories_qualified"]
    assert result["recorded_premise_status"] == "unresolved"
    assert all(h["recorded_prior_high_rate_exposure"] is None for h in result["histories"].values())


def test_real_sixth_phase_is_retained_when_present():
    reports, manifest = campaign_fixture()
    report = reports[0]
    rest = copy.deepcopy(report["contiguous_steps"][-1])
    rest.update(
        {
            "step": 6,
            "current_a": {"min": 0, "max": 0, "time_weighted_mean": 0},
            "signed_observed_charge_ah": 0,
            "test_time_range_s": [56, 66],
            "measurement_dates_naive_local": [
                (datetime.fromisoformat(t) + timedelta(seconds=11)).isoformat()
                for t in rest["measurement_dates_naive_local"]
            ],
        }
    )
    report["contiguous_steps"].append(rest)
    report["canonical_six_step_sequence"] = True
    report["measurement_rows"] += 2
    result = aggregate_selected_histories(reports, manifest)
    assert result["full_histories_qualified"]
    interval = result["histories"]["k2"]["ordered_intervals"][0]
    assert interval["final_rest_recorded"]
    assert interval["source_step_sequence"] == [1, 2, 3, 4, 5, 6]
    assert interval["contiguous_steps"][-1] == rest
    assert interval["end_naive_local"] == rest["measurement_dates_naive_local"][-1]


def test_one_second_clock_tolerance_is_inclusive_and_not_peak_to_peak():
    reports, manifest = campaign_fixture()
    report = reports[0]
    phase = report["contiguous_steps"][2]
    phase["measurement_dates_naive_local"] = [
        (datetime.fromisoformat(t) + timedelta(seconds=offset)).isoformat()
        for t, offset in zip(phase["measurement_dates_naive_local"], (1, -1), strict=True)
    ]
    report["measurement_clock_audit"]["max_relative_date_test_clock_discrepancy_s"] = 1
    phase["commanded_step_time_range_s"] = [1, 13]
    phase["clock_relation_max_deviation_s"] = 1
    assert aggregate_selected_histories(reports, manifest)["full_histories_qualified"]
