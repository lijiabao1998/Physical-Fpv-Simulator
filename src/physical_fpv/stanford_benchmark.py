"""Prospective single-record comparison with explicit unobserved input intervals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from physical_fpv.core import ModelConfig, SimulationResult
from physical_fpv.current_profile import CurrentProfile
from physical_fpv.stanford_data import inspect_pilot
from physical_fpv.thermal_benchmark import THERMAL_GATES, piecewise_error, temperature_domains

PROTOCOL_SHA256 = "009f64f52b889c56fed15e085007a82c24ed58e8b926c49e5f964f9e185f53b0"
SCHEDULING_ADDENDUM_SHA256 = "d3ce12b439053f88df50f8cc6448c318c139a302cd3421755a505aa6dec1d27e"
MEMORY_ADDENDUM_SHA256 = "20a232abec94c8210e48efdb24bad18471a6664a29f0a4fee1adf19aab22bc28"
SOURCE_SHA256 = "b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6"


def prepare_pilot(
    raw: Path, manifest: dict
) -> tuple[np.ndarray, CurrentProfile, ModelConfig, dict]:
    report, observed = inspect_pilot(raw, manifest)
    if report["source"]["sha256"] != SOURCE_SHA256:
        raise ValueError("The preselected Stanford k1 measurement source changed")
    if observed is None or not report["canonical_six_step_sequence"]:
        raise ValueError("Pilot requires the qualified six-phase source protocol")
    clock = report["measurement_clock_audit"]
    if clock["backwards_date_intervals"] or clock["max_relative_date_test_clock_discrepancy_s"] > 1:
        raise ValueError("Measurement clocks are not qualified")
    for phase in report["contiguous_steps"]:
        if (
            phase["exact_duplicate_times"]
            or phase["backwards_step_clock_intervals"]
            or phase["negative_step_clock_records"]
            or phase["clock_relation_max_deviation_s"] > 1
        ):
            raise ValueError("Source protocol clock needs inspection before prediction")
    rest = next(s for s in report["contiguous_steps"] if s["step"] == 4)
    if rest["current_a"]["min"] != 0 or rest["current_a"]["max"] != 0:
        raise ValueError("Pre-discharge source phase is not zero-current rest")
    time, raw_current, _, _ = observed.T
    current = -raw_current
    if time[0] != 1.0006 or time[-1] >= 6000 or np.any(np.diff(time) <= 0):
        raise ValueError("Frozen observed interval changed")
    profile = CurrentProfile(np.r_[0, time, 6000], np.r_[current[0], current, current[-1]])
    mean = float(np.trapezoid(current, time) / (time[-1] - time[0]))
    config = ModelConfig(
        parameter_set="ORegan2022",
        thermal="lumped",
        current_a=mean,
        ambient_temperature_k=298.15,
        initial_temperature_k=rest["surface_temperature_c"]["final"] + 273.15,
        heat_transfer_coefficient_w_m2_k=15,
        mesh_points=80,
        tolerance=1e-7,
        sample_period_s=5,
    )
    assumptions = {
        "source": report["source"],
        "observed_interval_s": [float(time[0]), float(time[-1])],
        "missing_initial_interval_s": [0, float(time[0])],
        "initial_interval_current_assumption_a": float(current[0]),
        "assumed_initial_charge_ah": profile.charge_integral_ah(time[0]),
        "initial_interval_is_measured": False,
        "initial_interval_bound_status": (
            "Declared time extent and CC hypothesis, not an empirical current bound"
        ),
        "explicit_unobserved_continuation_s": [float(time[-1]), 6000.0],
        "continuation_current_assumption_a": float(current[-1]),
        "current_profile_sha256": profile.fingerprint_sha256,
        "current_interpolation": "all source samples; piecewise linear; no smoothing",
        "initial_temperature_source": (
            "final zero-current pre-rest skin temperature, assumed initially uniform"
        ),
        "cooling_coefficient_status": (
            "ORegan h=15 prior hypothesis; not identified for Stanford fixture"
        ),
        "ambient_temperature_status": (
            "nominal chamber setpoint; ambient sensor time series unavailable"
        ),
        "temperature_observable": "predicted volume average versus measured central skin proxy",
        "independent_thermal_validation_established": False,
        "parameter_fitting_performed": False,
    }
    return observed, profile, config, assumptions


def product_integral(time: np.ndarray, first: np.ndarray, second: np.ndarray) -> float:
    """Exact integral of two piecewise-linear signals sharing time knots."""
    time, first, second = (np.asarray(a, dtype=float) for a in (time, first, second))
    if (
        time.ndim != 1
        or first.shape != time.shape
        or second.shape != time.shape
        or len(time) < 2
        or np.any(np.diff(time) <= 0)
        or not all(np.isfinite(a).all() for a in (time, first, second))
    ):
        raise ValueError("Invalid piecewise-linear product inputs")
    df, ds = np.diff(first), np.diff(second)
    return float(
        np.sum(
            np.diff(time)
            * (first[:-1] * second[:-1] + (first[:-1] * ds + second[:-1] * df) / 2 + df * ds / 3)
        )
    )


def evaluate_pilot(
    observed: np.ndarray,
    profile: CurrentProfile,
    model: SimulationResult,
    residual_path: Path | None = None,
) -> dict:
    observed = np.asarray(observed, dtype=float)
    if (
        observed.ndim != 2
        or observed.shape[1] != 4
        or len(observed) < 2
        or not np.isfinite(observed).all()
        or np.any(np.diff(observed[:, 0]) <= 0)
    ):
        raise ValueError("Invalid Stanford observed trace")
    t, raw_current, voltage, skin_t = observed.T
    if not np.allclose(profile.value_at(t), -raw_current, rtol=0, atol=1e-12):
        raise ValueError("Prediction current profile differs from measured amperes")
    if (
        model.current_protocol is None
        or model.current_protocol["fingerprint_sha256"] != profile.fingerprint_sha256
    ):
        raise ValueError("Model did not use the declared current profile")
    start, stop = max(t[0], model.time_s[0]), min(t[-1], model.time_s[-1])
    if start != t[0] or stop <= start:
        raise ValueError("Model does not cover the first observed time")
    common = np.unique(
        np.r_[
            start,
            t[(t > start) & (t < stop)],
            model.time_s[(model.time_s > start) & (model.time_s < stop)],
            stop,
        ]
    )
    predicted_v = np.interp(common, model.time_s, model.voltage_v)
    predicted_t = np.interp(common, model.time_s, model.temperature_k)
    measured_v, measured_t = np.interp(common, t, voltage), np.interp(common, t, skin_t)
    vrmse, vmax = piecewise_error(common, predicted_v - measured_v)
    trmse, tmax = piecewise_error(common, predicted_t - measured_t)
    q_observed = float(np.trapezoid(-raw_current, t) / 3600)
    q_predicted = profile.charge_integral_ah(model.time_s[-1]) - profile.charge_integral_ah(start)
    if q_observed <= 0:
        raise ValueError("Observed discharge capacity must be positive")
    q_error = abs(q_predicted - q_observed) / q_observed
    observed_energy = product_integral(t, -raw_current, voltage) / 3600
    energy_knots = np.unique(
        np.r_[
            start,
            model.time_s[(model.time_s > start)],
            profile.time_s[(profile.time_s > start) & (profile.time_s < model.time_s[-1])],
        ]
    )
    predicted_energy = (
        product_integral(
            energy_knots,
            profile.value_at(energy_knots),
            np.interp(energy_knots, model.time_s, model.voltage_v),
        )
        / 3600
    )
    energy_error = abs(predicted_energy - observed_energy) / observed_energy
    coverage = float((stop - start) / (t[-1] - t[0]))
    correct_event = "Minimum voltage" in model.termination
    electrical = {
        "voltage_rmse": vrmse <= THERMAL_GATES["voltage_rmse_v"],
        "voltage_max": vmax <= THERMAL_GATES["voltage_max_error_v"],
        "capacity": q_error <= THERMAL_GATES["capacity_relative_error"],
        "energy": energy_error <= THERMAL_GATES["energy_relative_error"],
        "coverage": coverage >= THERMAL_GATES["min_coverage"],
        "voltage_cutoff_reached": correct_event,
        "physical_audit": model.physical_audit["passed"],
    }
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
            header="time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v,measured_skin_k,predicted_average_k,temperature_proxy_error_k",
        )
    return {
        "cell": "Stanford k1",
        "source_sha256": SOURCE_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "scheduling_addendum_sha256": SCHEDULING_ADDENDUM_SHA256,
        "memory_addendum_sha256": MEMORY_ADDENDUM_SHA256,
        "model": model.metadata(),
        "comparison_role": (
            "preselected external-source pilot; no new fit; not a blinded six-cell validation"
        ),
        "fitting_performed": False,
        "common_observed_interval_s": [float(start), float(stop)],
        "voltage_rmse_v": vrmse,
        "voltage_max_absolute_error_v": vmax,
        "temperature_proxy_rmse_k": trmse,
        "temperature_proxy_max_absolute_error_k": tmax,
        "measured_observed_capacity_ah": q_observed,
        "predicted_window_capacity_ah": q_predicted,
        "capacity_relative_error": q_error,
        "measured_observed_energy_wh": observed_energy,
        "predicted_window_energy_wh": predicted_energy,
        "energy_relative_error": energy_error,
        "observed_time_coverage": coverage,
        "measured_endpoint_time_s": float(t[-1]),
        "predicted_endpoint_time_s": float(model.time_s[-1]),
        "predicted_voltage_cutoff_time_s": float(model.time_s[-1]) if correct_event else None,
        "unobserved_late_continuation_used_s": max(0.0, float(model.time_s[-1] - t[-1])),
        "initial_assumed_charge_excluded_from_metrics_ah": profile.charge_integral_ah(start),
        "electrical_gates": electrical,
        "electrical_gates_passed": bool(all(electrical.values())),
        "thermal_proxy_gates": {"rmse": trmse <= 2, "maximum_error": tmax <= 5},
        "independent_thermal_validation_established": False,
        "temperature_domains": temperature_domains(skin_t, model.temperature_k),
        "empirical_thresholds": THERMAL_GATES,
    }


def verify_protocol(root: Path) -> dict:
    path = root / "docs/stanford-validation-protocol.md"
    if hashlib.sha256(path.read_bytes()).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Frozen Stanford prediction protocol changed")
    addendum = root / "docs/stanford-scheduling-addendum.md"
    if hashlib.sha256(addendum.read_bytes()).hexdigest() != SCHEDULING_ADDENDUM_SHA256:
        raise ValueError("Frozen Stanford scheduling addendum changed")
    memory = root / "docs/stanford-memory-addendum.md"
    if hashlib.sha256(memory.read_bytes()).hexdigest() != MEMORY_ADDENDUM_SHA256:
        raise ValueError("Frozen Stanford native-audit addendum changed")
    chronology = json.loads((root / "docs/benchmarks/stanford-k1-chronology.json").read_text())
    if (
        not chronology["recorded_order_qualified"]
        or not chronology["complete"]
        or chronology["provisional_earlier_high_rate_files"]
    ):
        raise ValueError("Frozen target chronology qualification changed")
    return chronology
