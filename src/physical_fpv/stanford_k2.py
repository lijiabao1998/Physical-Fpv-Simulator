"""Frozen, explicitly conditional Stanford k2 comparison; no solves or fitting here.

The measured current has all original knots. Its two unmeasured extensions are
hypotheses, never observations. Event-based errors retain any early or late
cutoff; voltage and skin-proxy temperature errors use observed overlap only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from physical_fpv.core import ModelConfig, SimulationResult
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.stanford_benchmark import product_integral
from physical_fpv.stanford_data import inspect_workbook
from physical_fpv.thermal_benchmark import THERMAL_GATES, piecewise_error, temperature_domains

SOURCE_FILENAME = "NMC_k2_1C_25degC.xlsx"
SOURCE_SHA256 = "20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086"
SOURCE_BYTES = 1_802_458
OBSERVED_SHA256 = "eefce5eea77a1c3acc8c4f9b384f5bf8c32728d731bbc296f9df524146d9f1e7"
OBSERVED_INTERVAL_S = (1.0003, 3435.7713)
PROFILE_END_TIME_S = 6000.0
INITIAL_TEMPERATURE_K = 297.55456771850584
INITIAL_CONCENTRATIONS_MOL_M3 = {"negative": 28866.0, "positive": 13975.0}
PROFILE_SCHEDULE = "adaptive"
PROTOCOL_PATH = "docs/stanford-k2-prediction-protocol.md"
PROTOCOL_SHA256 = "24006e294ffd9db813e9f153695120ebdfef38a61d17408212401c12e9efd1cc"
INPUT_CONTRACT_PATH = "data/stanford-k2-pilot-input.json"
INPUT_CONTRACT_SHA256 = "0e0d8360fa87870f4103110c48e95f93774696e46046bc335309c7822c037477"
HISTORY_PATH = "docs/benchmarks/stanford-k2-k6-history-partial.json"
SELECTION_ROLE = (
    "exploratory conditional test; k2 selected after observing cohort boundaries and history; "
    "not blinded or an independent validation"
)
SCOPE = (
    "Stanford k2 published campaign history qualified; unrecorded age, storage and exposure "
    "unknown; freshness not established; not certified for FPV, abuse, aging or safety"
)


def _protocol_identity() -> str:
    if PROTOCOL_SHA256 is None:
        raise ValueError("Stanford k2 protocol has not yet been frozen")
    return PROTOCOL_SHA256


def _observed_identity(observed: np.ndarray) -> str:
    """Hash row-major float64 seconds, raw amperes, volts and converted kelvin."""
    return hashlib.sha256(np.asarray(observed, dtype="<f8").tobytes(order="C")).hexdigest()


def _validate_observed(observed: np.ndarray) -> np.ndarray:
    observed = np.asarray(observed, dtype=float)
    if (
        observed.ndim != 2
        or observed.shape[1] != 4
        or len(observed) < 2
        or not np.isfinite(observed).all()
        or np.any(np.diff(observed[:, 0]) <= 0)
        or np.any(observed[:, 1] >= 0)
        or np.any(observed[:, 2:] <= 0)
    ):
        raise ValueError("Invalid Stanford k2 observed trace or discharge-current sign")
    if tuple(observed[[0, -1], 0]) != OBSERVED_INTERVAL_S:
        raise ValueError("Frozen k2 commanded-time observed interval changed")
    if _observed_identity(observed) != OBSERVED_SHA256:
        raise ValueError("Observed trace differs from the frozen Stanford k2 source")
    return observed


def _profile(observed: np.ndarray) -> CurrentProfile:
    time, current = observed[:, 0], -observed[:, 1]
    return CurrentProfile(
        np.r_[0.0, time, PROFILE_END_TIME_S], np.r_[current[0], current, current[-1]]
    )


def _config(observed: np.ndarray) -> ModelConfig:
    time, current = observed[:, 0], -observed[:, 1]
    return ModelConfig(
        model="DFN",
        thermal="lumped",
        parameter_set="ORegan2022",
        initial_temperature_k=INITIAL_TEMPERATURE_K,
        heat_transfer_coefficient_w_m2_k=15,
        # Scalar is core's duration/envelope input, not the applied forcing.
        current_a=float(np.trapezoid(current, time) / (time[-1] - time[0])),
        ambient_temperature_k=298.15,
        mesh_points=80,
        tolerance=1e-7,
        sample_period_s=5,
    )


def _validate_inspection(report: dict) -> None:
    source = report["source"]
    if (
        source["filename"] != SOURCE_FILENAME
        or source["sha256"] != SOURCE_SHA256
        or source["bytes"] != SOURCE_BYTES
    ):
        raise ValueError("Frozen Stanford k2 measurement source changed")
    phases = report["contiguous_steps"]
    if not report["canonical_six_step_sequence"] or [p["step"] for p in phases] != list(
        range(1, 7)
    ):
        raise ValueError("Stanford k2 requires the qualified six-phase source protocol")
    clock = report["measurement_clock_audit"]
    discrepancy = clock["max_relative_date_test_clock_discrepancy_s"]
    if (
        clock["backwards_date_intervals"]
        or clock["date_test_clock_jumps_above_1s"]
        or not np.isfinite(discrepancy)
        or not 0 <= discrepancy <= 1
    ):
        raise ValueError("Stanford k2 measurement clocks are not qualified")
    for phase in phases:
        deviation = phase["clock_relation_max_deviation_s"]
        if (
            phase["exact_duplicate_times"]
            or phase["duplicate_time_conflicts"]
            or phase["backwards_step_clock_intervals"]
            or phase["negative_step_clock_records"]
            or not np.isfinite(deviation)
            or not 0 <= deviation <= 1
        ):
            raise ValueError("Stanford k2 source step clocks are not qualified")
        if phase["step"] in (1, 4, 6) and (
            phase["current_a"]["min"] != 0 or phase["current_a"]["max"] != 0
        ):
            raise ValueError("Stanford k2 rest phase is not zero-current rest")
    rest_temperature = phases[3]["surface_temperature_c"]["final"] + 273.15
    if rest_temperature != INITIAL_TEMPERATURE_K:
        raise ValueError("Frozen k2 final pre-rest skin temperature changed")


def prepare_k2(raw: Path, manifest: dict) -> tuple[np.ndarray, CurrentProfile, ModelConfig, dict]:
    """Inspect exactly k2's pinned workbook and preserve the commanded clock."""
    protocol_sha256 = _protocol_identity()
    entries = [e for e in manifest["files"] if e["filename"] == SOURCE_FILENAME]
    if (
        len(entries) != 1
        or entries[0]["size"] != SOURCE_BYTES
        or entries[0]["content_details"]["sha256_hash"] != SOURCE_SHA256
    ):
        raise ValueError("Manifest does not identify the single frozen Stanford k2 source")
    report, observed = inspect_workbook(raw, entries[0], manifest)
    _validate_inspection(report)
    if observed is None:
        raise ValueError("Stanford k2 source has no unique discharge")
    observed = _validate_observed(observed)
    profile, config = _profile(observed), _config(observed)
    config.validate()
    assumptions = {
        "cell": "Stanford k2",
        "source": report["source"],
        "protocol_sha256": protocol_sha256,
        "observed_trace_sha256": OBSERVED_SHA256,
        "observed_trace_hash_format": "C-order little-endian float64: step_s, raw_A, V, skin_K",
        "comparison_role": SELECTION_ROLE,
        "selected_after_observations": True,
        "blinded": False,
        "observed_interval_s": list(OBSERVED_INTERVAL_S),
        "missing_initial_interval_s": [0.0, OBSERVED_INTERVAL_S[0]],
        "initial_interval_current_assumption_a": float(profile.current_a[0]),
        "assumed_initial_charge_ah": profile.charge_integral_ah(OBSERVED_INTERVAL_S[0]),
        "initial_interval_is_measured": False,
        "initial_interval_bound_status": (
            "Declared time extent and first-current hypothesis, not an empirical current bound"
        ),
        "explicit_unobserved_continuation_s": [OBSERVED_INTERVAL_S[1], PROFILE_END_TIME_S],
        "continuation_current_assumption_a": float(profile.current_a[-1]),
        "continuation_interval_is_measured": False,
        "current_profile_sha256": profile.fingerprint_sha256,
        "current_interpolation": "all source samples; piecewise linear; no smoothing or averaging",
        "scalar_current_status": "duration/envelope metadata only; profile is actual forcing",
        "solver_profile_schedule": PROFILE_SCHEDULE,
        "initial_temperature_k": config.initial_temperature_k,
        "initial_temperature_source": (
            "final zero-current pre-rest skin temperature, assumed initially uniform"
        ),
        "initial_concentrations_mol_m3": dict(INITIAL_CONCENTRATIONS_MOL_M3),
        "initial_concentration_status": "published ORegan2022 values; no SOC or voltage fit",
        "cooling_coefficient_status": (
            "ORegan h=15 prior hypothesis; not identified for Stanford fixture"
        ),
        "ambient_temperature_status": (
            "nominal chamber setpoint 298.15 K; ambient sensor time series unavailable"
        ),
        "temperature_observable": "predicted volume average versus measured central skin proxy",
        "independent_thermal_validation_established": False,
        "parameter_fitting_performed": False,
        "scope": SCOPE,
    }
    return observed, profile, config, assumptions


