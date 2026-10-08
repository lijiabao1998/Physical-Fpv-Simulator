from datetime import datetime, timedelta

import pytest

from physical_fpv.stanford_transitions import inspect_transitions


def records():
    rows = []
    currents = {1: 0.0, 2: 1.5, 3: 0.05, 4: 0.0, 5: -5.0, 6: 0.0}
    voltages = {1: 3.2, 2: 3.4, 3: 4.2, 4: 4.2, 5: 3.9, 6: 3.1}
    for phase in range(1, 7):
        for step_time in (1.0, 2.0):
            time = float(len(rows) + 1)
            rows.append(
                (
                    datetime(2020, 1, 1) + timedelta(seconds=time),
                    time,
                    step_time,
                    phase,
                    voltages[phase],
                    currents[phase],
                    25.0,
                )
            )
    return rows


def test_rest_to_discharge_retains_original_rows_and_current_sign():
    report = inspect_transitions(iter(records()))
    onset = report["rest_to_discharge"]
    assert onset["left"]["excel_row"] == 9
    assert onset["right"]["excel_row"] == 10
    assert onset["current_change_a"] == -5
    assert onset["voltage_change_v"] == pytest.approx(-0.3)
    assert onset["apparent_transition_ratio_ohm"] == pytest.approx(0.06)
    assert onset["source_sample_gap_s"] == 1
    assert onset["ratio_is_intrinsic_resistance"] is False
    assert report["measurement_rows"] == 12
    assert len(report["transitions"]) == 5


def test_equal_timestamp_current_step_preserves_both_limits():
    rows = records()
    right = list(rows[8])
    right[1] = rows[7][1]
    rows[8] = tuple(right)
    report = inspect_transitions(rows)
    onset = report["rest_to_discharge"]
    assert onset["source_sample_gap_s"] == 0
    assert onset["left"]["current_a"] == 0
    assert onset["right"]["current_a"] == -5
    assert report["exact_duplicate_times"] == 1
    assert report["duplicate_time_conflicts"] == 1
    assert report["measurement_rows"] == 12


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda r: r.__setitem__(9, (r[9][0], 0, *r[9][2:])), "test clock reverses"),
        (lambda r: r.__setitem__(9, (*r[9][:4], float("nan"), *r[9][5:])), "Nonfinite"),
        (lambda r: r.pop(), ""),
    ],
)
def test_invalid_measurements_fail(mutation, match):
    rows = records()
    mutation(rows)
    if match:
        with pytest.raises(ValueError, match=match):
            inspect_transitions(rows)
    else:
        # A shorter final block is retained, not padded to the other block lengths.
        assert inspect_transitions(rows)["blocks"][-1]["rows"] == 1


def test_nonzero_pre_rest_is_not_treated_as_zero_current_reference():
    rows = records()
    rows[6] = (*rows[6][:5], 0.02, rows[6][6])
    with pytest.raises(ValueError, match="zero-current rest"):
        inspect_transitions(rows)


def test_missing_final_rest_is_reported_without_inventing_an_endpoint():
    report = inspect_transitions(records()[:10])
    assert report["recorded_steps"] == [1, 2, 3, 4, 5]
    assert report["post_discharge_rest_recorded"] is False
    assert report["transitions"][-1]["steps"] == [4, 5]
    assert len(report["blocks"]) == 5


def test_missing_internal_protocol_phase_is_rejected():
    rows = [r for r in records() if r[3] != 3]
    with pytest.raises(ValueError, match="five-step source prefix"):
        inspect_transitions(rows)
