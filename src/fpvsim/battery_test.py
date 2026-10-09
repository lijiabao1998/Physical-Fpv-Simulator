"""Virtual battery test bench: a hybrid pulse power characterisation (HPPC).

Mirrors a real bench test in a thermal chamber: the pack sits at a set
temperature (no self-heating), a programmable load draws a sequence of
current steps, and time, current, voltage and temperature are logged with
instrument noise. The CSV uses the "name [unit]" header convention that
sysid.py reads, so virtual and real test data go through the same analysis
(``fpvsim fit-battery``).

Protocol, at each state-of-charge level from full down to ``soc_min``:

    rest (long enough to relax)  ->  discharge pulse  ->  rest (relaxation)
    ->  constant-current discharge to the next level

The relaxed voltage before each pulse gives the open-circuit voltage at that
state of charge; the instant step at the pulse edges gives R0; the slow
part of the pulse and of the relaxation gives R1 and tau1.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from .battery import Battery, BatteryState


@dataclass(frozen=True)
class HppcProtocol:
    pulse_c: float = 5.0  # pulse current as a multiple of capacity (C-rate)
    pulse_s: float = 30.0
    rest_before_s: float = 300.0  # relaxation before each pulse (OCV reading)
    rest_after_s: float = 120.0
    discharge_c: float = 1.0
    soc_step: float = 0.1
    soc_min: float = 0.1
    sample_rate: float = 10.0  # Hz
    voltage_noise: float = 0.002  # V, 1 sigma
    current_noise: float = 0.02  # A, 1 sigma


COLUMNS = (("time", "s"), ("current", "A"), ("voltage", "V"), ("temperature", "degC"))


def run_hppc(battery: Battery, temperature: float, protocol: HppcProtocol = HppcProtocol(),
             seed: int = 1) -> dict[str, np.ndarray]:
    """Simulate the test; returns SI arrays (time, current, voltage, temperature).

    The chamber holds the pack at ``temperature`` (K), so the thermal model is
    switched off and the resistances are those at that temperature."""
    held = replace(battery, heat_capacity=0.0)
    rng = np.random.default_rng(seed)
    dt = 1.0 / protocol.sample_rate
    i_pulse = protocol.pulse_c * battery.capacity / 3600.0
    i_dis = protocol.discharge_c * battery.capacity / 3600.0
    schedule: list[tuple[float, float]] = []  # (duration, current)
    soc = 1.0
    level = 1.0
    while level >= protocol.soc_min - 1e-9:
        schedule += [(protocol.rest_before_s, 0.0), (protocol.pulse_s, i_pulse), (protocol.rest_after_s, 0.0)]
        soc -= i_pulse * protocol.pulse_s / battery.capacity
        level = round(level - protocol.soc_step, 10)
        if level < protocol.soc_min - 1e-9:
            break
        schedule.append(((soc - level) * battery.capacity / i_dis, i_dis))
        soc = level
    state = BatteryState(1.0, 0.0, temperature)
    t_out, i_out, v_out = [], [], []
    t = 0.0
    for duration, current in schedule:
        steps = int(round(duration / dt))
        for _ in range(steps):
            r0 = held.r0_at(temperature)
            v = state.source_voltage(held) - current * r0
            t_out.append(t)
            i_out.append(current)
            v_out.append(v)
            state = state.step(held, current, dt)
            t += dt
    n = len(t_out)
    return {
        "time": np.array(t_out),
        "current": np.array(i_out) + rng.normal(0.0, protocol.current_noise, n),
        "voltage": np.array(v_out) + rng.normal(0.0, protocol.voltage_noise, n),
        "temperature": np.full(n, temperature),
    }


def write_csv(data: dict[str, np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"{name} [{unit}]" for name, unit in COLUMNS])
        temp_c = data["temperature"] - 273.15
        for k in range(len(data["time"])):
            w.writerow([f"{data['time'][k]:.2f}", f"{data['current'][k]:.4f}", f"{data['voltage'][k]:.4f}",
                        f"{temp_c[k]:.2f}"])