def _validate_prediction(
    observed: np.ndarray, profile: CurrentProfile, model: SimulationResult, assumptions: dict
) -> None:
    source = assumptions.get("source", {})
    if (
        assumptions.get("cell") != "Stanford k2"
        or source.get("filename") != SOURCE_FILENAME
        or source.get("sha256") != SOURCE_SHA256
        or source.get("bytes") != SOURCE_BYTES
        or assumptions.get("protocol_sha256") != _protocol_identity()
        or assumptions.get("observed_trace_sha256") != OBSERVED_SHA256
    ):
        raise ValueError("Prediction source/protocol identity is not frozen Stanford k2")
    expected_profile = _profile(observed)
    if (
        profile.fingerprint_sha256 != expected_profile.fingerprint_sha256
        or assumptions.get("current_profile_sha256") != profile.fingerprint_sha256
    ):
        raise ValueError("Prediction forcing differs from exact k2 knots and declared extensions")
    config = model.config
    if config.mesh_points not in (80, 120) or config != replace(
        _config(observed), mesh_points=config.mesh_points
    ):
        raise ValueError("Model config differs from the frozen k2 DFN80/120 protocol")
    protocol = model.current_protocol or {}
    if (
        protocol.get("fingerprint_sha256") != profile.fingerprint_sha256
        or protocol.get("integration_schedule") != PROFILE_SCHEDULE
        or protocol.get("implicit_extrapolation") is not False
        or protocol.get("solver_stops_at_profile_knots") is not False
    ):
        raise ValueError("Model did not use the frozen k2 current profile and adaptive schedule")
    if model.solver_cache_info and model.solver_cache_info.get("profile_template_reused"):
        raise ValueError("Profile-specific model state must not be reused across cells")
    time = np.asarray(model.time_s)
    if (
        time.ndim != 1
        or len(time) < 2
        or not np.isfinite(time).all()
        or time[0] != 0
        or np.any(np.diff(time) <= 0)
        or time[-1] > profile.end_time_s
        or time[-1] <= observed[0, 0]
    ):
        raise ValueError("Invalid k2 model time coverage")
    for values in (model.voltage_v, model.temperature_k):
        values = np.asarray(values)
        if values.shape != time.shape or not np.isfinite(values).all():
            raise ValueError("Invalid k2 model observable samples")


