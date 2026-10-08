"""Input qualification and analytical k2 fixtures; never run a battery solve."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from physical_fpv import stanford_k2 as k2
from physical_fpv.core import SimulationResult
from physical_fpv.current_profile import CurrentProfile


def inspection_report():
    phases = [
        {
            "step": step,
            "exact_duplicate_times": 0,
            "duplicate_time_conflicts": 0,
            "backwards_step_clock_intervals": 0,
            "negative_step_clock_records": 0,
            "clock_relation_max_deviation_s": 0,
            "current_a": {"min": 0, "max": 0},
            "surface_temperature_c": {"final": 24.40456771850586},
        }
        for step in range(1, 7)
    ]
    return {
        "source": {
            "filename": k2.SOURCE_FILENAME,
            "sha256": k2.SOURCE_SHA256,
            "bytes": k2.SOURCE_BYTES,
        },
        "canonical_six_step_sequence": True,
        "contiguous_steps": phases,
        "measurement_clock_audit": {
            "backwards_date_intervals": 0,
            "date_test_clock_jumps_above_1s": 0,
            "max_relative_date_test_clock_discrepancy_s": 0.001,
        },
    }


@pytest.fixture
def inputs(monkeypatch):
    time = np.array([k2.OBSERVED_INTERVAL_S[0], 1000.0, 2000.0, k2.OBSERVED_INTERVAL_S[1]])
    observed = np.column_stack(
        (time, -(5 + time * 0.00001), 4.1 - 0.0004 * time, 297.6 + 0.002 * time)
    )
    # A synthetic trace is explicitly substituted. Production pins the real workbook-derived hash.
    monkeypatch.setattr(k2, "OBSERVED_SHA256", k2._observed_identity(observed))
    monkeypatch.setattr(k2, "PROTOCOL_SHA256", "a" * 64)
    report = inspection_report()
    monkeypatch.setattr(k2, "inspect_workbook", lambda *args: (copy.deepcopy(report), observed))
    manifest = {
        "files": [
            {"filename": "NMC_k1_1C_25degC.xlsx"},
            {
                "filename": k2.SOURCE_FILENAME,
                "size": k2.SOURCE_BYTES,
                "content_details": {"sha256_hash": k2.SOURCE_SHA256},
            },
        ]
    }
    prepared = k2.prepare_k2(Path("unused"), manifest)
    return prepared, manifest, report


def result_for(prepared, endpoint=None, mesh=80):
    observed, profile, config, _ = prepared
    endpoint = observed[-1, 0] if endpoint is None else endpoint
    time = np.unique(np.r_[0, observed[observed[:, 0] < endpoint, 0], endpoint])
    temperature = 297.6 + 0.002 * time
    temperature[0] = config.initial_temperature_k
    return SimulationResult(
        config=replace(config, mesh_points=mesh),
        time_s=time,
        voltage_v=4.1 - 0.0004 * time,
        capacity_ah=profile.charge_integral_ah(time),
        temperature_k=temperature,
        lithium_mol=np.ones(len(time)),
        heating_w=np.zeros(len(time)),
        cooling_w=np.zeros(len(time)),
        heat_capacity_j_k=None,
        termination="event: Minimum voltage [V]",
        physical_audit={"passed": True},
        parameter_fingerprint="explicitly-synthetic-no-solve",
        solver_cache_info={"profile_template_reused": False},
        current_protocol={
            "fingerprint_sha256": profile.fingerprint_sha256,
            "integration_schedule": "adaptive",
            "implicit_extrapolation": False,
            "solver_stops_at_profile_knots": False,
        },
    )


def evaluate(prepared, model=None, **kwargs):
    observed, profile, _, assumptions = prepared
    return k2.evaluate_k2(
        observed, profile, model or result_for(prepared), assumptions=assumptions, **kwargs
    )


def test_preparation_preserves_exact_all_knots_and_explicit_unobserved_gaps(inputs):
    prepared, _, _ = inputs
    observed, profile, config, assumptions = prepared
    np.testing.assert_array_equal(profile.time_s, np.r_[0, observed[:, 0], 6000])
    np.testing.assert_array_equal(profile.current_a[1:-1], -observed[:, 1])
    assert profile.current_a[0] == -observed[0, 1]
    assert profile.current_a[-1] == -observed[-1, 1]
    assert assumptions["missing_initial_interval_s"] == [0, 1.0003]
    assert assumptions["explicit_unobserved_continuation_s"] == [3435.7713, 6000]
    assert assumptions["initial_interval_is_measured"] is False
    assert assumptions["continuation_interval_is_measured"] is False
    assert assumptions["solver_profile_schedule"] == "adaptive"
    assert config.initial_temperature_k == 297.55456771850584
    assert config.ambient_temperature_k == 298.15
    assert config.heat_transfer_coefficient_w_m2_k == 15
    assert config.model == "DFN"
    assert config.parameter_set == "ORegan2022"
    assert config.thermal == "lumped"
    assert config.mesh_points == 80
    assert config.tolerance == 1e-7
    assert config.sample_period_s == 5
    assert assumptions["initial_concentrations_mol_m3"] == {
        "negative": 28866,
        "positive": 13975,
    }
    assert assumptions["parameter_fitting_performed"] is False


def test_missing_initial_charge_is_excluded_without_first_time_shift(inputs):
    prepared, _, _ = inputs
    report = evaluate(prepared)
    assert report["common_observed_interval_s"] == [1.0003, 3435.7713]
    assert report["capacity_relative_error"] == pytest.approx(0, abs=1e-14)
    assert report["energy_relative_error"] == pytest.approx(0, abs=1e-14)
    assert report["initial_assumed_charge_excluded_from_metrics_ah"] == pytest.approx(
        -prepared[0][0, 1] * 1.0003 / 3600
    )
    assert report["electrical_gates_passed"]
    assert report["source_window_empirical_qualification_passed"]
    assert not report["independent_validation_established"]


def test_early_cutoff_keeps_missing_capacity_and_energy_in_event_errors(inputs):
    prepared, _, _ = inputs
    report = evaluate(prepared, result_for(prepared, endpoint=2000))
    assert report["voltage_rmse_v"] == pytest.approx(0, abs=1e-14)
    assert report["capacity_relative_error"] > 0.4
    assert report["energy_relative_error"] > 0.35
    assert report["observed_time_coverage"] < 0.6
    assert not report["electrical_gates_passed"]
    assert not report["source_window_empirical_qualification_passed"]
    overlap = report["observed_window_diagnostics"]
    assert overlap["predicted_capacity_ah"] == pytest.approx(overlap["measured_capacity_ah"])
    assert not overlap["used_for_event_acceptance_gates"]


def test_late_cutoff_retains_tail_and_cannot_claim_empirical_pass(inputs):
    prepared, _, _ = inputs
    report = evaluate(prepared, result_for(prepared, endpoint=3450))
    assert report["common_observed_interval_s"] == [1.0003, 3435.7713]
    assert report["event_comparison_interval_s"] == [1.0003, 3450]
    assert report["unobserved_late_continuation_used_s"] == pytest.approx(14.2287)
    assert report["capacity_relative_error"] > 0
    assert report["energy_relative_error"] > 0
    assert report["electrical_gates_passed"]  # Small errors pass the mathematical gates only.
    assert report["event_metrics_conditional_on_post_observation_forcing"]
    assert not report["source_window_empirical_qualification_passed"]
    assert "unmeasured" in report["source_window_empirical_qualification_reasons"][0]


def test_long_late_cutoff_cannot_hide_event_error_by_cropping(inputs):
    prepared, _, _ = inputs
    report = evaluate(prepared, result_for(prepared, endpoint=5000))
    assert report["voltage_rmse_v"] == pytest.approx(0, abs=1e-14)
    assert report["capacity_relative_error"] > 0.4
    assert report["energy_relative_error"] > 0.3
    assert not report["electrical_gates"]["capacity"]
    assert not report["electrical_gates"]["energy"]


def test_temperature_proxy_compares_only_observed_overlap_and_has_separate_gates(inputs):
    prepared, _, _ = inputs
    model = result_for(prepared, endpoint=3450)
    model.temperature_k[-1] = 999
    report = evaluate(prepared, model)
    assert report["temperature_proxy_rmse_k"] == pytest.approx(0, abs=1e-12)
    assert report["temperature_domains"]["ranges"]["volume_average_prediction_c"][1] == (
        999 - 273.15
    )
    assert not report["temperature_domains"]["inside_all_listed_measurement_domains"]
    assert report["temperature_domain_trajectory_intervals_s"] == {
        "surface_measurement": [1.0003, 3435.7713],
        "volume_average_prediction": [0, 3450],
    }
    assert "full observed skin trajectory" in report["temperature_domains_scope"]
    assert "full model volume-average trajectory" in report["temperature_domains_scope"]
    assert report["event_metrics_conditional_on_post_observation_forcing"]
    assert not report["source_window_empirical_qualification_passed"]
    model = result_for(prepared)
    model.temperature_k += 6
    report = evaluate(prepared, model)
    assert report["electrical_gates_passed"]
    assert report["thermal_proxy_gates"] == {"rmse": False, "maximum_error": False}
    assert not report["independent_thermal_validation_established"]


def test_k2_labels_and_frozen_thresholds_contain_no_stale_k1_metadata(inputs, tmp_path):
    prepared, _, _ = inputs
    report = evaluate(prepared, residual_path=tmp_path / "k2-residual.csv")
    assert report["cell"] == "Stanford k2"
    assert report["source_filename"] == k2.SOURCE_FILENAME
    assert report["source_sha256"] == k2.SOURCE_SHA256
    assert report["protocol_sha256"] == "a" * 64
    assert report["selected_after_observations"]
    assert report["blinded"] is False
    assert "not blinded" in report["comparison_role"]
    assert "unrecorded age" in report["model"]["scope"]
    assert "freshness not established" in report["model"]["scope"]
    serialized = json.dumps(report)
    assert "k1" not in serialized
    assert "fresh LG M50" not in serialized
    assert "scheduling_addendum_sha256" not in report
    assert "memory_addendum_sha256" not in report
    thresholds = report["empirical_thresholds"]
    assert thresholds["voltage_rmse_v"] == 0.050
    assert thresholds["voltage_max_error_v"] == 0.300
    assert thresholds["capacity_relative_error"] == 0.05
    assert thresholds["energy_relative_error"] == 0.05
    assert thresholds["min_coverage"] == 0.95
    residual = np.loadtxt(tmp_path / "k2-residual.csv", delimiter=",", skiprows=1)
    np.testing.assert_array_equal(residual[:, 0], prepared[0][:, 0])


@pytest.mark.parametrize("mesh", [80, 120])
def test_only_declared_two_meshes_are_supported(inputs, mesh):
    prepared, _, _ = inputs
    assert evaluate(prepared, result_for(prepared, mesh=mesh))["electrical_gates_passed"]


@pytest.mark.parametrize(
    "change",
    [
        {"model": "SPMe"},
        {"parameter_set": "Chen2020"},
        {"thermal": "isothermal"},
        {"initial_temperature_k": 298.15},
        {"ambient_temperature_k": 297.15},
        {"heat_transfer_coefficient_w_m2_k": 16},
        {"current_a": 5.0},
        {"mesh_points": 40},
        {"tolerance": 1e-6},
        {"sample_period_s": 10},
        {"max_temperature_k": 330},
    ],
)
def test_rejects_changed_model_configuration(inputs, change):
    prepared, _, _ = inputs
    model = result_for(prepared)
    model.config = replace(model.config, **change)
    with pytest.raises(ValueError, match="config"):
        evaluate(prepared, model)


@pytest.mark.parametrize("field", ["sha256", "filename", "bytes"])
def test_rejects_wrong_source_identity(inputs, field):
    prepared, _, _ = inputs
    prepared[3]["source"][field] = "wrong"
    with pytest.raises(ValueError, match="source/protocol"):
        evaluate(prepared)


@pytest.mark.parametrize("field", ["cell", "protocol_sha256", "observed_trace_sha256"])
def test_rejects_cross_cell_or_changed_protocol_metadata(inputs, field):
    prepared, _, _ = inputs
    prepared[3][field] = "k1"
    with pytest.raises(ValueError, match="source/protocol"):
        evaluate(prepared)


def test_source_identity_is_pinned_against_cross_cell_arrays(inputs):
    prepared, _, _ = inputs
    prepared[0][1, 2] += 0.01
    with pytest.raises(ValueError, match="frozen Stanford k2 source"):
        evaluate(prepared)


def test_rejects_average_current_and_extra_hidden_current_knots(inputs):
    prepared, _, _ = inputs
    observed, profile, config, assumptions = prepared
    average = CurrentProfile([0, 6000], [config.current_a, config.current_a])
    extra_time = np.sort(np.r_[profile.time_s, 50.0])
    extra = CurrentProfile(extra_time, profile.value_at(extra_time))
    for invalid in (average, extra):
        with pytest.raises(ValueError, match="forcing"):
            k2.evaluate_k2(observed, invalid, result_for(prepared), assumptions=assumptions)


@pytest.mark.parametrize(
    "change",
    [
        {"fingerprint_sha256": "k1-profile"},
        {"integration_schedule": "all_knots"},
        {"implicit_extrapolation": True},
        {"solver_stops_at_profile_knots": True},
    ],
)
def test_rejects_wrong_model_forcing_identity_or_schedule(inputs, change):
    prepared, _, _ = inputs
    model = result_for(prepared)
    model.current_protocol.update(change)
    with pytest.raises(ValueError, match="current profile"):
        evaluate(prepared, model)


def test_rejects_profile_cache_cross_cell_reuse(inputs):
    prepared, _, _ = inputs
    model = result_for(prepared)
    model.solver_cache_info["profile_template_reused"] = True
    with pytest.raises(ValueError, match="reused across cells"):
        evaluate(prepared, model)


@pytest.mark.parametrize(
    "termination", ["final time", "event: Research temperature envelope", "not Minimum voltage"]
)
def test_wrong_termination_is_failed_not_a_voltage_event(inputs, termination):
    prepared, _, _ = inputs
    model = result_for(prepared)
    model.termination = termination
    report = evaluate(prepared, model)
    assert not report["electrical_gates_passed"]
    assert report["predicted_voltage_cutoff_time_s"] is None


def test_failed_physical_audit_cannot_pass(inputs):
    prepared, _, _ = inputs
    model = result_for(prepared)
    model.physical_audit["passed"] = False
    assert not evaluate(prepared, model)["electrical_gates_passed"]


@pytest.mark.parametrize(
    "field",
    [
        "exact_duplicate_times",
        "duplicate_time_conflicts",
        "backwards_step_clock_intervals",
        "negative_step_clock_records",
        "clock_relation_max_deviation_s",
    ],
)
def test_rejects_unqualified_clocks_in_any_source_phase(inputs, monkeypatch, field):
    prepared, manifest, report = inputs
    report["contiguous_steps"][5][field] = 2
    monkeypatch.setattr(k2, "inspect_workbook", lambda *args: (report, prepared[0]))
    with pytest.raises(ValueError, match="clocks"):
        k2.prepare_k2(Path("unused"), manifest)


@pytest.mark.parametrize(
    "field",
    [
        "backwards_date_intervals",
        "date_test_clock_jumps_above_1s",
        "max_relative_date_test_clock_discrepancy_s",
    ],
)
def test_rejects_unqualified_date_test_clock(inputs, monkeypatch, field):
    prepared, manifest, report = inputs
    report["measurement_clock_audit"][field] = 2
    monkeypatch.setattr(k2, "inspect_workbook", lambda *args: (report, prepared[0]))
    with pytest.raises(ValueError, match="clocks"):
        k2.prepare_k2(Path("unused"), manifest)


@pytest.mark.parametrize("phase", [0, 3, 5])
def test_requires_every_recorded_rest_to_have_zero_current(inputs, monkeypatch, phase):
    prepared, manifest, report = inputs
    report["contiguous_steps"][phase]["current_a"]["min"] = -0.001
    monkeypatch.setattr(k2, "inspect_workbook", lambda *args: (report, prepared[0]))
    with pytest.raises(ValueError, match="zero-current rest"):
        k2.prepare_k2(Path("unused"), manifest)


def test_missing_rest_and_changed_rest_temperature_rejected(inputs, monkeypatch):
    prepared, manifest, report = inputs
    report["contiguous_steps"].pop(3)
    monkeypatch.setattr(k2, "inspect_workbook", lambda *args: (report, prepared[0]))
    with pytest.raises(ValueError, match="six-phase"):
        k2.prepare_k2(Path("unused"), manifest)
    report = inspection_report()
    report["contiguous_steps"][3]["surface_temperature_c"]["final"] += 1
    with pytest.raises(ValueError, match="skin temperature"):
        k2.prepare_k2(Path("unused"), manifest)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "hash", "bytes"])
def test_manifest_must_select_exactly_one_checksum_pinned_k2(inputs, mutation):
    _, manifest, _ = inputs
    if mutation == "missing":
        manifest["files"].pop()
    elif mutation == "duplicate":
        manifest["files"].append(copy.deepcopy(manifest["files"][-1]))
    elif mutation == "hash":
        manifest["files"][-1]["content_details"]["sha256_hash"] = "wrong"
    else:
        manifest["files"][-1]["size"] += 1
    with pytest.raises(ValueError, match="Manifest"):
        k2.prepare_k2(Path("unused"), manifest)


@pytest.mark.parametrize("mutation", ["duplicate", "backwards", "shift", "positive_current", "nan"])
def test_invalid_observation_timestamps_and_sign_rejected(inputs, mutation):
    prepared, _, _ = inputs
    model = result_for(prepared)
    observed = prepared[0]
    if mutation == "duplicate":
        observed[1, 0] = observed[0, 0]
    elif mutation == "backwards":
        observed[1, 0] = -1
    elif mutation == "shift":
        observed[:, 0] -= observed[0, 0]
    elif mutation == "positive_current":
        observed[1, 1] *= -1
    else:
        observed[1, 2] = np.nan
    with pytest.raises(ValueError, match="trace|interval"):
        evaluate(prepared, model)


def test_protocol_must_be_frozen_before_preparation(inputs, monkeypatch):
    _, manifest, _ = inputs
    monkeypatch.setattr(k2, "PROTOCOL_SHA256", None)
    with pytest.raises(ValueError, match="not yet been frozen"):
        k2.prepare_k2(Path("unused"), manifest)


def test_protocol_checks_k2_complete_history_without_promoting_k6(tmp_path, monkeypatch):
    content = b"Synthetic frozen conditional protocol\n"
    monkeypatch.setattr(k2, "PROTOCOL_SHA256", hashlib.sha256(content).hexdigest())
    protocol = tmp_path / k2.PROTOCOL_PATH
    protocol.parent.mkdir(parents=True)
    protocol.write_bytes(content)
    history_path = tmp_path / k2.HISTORY_PATH
    history_path.parent.mkdir(parents=True)
    original = json.loads(Path(k2.HISTORY_PATH).read_text())
    history_path.write_bytes(Path(k2.HISTORY_PATH).read_bytes())
    contract_path = tmp_path / k2.INPUT_CONTRACT_PATH
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes(Path(k2.INPUT_CONTRACT_PATH).read_bytes())
    (tmp_path / "data/stanford-manifest.json").write_bytes(
        Path("data/stanford-manifest.json").read_bytes()
    )
    assert k2.verify_protocol(tmp_path)["cell_id"] == "k2"
    original["saved_report_analysis"]["histories"]["k2"]["history_qualified"] = False
    history_path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="history|chronology"):
        k2.verify_protocol(tmp_path)
    protocol.write_bytes(b"Changed protocol")
    with pytest.raises(ValueError, match="protocol changed"):
        k2.verify_protocol(tmp_path)


@pytest.mark.data
def test_real_k2_preparation_never_reuses_k1_selection():
    raw = Path("data/stanford/raw")
    if not (raw / k2.SOURCE_FILENAME).exists():
        pytest.skip("Pinned Stanford k2 workbook is not locally available")
    if k2.PROTOCOL_SHA256 is None:
        pytest.skip("K2 protocol has not yet been frozen")
    pytest.importorskip("openpyxl")
    observed, profile, config, assumptions = k2.prepare_k2(
        raw, json.loads(Path("data/stanford-manifest.json").read_text())
    )
    assert observed.shape == (3436, 4)
    assert tuple(observed[[0, -1], 0]) == (1.0003, 3435.7713)
    np.testing.assert_array_equal(profile.current_a[1:-1], -observed[:, 1])
    assert config.current_a == pytest.approx(5.000371049908912)
    assert config.initial_temperature_k == 297.55456771850584
    assert assumptions["source"]["filename"] == k2.SOURCE_FILENAME
    assert k2.verify_protocol(Path.cwd())["history_qualified"]
