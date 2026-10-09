"""Cross-cell transfer of the frozen finite-time response comparison."""

import numpy as np

from physical_fpv.onset_response import brackets, curve, observed_response, query


def cross_cell_comparison(k1_rest, k1_load, k1_model, k2_rest, k2_load, k2_model):
    """Compare observed anchors/falls using only saved terminal voltage and temperature."""
    k1_load, k2_load = curve(k1_load, 4), curve(k2_load, 4)
    k1_model, k2_model = curve(k1_model, 3), curve(k2_model, 3)
    first = max(k1_load[0, 0], k2_load[0, 0], k1_model[0, 0], k2_model[0, 0])
    if first >= 2:
        raise ValueError("Common initial query must precede2s")
    times = np.array([first, 2.0, 5.0, 10.0])
    cases = {}
    for name, rest, load, model in (
        ("k1", k1_rest, k1_load, k1_model),
        ("k2", k2_rest, k2_load, k2_model),
    ):
        observed = observed_response(rest, load, times)
        saved = query(model, times)
        cases[name] = {
            "observed": observed,
            "model_terminal_v": saved[:, 0].tolist(),
            "model_bulk_temperature_k": saved[:, 1].tolist(),
            "terminal_residual_v": (saved[:, 0] - observed["voltage_v"]).tolist(),
            "model_query_brackets": brackets(model, times),
        }
    one, two = cases["k1"], cases["k2"]
    anchor = one["observed"]["rest"]["endpoint_v"] - two["observed"]["rest"]["endpoint_v"]
    model_delta = np.array(one["model_terminal_v"]) - two["model_terminal_v"]
    fall_delta = np.array(one["observed"]["voltage_fall_v"]) - two["observed"]["voltage_fall_v"]
    error_delta = np.array(one["terminal_residual_v"]) - two["terminal_residual_v"]
    closure = float(max(abs(error_delta - (model_delta - anchor + fall_delta))))
    if closure > 1e-12:
        raise ValueError("Cross-cell terminal/anchor/fall identity failed")
    return {
        "query_times_s": times.tolist(),
        "cases": cases,
        "delta_direction": "k1_minus_k2",
        "delta_rest_anchor_v": anchor,
        "delta_model_terminal_v": model_delta.tolist(),
        "delta_observed_voltage_fall_v": fall_delta.tolist(),
        "delta_terminal_residual_v": error_delta.tolist(),
        "arithmetic_closure_max_v": closure,
        "measured_skin_temperature_difference_k": (
            np.array(one["observed"]["skin_k"]) - two["observed"]["skin_k"]
        ).tolist(),
        "model_bulk_temperature_difference_k": (
            np.array(one["model_bulk_temperature_k"]) - two["model_bulk_temperature_k"]
        ).tolist(),
        "same_absolute_soc_established": False,
        "shared_physical_resistance_identified": False,
        "unsaved_internal_states_inferred": False,
    }
