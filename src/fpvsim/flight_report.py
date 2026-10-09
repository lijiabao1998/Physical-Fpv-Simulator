"""Stage 6 flight-test report: what happened in a flight, and whether the
models stayed inside the range where they can be trusted."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import __version__, plots
from . import flightanalysis as fa
from .blackbox import FlightLog
from .design import Build
from .flightcontroller import FcConfig
from .report import git_version, md_table, rel_path
from .rotor_ff import CLASSICAL_LIMIT

AXES = ("roll", "pitch", "yaw")
AXIS_ZH = {"roll": "滾轉", "pitch": "俯仰", "yaw": "偏航"}

# Validity envelope of the flight models (see docs/models.md)
DESCENT_LIMIT = 0.5  # axial descent speed / hover induced velocity: wake re-ingestion, vortex ring risk
MACH_LIMIT = 0.70


@dataclass(frozen=True)
class Excursion:
    title: str
    fraction: float
    first: float | None  # s
    note: str


def _excursion(t: np.ndarray, mask: np.ndarray, title: str, note: str) -> Excursion:
    idx = np.nonzero(mask)[0]
    return Excursion(title, float(mask.mean()), float(t[idx[0]]) if len(idx) else None, note)


def envelope(log: FlightLog, j_max: float, oblique: bool = False) -> list[Excursion]:
    """Excursions out of the models' validity range. ``oblique``: the rotors use
    the oblique-flow tables (rotor_ff.py) rather than the axial curves."""
    t = log.time
    if oblique:
        wake = _excursion(t, log["descent_ratio"] > DESCENT_LIMIT,
                          f"渦環狀態區（軸向下降 > {DESCENT_LIMIT:g} 倍懸停誘導速度，且水平速度低於懸停誘導速度）",
                          "平均誘導速度用經驗曲線（Leishman），平均推力的不確定度較大；推力脈動（propwash）未建模")
        table = _excursion(t, log["rotor_off_design"] > 0.5,
                           f"槳在低轉速高速狀態（前進比 μ 或入流比 |λ| > {CLASSICAL_LIMIT:g}，以槳尖速度計）",
                           "葉片大部分失速或逆流，槳力來自平板失速模型，只能定性參考；常見於收油後的高速俯衝或爬升滑行")
    else:
        wake = _excursion(t, log["descent_ratio"] > DESCENT_LIMIT,
                          f"下降進入自身尾流（下降速度 > {DESCENT_LIMIT:g} 倍懸停誘導速度）",
                          "動量理論在此失效，渦環狀態與 propwash 未建模；這段的推力與抖動不可信")
        table = _excursion(t, log["max_advance_ratio"] >= j_max, f"前進比超出槳係數表（J ≥ {j_max:g}）",
                           "槳係數以表格最後一點外插，推力估計不可信")
    return [
        wake,
        table,
        _excursion(t, log["tip_mach"] > MACH_LIMIT, f"槳尖馬赫數 > {MACH_LIMIT:g}", "未計入壓縮性，推力與扭矩偏樂觀"),
        _excursion(t, log["saturated"] > 0.5, "混控飽和", "馬達已到 0% 或 100%，姿態控制能力受限；不是模型問題，是飛行限制"),
        _excursion(t, log["on_ground"] > 0.5, "接觸地面", "接地模型為簡化的彈簧阻尼與庫侖摩擦"),
        _excursion(t, log["ground_effect"] > 1.02, "地面效應區（推力增加 > 2%）",
                   "Cheeseman–Bennett 單槳模型；多旋翼槳與槳之間的干擾未建模"),
    ]


def wind_text(meta: dict) -> str:
    w = meta.get("wind") or {}
    if not w or w.get("speed_m_s", 0.0) <= 0.0:
        return "無風"
    text = (f"{w['speed_m_s']:.1f} m/s（{w['ref_height_m']:g} m 高），來自 {w['from_deg']:.0f}°，"
            f"對數風剖面 z0 = {w['roughness_m']:g} m")
    if w.get("turbulence"):
        from .wind import dryden_scales

        sigma_w = dryden_scales(6.1, w["w20_m_s"])[5]
        text += f"；Dryden 紊流（6.1 m 風速 {w['w20_m_s']:.1f} m/s，垂直強度 σ_w = {sigma_w:.2f} m/s）"
    else:
        text += "；無紊流"
    return text


def summary(log: FlightLog, cells: int) -> list[tuple[str, str]]:
    t = log.time
    speed = np.sqrt(log["vel_n"] ** 2 + log["vel_e"] ** 2 + log["vel_d"] ** 2)
    horiz = np.hypot(log["vel_n"], log["vel_e"])
    tilt = np.degrees(np.arccos(np.clip(np.cos(np.radians(log["att_roll"])) * np.cos(np.radians(log["att_pitch"])), -1, 1)))
    energy = float(np.trapezoid(log["vbat"] * log["current"], t)) / 3600.0
    alt = log["alt"]
    return [
        ("飛行時間", f"{t[-1]:.1f} s"),
        ("最大速度（三維 / 水平）", f"{speed.max():.1f} / {horiz.max():.1f} m/s（{speed.max() * 3.6:.0f} / {horiz.max() * 3.6:.0f} km/h）"),
        ("最大爬升 / 下降速度", f"{(-log['vel_d']).max():.1f} / {log['vel_d'].max():.1f} m/s"),
        ("高度範圍（起始 {:.0f} m）".format(alt[0]), f"{alt.min():.1f} – {alt.max():.1f} m"),
        ("最大傾角", f"{tilt.max():.0f}°"),
        ("最大角速度（滾轉 / 俯仰 / 偏航）", " / ".join(f"{np.abs(log['rate_' + a]).max():.0f}" for a in AXES) + " deg/s"),
        ("最低單芯電壓（ESC 端）", f"{log['vbat'].min() / cells:.2f} V"),
        ("最大 / 最小電流", f"{log['current'].max():.0f} / {log['current'].min():.0f} A（負值為煞車回充）"),
        ("用電量", f"{log['mah'][-1]:.0f} mAh，{energy:.2f} Wh"),
        ("剩餘電量", f"{100 * log['soc'][-1]:.0f}%"),
        ("電池溫度（起飛 → 最高）", f"{log['batt_temp'][0]:.1f} → {log['batt_temp'].max():.1f} °C"),
    ] + ([
        ("風（記錄值，水平平均 / 最大）", f"{np.hypot(log['wind_n'], log['wind_e']).mean():.1f} / "
                                     f"{np.hypot(log['wind_n'], log['wind_e']).max():.1f} m/s，垂直 ±{np.abs(log['wind_d']).max():.1f} m/s"),
        ("空速（平均 / 最大）", f"{log['airspeed'].mean():.1f} / {log['airspeed'].max():.1f} m/s"),
    ] if np.any(log["wind_n"] != 0.0) or np.any(log["wind_e"] != 0.0) or np.any(log["wind_d"] != 0.0) else [])


def generate(build: Build, cfg: FcConfig, log: FlightLog, title: str, out_dir: Path, j_max: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    oblique = build.prop_blade is not None
    log.write_csv(out_dir / "flight_log.csv")
    t = log.time
    cells = build.battery_series
    plots.trajectory(t, log["pos_n"], log["pos_e"], log["alt"], out_dir / "trajectory.png")
    plots.timeseries(
        [
            {
                "title": f"{axis.capitalize()} rate",
                "ylabel": "deg/s",
                "series": [("setpoint", t, log[f"setpoint_{axis}"]), ("gyro (filtered)", t, log[f"gyro_{axis}"])],
            }
            for axis in AXES
        ]
        + [{"title": "Attitude", "ylabel": "deg", "series": [(a, t, log[f"att_{a}"]) for a in AXES]}],
        out_dir / "rates.png",
    )
    n = len([c for c in log.columns if c.startswith("rpm_")])
    plots.timeseries(
        [
            {"title": "Motor output", "ylabel": "%", "series": [(f"M{i + 1}", t, log[f"motor_{i}"]) for i in range(n)], "ylim": (0, 105)},
            {"title": "Rotor speed", "ylabel": "rpm", "series": [(f"M{i + 1}", t, log[f"rpm_{i}"]) for i in range(n)]},
            {"title": "Motor phase current (averaged)", "ylabel": "A", "series": [(f"M{i + 1}", t, log[f"motor_current_{i}"]) for i in range(n)]},
        ],
        out_dir / "motors.png",
    )
    plots.timeseries(
        [
            {"title": "Cell voltage at the ESC", "ylabel": "V", "series": [("vbat / cell", t, log["vbat"] / cells)]},
            {"title": "Battery current", "ylabel": "A", "series": [("current", t, log["current"])], "refs": [(0.0, "")]},
            {"title": "Charge used", "ylabel": "mAh", "series": [("mAh", t, log["mah"])]},
        ],
        out_dir / "power.png",
    )
    windy = bool(np.any(log["wind_n"] != 0.0) or np.any(log["wind_e"] != 0.0) or np.any(log["wind_d"] != 0.0))
    if windy:
        plots.timeseries(
            [
                {"title": "Wind at the aircraft (mean + turbulence)", "ylabel": "m/s",
                 "series": [("north", t, log["wind_n"]), ("east", t, log["wind_e"]), ("down", t, log["wind_d"])]},
                {"title": "Airspeed", "ylabel": "m/s", "series": [("airspeed", t, log["airspeed"])]},
            ],
            out_dir / "wind.png",
        )
    plots.timeseries(
        [
            {"title": "Descent into own wake", "ylabel": "v_descent / v_i", "series": [("descent ratio", t, log["descent_ratio"])],
             "refs": [(DESCENT_LIMIT, "model limit")]},
            {"title": "Edgewise advance ratio (worst rotor)", "ylabel": "mu", "series": [("mu", t, log["max_edgewise_ratio"])],
             "refs": [(CLASSICAL_LIMIT, "flat-plate regime")], "ylim": (0, 2)} if oblique else
            {"title": "Advance ratio (worst rotor)", "ylabel": "J", "series": [("J", t, log["max_advance_ratio"])],
             "refs": [(j_max, "end of prop table")]},
            {"title": "Tip Mach number", "ylabel": "Mach", "series": [("Mach", t, log["tip_mach"])], "refs": [(MACH_LIMIT, "model limit")]},
        ],
        out_dir / "validity.png",
    )

    md: list[str] = []
    add = md.append
    add(f"# 飛行測試報告：{title}\n")
    add("> 由 `fpvsim fly` 自動產生。原始 log 在 `flight_log.csv`（欄位格式見 docs/flight-sim.md）。\n")
    add(md_table(["項目", "內容"], [
        ["機體", f"{build.name}（`{rel_path(build.path, Path.cwd())}`）"],
        ["飛控設定", f"{cfg.name}（`{cfg.id}`）"],
        ["輸入", f"`{log.meta.get('input')}`"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
        ["輸入檔雜湊", f"`{log.meta.get('input_hash')}`"],
        ["隨機種子", str(log.meta.get("seed"))],
        ["風", wind_text(log.meta)],
        ["地面效應", "計入（Cheeseman–Bennett）" if log.meta.get("ground_effect", True) else "關閉"],
        ["更新率", f"物理 {log.meta['physics_rate_hz']:g} Hz，陀螺儀 {log.meta['gyro_rate_hz']:g} Hz，PID {log.meta['pid_rate_hz']:g} Hz，記錄 {log.meta['log_rate_hz']:g} Hz"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    add(md_table(["項目", "數值"], [list(r) for r in summary(log, cells)]))
    add("")
    crashed = log.meta.get("crashed")
    add(f"- 觸地最大速度 {log.meta.get('max_contact_speed_m_s', 0.0):.2f} m/s，"
        f"{'**判定為墜機**' if crashed else '未墜機'}（門檻 3 m/s）。")
    add("")
    add("![Trajectory](trajectory.png)\n")

    add("## 1. 姿態控制\n")
    rows = []
    for axis in AXES:
        sp, gy = log[f"setpoint_{axis}"], log[f"gyro_{axis}"]
        rows.append([AXIS_ZH[axis], f"{fa.tracking_rms(sp, gy):.1f} deg/s", f"{1000 * fa.latency(sp, gy, log.rate):.0f} ms",
                     f"{np.abs(sp).max():.0f} deg/s"])
    add(md_table(["軸", "追蹤誤差 (RMS)", "延遲（互相關）", "最大命令角速度"], rows))
    add("")
    add("![Rates](rates.png)\n")

    add("## 2. 馬達與動力\n")
    add("![Motors](motors.png)\n")
    add("![Power](power.png)\n")
    if windy:
        add("![Wind](wind.png)\n")

    add("## 3. 模型適用範圍監測\n")
    add("模擬器會記錄飛行是否離開物理模型的適用範圍。超出範圍的片段，數值只能當作定性參考。\n")
    add(md_table(["狀況", "時間占比", "首次發生", "影響"], [
        [e.title, f"{e.fraction:.1%}", "—" if e.first is None else f"{e.first:.2f} s", e.note] for e in envelope(log, j_max, oblique)
    ]))
    add("")
    add("![Validity](validity.png)\n")

    add("## 4. 這次模擬沒有包含的東西\n")
    if oblique:
        add("- 渦環狀態只模擬平均誘導速度（經驗曲線）；推力脈動與 propwash 抖動不模擬")
    else:
        add("- 下降進入自身尾流時的渦環狀態與 propwash 抖動（只監測，不模擬）")
    add("- 機架彈性與共振；振動只進入陀螺儀量測，不影響剛體運動")
    add("- 紊流的空間變化（各顆槳感受到的陣風相同，沒有旋轉紊流分量）；懸停時凍結紊流假設不成立")
    if oblique:
        add("- 槳的斜向氣流係數以剛性與自由揮舞兩個極限混合（`prop.flap_fraction`），尚未用風洞數據確認")
    else:
        add("- 槳在斜向氣流中的非軸向效應（只計入軸向前進比與槳盤阻力）")
    add("- 自動測試飛手只是測試工具，不代表人類飛手的反應與習慣")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
