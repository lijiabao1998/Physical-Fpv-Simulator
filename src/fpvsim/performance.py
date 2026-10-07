"""Design-level performance: hover, full throttle, hover endurance.

Definitions used throughout the reports:

* Hover: all rotors equal, total net thrust = weight. Net thrust is rotor
  thrust times the frame's thrust-interference factor (downwash blocked by
  the arms).
* Full throttle: duty = 1 on all motors, short punch from a rested pack
  (polarisation voltage v_rc = 0, so only R0 sags). Static, no forward speed.
* Hover endurance: constant hover from full charge until the first of
  (state of charge <= reserve) or (loaded cell voltage at the ESC <= minimum).
  This is an upper bound for real flights, which are never steady hover.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .battery import BatteryState
from .powertrain import OperatingPoint

if TYPE_CHECKING:  # design imports this module; avoid the cycle at runtime
    from .design import Aircraft


@dataclass(frozen=True)
class Metric:
    key: str
    title: str
    label: str  # short English label for charts
    unit: str  # display unit
    fmt: str


METRICS: dict[str, Metric] = {
    m.key: m
    for m in (
        Metric("auw", "全備重量", "All-up weight", "g", ".0f"),
        Metric("dry_mass", "不含電池重量", "Dry mass", "g", ".0f"),
        Metric("cg_offset", "重心與推力中心的水平偏移", "CG offset from thrust centre", "mm", ".1f"),
        Metric("thrust_to_weight", "靜態推重比（滿電、全油門）", "Static thrust-to-weight", "1", ".2f"),
        Metric("hover_duty", "懸停油門（馬達輸出，滿電）", "Hover motor output", "%", ".1f"),
        Metric("hover_throttle", "懸停油門（搖桿位置，扣除 idle）", "Hover stick throttle", "%", ".1f"),
        Metric("hover_rpm", "懸停轉速", "Hover speed", "rpm", ".0f"),
        Metric("hover_current", "懸停總電流（滿電）", "Hover current", "A", ".2f"),
        Metric("hover_power", "懸停電功率（滿電）", "Hover power", "W", ".1f"),
        Metric("hover_efficiency", "懸停效率", "Hover efficiency", "gf/W", ".2f"),
        Metric("endurance", "懸停續航", "Hover endurance", "min", ".2f"),
        Metric("peak_current", "全油門總電流（滿電）", "Full-throttle current", "A", ".1f"),
        Metric("peak_motor_current", "全油門單顆馬達電流", "Full-throttle motor current", "A", ".1f"),
        Metric("peak_c_rate", "全油門放電倍率 (C)", "Full-throttle C-rate", "1", ".0f"),
        Metric("full_throttle_cell_voltage", "全油門單芯電壓（滿電）", "Full-throttle cell voltage", "V", ".2f"),
        Metric("tip_mach", "全油門槳尖馬赫數", "Full-throttle tip Mach", "1", ".3f"),
        Metric("disk_loading", "懸停槳盤負載", "Hover disk loading", "Pa", ".1f"),
    )
}


def source_resistance(ac: "Aircraft") -> float:
    return ac.battery.r0 + ac.harness_resistance


def hover_point(ac: "Aircraft", state: BatteryState = BatteryState()) -> OperatingPoint | None:
    thrust = ac.weight / (ac.powertrain.n_rotors * ac.thrust_interference)
    return ac.powertrain.for_thrust(thrust, state.source_voltage(ac.battery), source_resistance(ac), ac.env.rho)


def full_throttle_point(ac: "Aircraft", state: BatteryState = BatteryState()) -> OperatingPoint | None:
    return ac.powertrain.at_duty(1.0, state.source_voltage(ac.battery), source_resistance(ac), ac.env.rho)


@dataclass(frozen=True)
class EnduranceResult:
    t: np.ndarray  # s
    soc: np.ndarray
    v_cell: np.ndarray  # loaded cell voltage at the ESC, V
    i_bus: np.ndarray  # A
    duty: np.ndarray
    endurance: float  # s
    reason: str  # reserve_soc, min_cell_voltage, cannot_hover or t_max

    REASONS_ZH = {
        "reserve_soc": "達到保留電量",
        "min_cell_voltage": "負載下單芯電壓達到下限",
        "cannot_hover": "電壓不足以懸停",
        "t_max": "達到模擬時間上限",
    }

    @property
    def reason_zh(self) -> str:
        return self.REASONS_ZH[self.reason]


def hover_endurance(ac: "Aircraft", dt: float = 1.0, t_max: float = 7200.0) -> EnduranceResult:
    reserve = ac.criteria.reserve_soc
    v_min = ac.criteria.min_cell_voltage
    series = ac.battery.series
    state = BatteryState()
    rows: list[tuple[float, float, float, float, float]] = []
    t = 0.0
    reason, t_end = "t_max", t_max
    while t <= t_max:
        op = hover_point(ac, state)
        if op is None:
            reason, t_end = "cannot_hover", t
            break
        v_cell = op.v_bus / series
        if state.soc <= reserve or v_cell <= v_min:
            t_end, reason = _crossing(rows, t, state.soc, v_cell, reserve, v_min)
            break
        rows.append((t, state.soc, v_cell, op.i_bus, op.duty))
        state = state.step(ac.battery, op.i_bus, dt)
        t += dt
    arr = np.array(rows) if rows else np.zeros((0, 5))
    return EnduranceResult(arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4], t_end, reason)


def _crossing(rows, t, soc, v_cell, reserve, v_min) -> tuple[float, str]:
    """Linearly interpolate when the first criterion was crossed in the last step."""
    if not rows:
        return 0.0, "reserve_soc" if soc <= reserve else "min_cell_voltage"
    t0, soc0, v0 = rows[-1][0], rows[-1][1], rows[-1][2]
    candidates = []
    if soc <= reserve:
        candidates.append(((soc0 - reserve) / (soc0 - soc), "reserve_soc"))
    if v_cell <= v_min:
        candidates.append(((v0 - v_min) / (v0 - v_cell), "min_cell_voltage"))
    frac, reason = min(candidates)
    return t0 + frac * (t - t0), reason


def evaluate(ac: "Aircraft", dt: float = 1.0) -> dict[str, float]:
    """All design metrics in SI units. Infeasible ones are NaN."""
    nan = math.nan
    mp = ac.mass_props
    n = ac.powertrain.n_rotors
    battery_mass = sum(item.mass for item in ac.items if item.group == "battery")
    hover = hover_point(ac)
    full = full_throttle_point(ac)
    endurance = hover_endurance(ac, dt=dt)
    capacity_ah = ac.battery.capacity / 3600.0

    return {
        "auw": mp.mass,
        "dry_mass": mp.mass - battery_mass,
        "cg_offset": float(np.linalg.norm((mp.cg - ac.thrust_centroid)[:2])),
        "thrust_to_weight": n * full.thrust * ac.thrust_interference / ac.weight if full else nan,
        "hover_duty": hover.duty if hover else nan,
        "hover_throttle": max(0.0, (hover.duty - ac.motor_idle) / (1.0 - ac.motor_idle)) if hover else nan,
        "hover_rpm": hover.omega if hover else nan,
        "hover_current": hover.i_bus if hover else nan,
        "hover_power": hover.p_bus if hover else nan,
        "hover_efficiency": ac.weight / hover.p_bus if hover else nan,
        "endurance": endurance.endurance,
        "peak_current": full.i_bus if full else nan,
        "peak_motor_current": full.i_motor if full else nan,
        "peak_c_rate": full.i_bus / capacity_ah if full else nan,
        "full_throttle_cell_voltage": full.v_bus / ac.battery.series if full else nan,
        "tip_mach": ac.powertrain.prop.tip_mach(full.omega, ac.env.speed_of_sound) if full else nan,
        "disk_loading": ac.weight / (n * ac.powertrain.prop.disk_area),
    }


@dataclass(frozen=True)
class RatingCheck:
    title: str
    value: float  # SI
    limit: float  # SI
    unit: str
    note: str

    @property
    def passes(self) -> bool:
        return math.isfinite(self.value) and self.value <= self.limit


def rating_checks(ac: "Aircraft") -> list[RatingCheck]:
    """Full-throttle currents against component ratings."""
    full = full_throttle_point(ac)
    i_motor = full.i_motor if full else math.nan
    i_bus = full.i_bus if full else math.nan
    pt = ac.powertrain
    return [
        RatingCheck("馬達峰值電流", i_motor, pt.motor.max_current, "A", "馬達額定峰值電流（通常容許數秒）"),
        RatingCheck("ESC 單路電流", i_motor, pt.esc.max_current, "A", "ESC 額定連續電流；全油門通常是短時間"),
        RatingCheck(
            "電池放電電流",
            i_bus,
            ac.battery.max_current,
            "A",
            "以標示 C 數計算；C 數多為行銷數字，實際能力以內阻與溫升判斷",
        ),
    ]