def _predicted_energy(
    profile: CurrentProfile, model: SimulationResult, start: float, stop: float
) -> float:
    knots = np.unique(
        np.r_[
            start,
            model.time_s[(model.time_s > start) & (model.time_s < stop)],
            profile.time_s[(profile.time_s > start) & (profile.time_s < stop)],
            stop,
        ]
    )
    return (
        product_integral(
            knots, profile.value_at(knots), np.interp(knots, model.time_s, model.voltage_v)
        )
        / 3600
    )


def evaluate_k2(
    observed: np.ndarray,
    profile: CurrentProfile,
    model: SimulationResult,
    residual_path: Path | None = None,
    *,
    assumptions: dict,
) -> dict:
    """Score frozen inputs without mistaking an unobserved continuation for data.

    ``electrical_gates_passed`` reports the original mathematical thresholds.
    Source-window empirical qualification additionally requires zero late
    extrapolated forcing. Even a passing result remains exploratory/nonblind.
    """
    observed = _validate_observed(observed)
    _validate_prediction(observed, profile, model, assumptions)
    time, raw_current, voltage, skin_t = observed.T
    start, stop = float(time[0]), float(min(time[-1], model.time_s[-1]))
    endpoint = float(model.time_s[-1])
    common = np.unique(
        np.r_[
            start,
            time[(time > start) & (time < stop)],
            model.time_s[(model.time_s > start) & (model.time_s < stop)],
            stop,
        ]
    )
    predicted_v = np.interp(common, model.time_s, model.voltage_v)
    predicted_t = np.interp(common, model.time_s, model.temperature_k)
    measured_v = np.interp(common, time, voltage)
    measured_t = np.interp(common, time, skin_t)
    vrmse, vmax = piecewise_error(common, predicted_v - measured_v)
    trmse, tmax = piecewise_error(common, predicted_t - measured_t)
    observed_charge = float(np.trapezoid(-raw_current, time) / 3600)
    initial_charge = profile.charge_integral_ah(start)
    predicted_charge = profile.charge_integral_ah(endpoint) - initial_charge
    observed_energy = product_integral(time, -raw_current, voltage) / 3600
    predicted_energy = _predicted_energy(profile, model, start, endpoint)
    charge_error = abs(predicted_charge - observed_charge) / observed_charge
    energy_error = abs(predicted_energy - observed_energy) / observed_energy
    coverage = float((stop - start) / (time[-1] - time[0]))
    correct_event = model.termination == "event: Minimum voltage [V]"
    electrical = {
        "voltage_rmse": vrmse <= THERMAL_GATES["voltage_rmse_v"],
        "voltage_max": vmax <= THERMAL_GATES["voltage_max_error_v"],
        "capacity": charge_error <= THERMAL_GATES["capacity_relative_error"],
        "energy": energy_error <= THERMAL_GATES["energy_relative_error"],
        "coverage": coverage >= THERMAL_GATES["min_coverage"],
        "voltage_cutoff_reached": correct_event,
        "physical_audit": model.physical_audit.get("passed") is True,
    }
    late_duration = max(0.0, endpoint - float(time[-1]))
    mathematical_pass = bool(all(electrical.values()))
    source_window_pass = mathematical_pass and late_duration == 0
    model_metadata = model.metadata()
    model_metadata["scope"] = SCOPE
    model_metadata["initial_concentrations_mol_m3"] = dict(INITIAL_CONCENTRATIONS_MOL_M3)
    if residual_path is not None:
        residual_path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(
            residual_path,
            np.column_stack(
                (
                    common,
                    measured_v,
                    predicted_v,
                    predicted_v - measured_v,
                    measured_t,
                    predicted_t,
                    predicted_t - measured_t,
                )
            ),
            delimiter=",",
            comments="",
            header=(
                "time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v,"
                "measured_skin_k,predicted_average_k,temperature_proxy_error_k"
            ),
        )
    return {
        "cell": "Stanford k2",
        "source_filename": SOURCE_FILENAME,
        "source_sha256": SOURCE_SHA256,
        "source_bytes": SOURCE_BYTES,
        "observed_trace_sha256": OBSERVED_SHA256,
        "protocol_sha256": _protocol_identity(),
        "model": model_metadata,
        "comparison_role": SELECTION_ROLE,
        "selected_after_observations": True,
        "blinded": False,
        "fitting_performed": False,
        "assumptions": assumptions,
        "common_observed_interval_s": [start, stop],
        "voltage_rmse_v": vrmse,
        "voltage_max_absolute_error_v": vmax,
        "voltage_max_absolute_error_time_s": float(
            common[np.argmax(np.abs(predicted_v - measured_v))]
        ),
        "temperature_proxy_rmse_k": trmse,
        "temperature_proxy_max_absolute_error_k": tmax,
        "temperature_proxy_max_absolute_error_time_s": float(
            common[np.argmax(np.abs(predicted_t - measured_t))]
        ),
        "measured_observed_capacity_ah": observed_charge,
        "predicted_window_capacity_ah": predicted_charge,
        "capacity_relative_error": charge_error,
        "measured_observed_energy_wh": observed_energy,
        "predicted_window_energy_wh": predicted_energy,
        "energy_relative_error": energy_error,
        "event_comparison_interval_s": [start, endpoint],
        "event_metrics_conditional_on_post_observation_forcing": late_duration > 0,
        "event_metrics_scope": (
            "initial observed time to model endpoint, compared with entire measured discharge; "
            "early/late endpoint differences retained; late forcing is an unmeasured hypothesis"
        ),
        "observed_time_coverage": coverage,
        "measured_endpoint_time_s": float(time[-1]),
        "predicted_endpoint_time_s": endpoint,
        "predicted_voltage_cutoff_time_s": endpoint if correct_event else None,
        "unobserved_late_continuation_used_s": late_duration,
        "initial_assumed_charge_excluded_from_metrics_ah": initial_charge,
        "electrical_gates": electrical,
        "electrical_gates_passed": mathematical_pass,
        "electrical_gates_scope": (
            "conditional event-based mathematical gates; not a source-window empirical PASS"
            if late_duration > 0
            else "observed-window empirical thresholds under declared initial-state assumptions"
        ),
        "source_window_empirical_qualification_passed": source_window_pass,
        "source_window_empirical_qualification_reasons": (
            ["model event requires unmeasured post-observation current continuation"]
            if late_duration > 0
            else []
        )
        + [f"failed electrical gate: {name}" for name, passed in electrical.items() if not passed],
        "observed_window_diagnostics": {
            "interval_s": [start, stop],
            "predicted_capacity_ah": profile.charge_integral_ah(stop) - initial_charge,
            "measured_capacity_ah": float(np.trapezoid(profile.value_at(common), common) / 3600),
            "predicted_energy_wh": _predicted_energy(profile, model, start, stop),
            "measured_energy_wh": product_integral(common, profile.value_at(common), measured_v)
            / 3600,
            "used_for_event_acceptance_gates": False,
        },
        "thermal_proxy_gates": {"rmse": trmse <= 2, "maximum_error": tmax <= 5},
        "independent_thermal_validation_established": False,
        "independent_validation_established": False,
        "temperature_domains": temperature_domains(skin_t, model.temperature_k),
        "temperature_domains_scope": (
            "full observed skin trajectory and full model volume-average trajectory, "
            "including initial and late unobserved model intervals; applicability diagnostic, "
            "not an extension of measured temperature or the common-window residual metrics"
        ),
        "temperature_domain_trajectory_intervals_s": {
            "surface_measurement": [float(time[0]), float(time[-1])],
            "volume_average_prediction": [float(model.time_s[0]), endpoint],
        },
        "empirical_thresholds": dict(THERMAL_GATES),
    }


