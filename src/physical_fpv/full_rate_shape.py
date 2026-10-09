"""Measured capacity and shape descriptors without inferred state or parameter fits."""

import numpy as np

from physical_fpv.contrast_persistence import charge_coordinates, checked_trace, time_at_charge

LABELS = ("k1_005c", "k1_1c", "k2_005c", "k2_1c")


def measured_summary(values):
    x = checked_trace(values, 4)
    charge = charge_coordinates(x)
    dt = np.diff(x[:, 0])
    duration = float(x[-1, 0] - x[0, 0])
    return {
        "rows": len(x),
        "recorded_step_time_interval_s": [float(x[0, 0]), float(x[-1, 0])],
        "observed_duration_s": duration,
        "observed_charge_ah": float(charge[-1]),
        "observed_charge_over_nominal_4_85ah": float(charge[-1] / 4.85),
        "missing_initial_charge_known": False,
        "omitted_command_interval_s": [0.0, float(x[0, 0])],
        "current_a": {
            "minimum": float(np.min(x[:, 1])),
            "maximum": float(np.max(x[:, 1])),
            "time_weighted_mean": float(np.sum(dt * (x[:-1, 1] + x[1:, 1]) / 2) / duration),
        },
        "voltage_v": {
            "first": float(x[0, 2]),
            "last": float(x[-1, 2]),
            "minimum": float(np.min(x[:, 2])),
            "maximum": float(np.max(x[:, 2])),
        },
        "skin_temperature_k": {
            "first": float(x[0, 3]),
            "last": float(x[-1, 3]),
            "minimum": float(np.min(x[:, 3])),
            "maximum": float(np.max(x[:, 3])),
        },
        "last_voltage_minus_nominal_cutoff_v": float(x[-1, 2] - 2.5),
        "exact_cutoff_crossing_verified": False,
        "state_of_health_identified": False,
    }


def differences(values):
    unavailable = {}

    def pair(a, b, label):
        if a in values and b in values:
            return values[a] - values[b]
        unavailable[label] = "One or both required records lack support"
        return None

    within_rate = {
        rate: pair("k1_" + rate, "k2_" + rate, "rate_" + rate) for rate in ("005c", "1c")
    }
    within_cell = {
        cell: pair(cell + "_005c", cell + "_1c", "cell_" + cell) for cell in ("k1", "k2")
    }
    interaction = closure = None
    if all(name in values for name in LABELS):
        interaction = within_rate["005c"] - within_rate["1c"]
        closure = interaction - (within_cell["k1"] - within_cell["k2"])
    else:
        unavailable["interaction"] = "All four records required"
    return {
        "specimen_k1_minus_k2": within_rate,
        "within_specimen_low_minus_high": within_cell,
        "rate_interaction": interaction,
        "identity_closure": closure,
        "unavailable_reasons": unavailable,
    }


def evaluate(cases, descriptors):
    if set(cases) != set(LABELS) or set(descriptors) != {"k1", "k2"}:
        raise ValueError("Exactly four records and two frozen descriptors required")
    if not np.isfinite(list(descriptors.values())).all():
        raise ValueError("Nonfinite descriptor")
    summaries = {name: measured_summary(cases[name]) for name in LABELS}
    charge_contrasts = differences({name: summaries[name]["observed_charge_ah"] for name in LABELS})
    points = []
    for q in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
        records, unavailable = {}, {}
        for name in LABELS:
            x = checked_trace(cases[name], 4)
            if q > summaries[name]["observed_charge_ah"]:
                unavailable[name] = "Target exceeds observed discharged charge"
                continue
            t = time_at_charge(x, q)
            current, voltage, skin = [float(np.interp(t, x[:, 0], x[:, k])) for k in (1, 2, 3)]
            records[name] = {
                "time_s": t,
                "current_a": current,
                "voltage_v": voltage,
                "skin_temperature_k": skin,
                "descriptive_w_v": voltage + current * descriptors[name[:2]],
            }
        row = {
            "conditional_charge_ah": q,
            "records": records,
            "unavailable_reasons": unavailable,
            "all_four_supported": not unavailable,
        }
        row["contrasts"] = {
            key: differences({name: records[name][key] for name in records})
            for key in ("voltage_v", "descriptive_w_v", "skin_temperature_k")
        }
        for key in ("voltage_v", "descriptive_w_v"):
            closure = row["contrasts"][key]["identity_closure"]
            if closure is not None and abs(closure) > 1e-12:
                raise ValueError("Voltage contrast identity failed")
        points.append(row)
    return {
        "record_summaries": summaries,
        "observed_charge_contrasts_ah": charge_contrasts,
        "frozen_descriptors_ohm": dict(descriptors),
        "conditional_charge_points": points,
    }
