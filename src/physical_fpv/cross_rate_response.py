"""Frozen finite-time response transfer across two currents and two specimens."""

import numpy as np

from physical_fpv.onset_response import curve, observed_response

LABELS = ("k1_1c", "k1_005c", "k2_1c", "k2_005c")


def compare_rates(records):
    if set(records) != set(LABELS):
        raise ValueError("Require exactly four frozen cell/rate records")
    loaded = {name: curve(records[name][1], 4) for name in LABELS}
    first = max(data[0, 0] for data in loaded.values())
    if first >= 2:
        raise ValueError("Common initial query must precede2s")
    times = np.array([first, 2.0, 5.0, 10.0])
    cases = {name: observed_response(records[name][0], loaded[name], times) for name in LABELS}
    for name, data in loaded.items():
        stop = int(np.searchsorted(data[:, 0], 10.0, side="left"))
        support = data[: stop + 1]
        cases[name]["onset_current_support"] = {
            "step_time_interval_s": [float(support[0, 0]), float(support[-1, 0])],
            "positive_current_min_a": float(min(-support[:, 2])),
            "positive_current_max_a": float(max(-support[:, 2])),
            "includes_first_sample_at_or_after_10s": True,
        }
    transfer = {}
    for cell in ("k1", "k2"):
        high, low = cases[cell + "_1c"], cases[cell + "_005c"]
        predicted = np.array(high["finite_time_apparent_response_ohm"]) * low["positive_current_a"]
        difference = np.array(low["voltage_fall_v"]) - predicted
        transfer[cell] = {
            "predicted_low_rate_fall_v": predicted.tolist(),
            "observed_minus_predicted_low_rate_fall_v": difference.tolist(),
            "relative_difference": [
                (float(d / p) if abs(p) > 1e-12 else None)
                for d, p in zip(difference, predicted, strict=True)
            ],
            "relative_denominator_guard_v": 1e-12,
            "low_minus_high_apparent_response_ohm": (
                np.array(low["finite_time_apparent_response_ohm"])
                - high["finite_time_apparent_response_ohm"]
            ).tolist(),
        }
    contrasts = {}
    for rate in ("1c", "005c"):
        one, two = cases["k1_" + rate], cases["k2_" + rate]
        contrasts[rate] = {
            "rest_anchor_difference_v": one["rest"]["endpoint_v"] - two["rest"]["endpoint_v"],
            "observed_fall_difference_v": (
                np.array(one["voltage_fall_v"]) - two["voltage_fall_v"]
            ).tolist(),
            "apparent_response_difference_ohm": (
                np.array(one["finite_time_apparent_response_ohm"])
                - two["finite_time_apparent_response_ohm"]
            ).tolist(),
            "skin_temperature_difference_k": (np.array(one["skin_k"]) - two["skin_k"]).tolist(),
        }
    predicted_delta = (
        np.array(transfer["k1"]["predicted_low_rate_fall_v"])
        - transfer["k2"]["predicted_low_rate_fall_v"]
    )
    return {
        "query_times_s": times.tolist(),
        "cases": cases,
        "transfer": transfer,
        "cell_contrasts_k1_minus_k2": contrasts,
        "predicted_low_rate_cell_fall_difference_v": predicted_delta.tolist(),
        "observed_minus_predicted_low_rate_cell_fall_difference_v": (
            np.array(contrasts["005c"]["observed_fall_difference_v"]) - predicted_delta
        ).tolist(),
        "interaction_low_minus_high_response_contrast_ohm": (
            np.array(contrasts["005c"]["apparent_response_difference_ohm"])
            - contrasts["1c"]["apparent_response_difference_ohm"]
        ).tolist(),
        "within_cell_low_minus_high_skin_temperature_k": {
            cell: (
                np.array(cases[cell + "_005c"]["skin_k"]) - cases[cell + "_1c"]["skin_k"]
            ).tolist()
            for cell in ("k1", "k2")
        },
        "statistical_acceptance_established": False,
        "contact_resistance_identified": False,
        "parameters_fitted": False,
        "physical_parameter_update": False,
    }