def verify_protocol(root: Path) -> dict:
    """Verify the new protocol and qualified k2 history; do not promote k6."""
    if hashlib.sha256((root / PROTOCOL_PATH).read_bytes()).hexdigest() != _protocol_identity():
        raise ValueError("Frozen Stanford k2 conditional protocol changed")
    if hashlib.sha256((root / INPUT_CONTRACT_PATH).read_bytes()).hexdigest() != (
        INPUT_CONTRACT_SHA256
    ):
        raise ValueError("Frozen Stanford k2 input contract changed")
    contract = json.loads((root / INPUT_CONTRACT_PATH).read_text())
    if (
        hashlib.sha256((root / "data/stanford-manifest.json").read_bytes()).hexdigest()
        != (contract["manifest_sha256"])
    ):
        raise ValueError("Frozen Stanford source manifest changed")
    if (
        hashlib.sha256((root / HISTORY_PATH).read_bytes()).hexdigest()
        != (contract["history_evidence_sha256"])
    ):
        raise ValueError("Frozen Stanford k2 history evidence changed")
    analysis = json.loads((root / HISTORY_PATH).read_text())["saved_report_analysis"]
    history = analysis["histories"]["k2"]
    target = [r for r in history["ordered_intervals"] if r["filename"] == SOURCE_FILENAME]
    if (
        history["cell_id"] != "k2"
        or history["target_filename"] != SOURCE_FILENAME
        or not history["complete"]
        or not history["history_qualified"]
        or not history["recorded_order_qualified"]
        or history["expected_files"] != 15
        or history["inspected_files"] != 15
        or history["missing_files"]
        or history["history_unresolved_reasons"]
        or history["overlaps"]
        or history["touching_boundaries"]
        or history["recorded_prior_high_rate_exposure"] is not False
        or history["qualified_earlier_high_rate_files"]
        or len(target) != 1
        or target[0]["source_sha256"] != SOURCE_SHA256
        or not target[0]["source_integrity_qualified"]
        or not target[0]["source_protocol_qualified"]
        or not target[0]["source_step_clock_qualified"]
        or not target[0]["clock_qualified"]
        or analysis["recorded_premise_status"] != "unresolved"
        or analysis["full_histories_qualified"] is not False
    ):
        raise ValueError("Frozen k2 chronology qualification or unresolved k6 status changed")
    return history
