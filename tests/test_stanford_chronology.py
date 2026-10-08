import copy
import json
from pathlib import Path

import pytest

from physical_fpv.stanford_chronology import summarize_chronology


def fixture():
    names = ["NMC_k1_5C_05degC.xlsx", "NMC_k1_1C_25degC.xlsx"]
    reports = []
    for index, name in enumerate(names):
        reports.append(
            {
                "source": {"filename": name, "sha256": "fixture-only-not-source"},
                "measurement_clock_audit": {
                    "backwards_date_intervals": 0,
                    "max_relative_date_test_clock_discrepancy_s": 0.001,
                },
                "measurement_rows": 2,
                "canonical_six_step_sequence": False,
                "contiguous_steps": [
                    {
                        "step": 1,
                        "measurement_dates_naive_local": [
                            f"2019-09-0{index + 1}T01:00:00",
                            f"2019-09-0{index + 1}T02:00:00",
                        ],
                    }
                ],
            }
        )
    manifest = {
        "files": [{"filename": n} for n in names],
        "target_filename": names[-1],
        "dataset_doi": "fixture",
        "license": "fixture",
        "authors": [],
    }
    return reports, manifest


def test_known_prior_stress_is_retained_without_claiming_freshness():
    reports, manifest = fixture()
    result = summarize_chronology(list(reversed(reports)), manifest)
    assert result["recorded_order_qualified"]
    assert result["provisional_earlier_high_rate_files"] == [reports[0]["source"]["filename"]]
    assert not result["fresh_target_established"]
    assert not result["independent_validation_established"]
    assert result["model_runs"] == 0


@pytest.mark.parametrize("problem", ["missing", "backwards", "drift", "overlap"])
def test_partial_or_inconsistent_dates_do_not_qualify_order(problem):
    reports, manifest = fixture()
    if problem == "missing":
        reports.pop(0)
    elif problem == "backwards":
        reports[0]["measurement_clock_audit"]["backwards_date_intervals"] = 1
    elif problem == "drift":
        reports[0]["measurement_clock_audit"]["max_relative_date_test_clock_discrepancy_s"] = 2
    else:
        reports[0]["contiguous_steps"][0]["measurement_dates_naive_local"][1] = (
            "2019-09-02T01:10:00"
        )
    result = summarize_chronology(reports, manifest)
    assert not result["recorded_order_qualified"]
    assert not result["fresh_target_established"]


def test_duplicate_report_cannot_count_as_another_experiment():
    reports, manifest = fixture()
    reports.append(copy.deepcopy(reports[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_chronology(reports, manifest)


def test_recorded_campaign_keeps_repeated_cell_and_nonvalidation_labels():
    result = json.loads(Path("docs/benchmarks/stanford-k1-chronology.json").read_text())
    assert result["complete"] and result["recorded_order_qualified"]
    assert result["inspected_files"] == 15
    assert len(result["inspection_report_sha256"]) == 15
    assert result["provisional_earlier_files"] == ["NMC_k1_0_05C_25degC.xlsx"]
    assert result["provisional_earlier_high_rate_files"] == []
    assert sum(x["measurement_rows"] for x in result["ordered_intervals"]) == 530735
    assert not result["fresh_target_established"]
    assert not result["independent_validation_established"]
    assert result["model_runs"] == 0
