"""Virtual wind-tunnel report (``fpvsim tunnel``) and the balance-data
identification report (``fpvsim fit-tunnel``)."""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import __version__, plots
from .design import Build
from .report import git_version, md_table, measurement_method, rel_path
from .tunnel import (CruiseEndurance, PolarPoint, RotorPoint, TrimCurve, Tunnel, cruise_endurance, drag_polar,
                     rotor_sweep, trim_curve)
from .tunnel_fit import TunnelFit, frame_values
from .uncertainty import MonteCarloResult, TornadoBar, monte_carlo, tornado

DEG = 180.0 / math.pi
POLAR_ALPHAS = np.radians([-10.0, 0.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0])
POLAR_SPEED = 15.0
DISK_ALPHAS = np.radians([0.0, 15.0, 30.0, 60.0, 90.0])
ROTOR_SPEEDS = np.arange(0.0, 30.0001, 2.0)

METRICS = {  # key: (title, unit, scale, format)
    "v_best_endurance": ("續航最久的速度（最低功率）", "m/s", 1.0, "{:.1f}"),
    "v_best_range": ("航程最遠的速度（最低功率 ÷ 速度）", "m/s", 1.0, "{:.1f}"),
    "v_max": ("最高平飛速度（滿電，全油門）", "m/s", 1.0, "{:.1f}"),
    "tilt_10": ("10 m/s 配平傾角", "°", DEG, "{:.1f}"),
    "tilt_20": ("20 m/s 配平傾角", "°", DEG, "{:.1f}"),
    "power_hover": ("懸停功率", "W", 1.0, "{:.0f}"),
    "power_10": ("10 m/s 功率", "W", 1.0, "{:.0f}"),
    "power_20": ("20 m/s 功率", "W", 1.0, "{:.0f}"),
}


def trim_metrics(ac, soc: float = 1.0) -> dict[str, float]:
    tun = Tunnel(ac, soc)
    curve = trim_curve(tun)
    by_speed = {round(p.speed, 6): p for p in curve.points}
    nan = math.nan
    v_e, v_r = curve.best_speeds() if len(curve.points) > 2 else (nan, nan)
    return {
        "v_best_endurance": v_e, "v_best_range": v_r, "v_max": curve.v_max,
        "tilt_10": by_speed[10.0].tilt if 10.0 in by_speed else nan,
        "tilt_20": by_speed[20.0].tilt if 20.0 in by_speed else nan,
        "power_hover": by_speed[0.0].p_bus if 0.0 in by_speed else nan,
        "power_10": by_speed[10.0].p_bus if 10.0 in by_speed else nan,
        "power_20": by_speed[20.0].p_bus if 20.0 in by_speed else nan,
    }


@dataclass
class TunnelStudy:
    build: Build
    tunnel: Tunnel
    polar_off: list[PolarPoint]
    polar_stopped: list[PolarPoint]
    alpha_off: list[PolarPoint]  # alpha sweep at POLAR_SPEED
    alpha_stopped: list[PolarPoint]
    rotor: list[RotorPoint]
    curve: TrimCurve
    cruise: list[CruiseEndurance]
    nominal: dict[str, float]
    mc: MonteCarloResult | None
    bars: dict[str, list[TornadoBar]]
    soc: float
    seed: int


def run_study(build: Build, samples: int = 200, seed: int = 1, soc: float = 1.0) -> TunnelStudy:
    ac = build.realize()
    tun = Tunnel(ac, soc)
    polar_off = drag_polar(tun, [5.0, 10.0, 15.0, 20.0, 30.0], [0.0], "off")
    polar_stopped = drag_polar(tun, [5.0, 10.0, 15.0, 20.0, 30.0], [0.0], "stopped")
    alpha_off = drag_polar(tun, [POLAR_SPEED], POLAR_ALPHAS, "off")
    alpha_stopped = drag_polar(tun, [POLAR_SPEED], POLAR_ALPHAS, "stopped")
    rotor = rotor_sweep(tun, tun.hover.omega, ROTOR_SPEEDS, DISK_ALPHAS)
    curve = trim_curve(tun)
    cruise = [cruise_endurance(tun, p.speed, p.x) for p in curve.points]
    nominal = trim_metrics(ac, soc)
    mc = monte_carlo(build, samples, seed, lambda a: trim_metrics(a, soc)) if samples > 0 else None
    _, bars = tornado(build, ["tilt_20", "v_best_range", "power_10"], lambda a: trim_metrics(a, soc))
    return TunnelStudy(build, tun, polar_off, polar_stopped, alpha_off, alpha_stopped, rotor, curve, cruise, nominal, mc,
                       bars, soc, seed)


def _fmt(key: str, value: float) -> str:
    title, unit, scale, fmt = METRICS[key]
    return "—" if not math.isfinite(value) else f"{fmt.format(value * scale)} {unit}"


def generate(study: TunnelStudy, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    b, tun, ac = study.build, study.tunnel, study.tunnel.ac
    rho = tun.rho
    curve = study.curve
    pts = curve.points
    v = np.array([p.speed for p in pts])

    # figures -------------------------------------------------------------
    plots.xy_panels([
        {"title": f"Drag area vs angle of attack ({POLAR_SPEED:g} m/s)", "xlabel": "alpha (nose down) [deg]",
         "ylabel": "D / (0.5 rho V^2) [cm^2]",
         "series": [("props removed", [p.alpha * DEG for p in study.alpha_off], [p.cda * 1e4 for p in study.alpha_off]),
                    ("props stopped", [p.alpha * DEG for p in study.alpha_stopped], [p.cda * 1e4 for p in study.alpha_stopped])]},
        {"title": "Pitching moment about the CG", "xlabel": "alpha (nose down) [deg]", "ylabel": "M_y [N mm]",
         "series": [("props removed", [p.alpha * DEG for p in study.alpha_off], [p.reading.moment[1] * 1e3 for p in study.alpha_off]),
                    ("props stopped", [p.alpha * DEG for p in study.alpha_stopped],
                     [p.reading.moment[1] * 1e3 for p in study.alpha_stopped])], "refs": [(0.0, "")]},
    ], out_dir / "polar.png")
    if study.rotor:
        t0 = study.rotor[0].thrust
        q0 = study.rotor[0].torque
        panels = []
        for key, title, ylabel, scale in (("thrust", "Thrust at hover rpm", "T / T_hover", 1.0 / t0),
                                          ("h_force", "Rotor drag (in-plane force H)", "H [N]", 1.0),
                                          ("torque", "Shaft torque", "Q / Q_hover", 1.0 / q0)):
            series = []
            for a in DISK_ALPHAS:
                sel = [r for r in study.rotor if abs(r.disk_alpha - a) < 1e-9]
                series.append((f"disk {a * DEG:.0f} deg", [r.speed for r in sel], [getattr(r, key) * scale for r in sel]))
            panels.append({"title": title, "xlabel": "Air speed [m/s]", "ylabel": ylabel, "series": series})
        plots.xy_panels(panels, out_dir / "rotor.png", ncols=3, panel_size=(3.6, 3.0))
    plots.xy_panels([
        {"title": "Trim tilt", "xlabel": "Speed [m/s]", "ylabel": "Tilt [deg]", "series": [("tilt", v, [p.tilt * DEG for p in pts])]},
        {"title": "Throttle", "xlabel": "Speed [m/s]", "ylabel": "Duty [%]",
         "series": [("collective", v, [100 * p.collective for p in pts]), ("highest motor", v, [100 * max(p.duties) for p in pts])],
         "refs": [(100.0, "full throttle")]},
        {"title": "Drag budget along the flight path", "xlabel": "Speed [m/s]", "ylabel": "Drag [N]",
         "series": [("airframe", v, [p.body_drag for p in pts]), ("rotors (H)", v, [p.rotor_drag for p in pts])]},
        {"title": "Battery output power", "xlabel": "Speed [m/s]", "ylabel": "Power [W]",
         "series": [("power", v, [p.p_bus for p in pts])],
         "vrefs": [(x, lab) for x, lab in zip(curve.best_speeds(), ("min power", "min P/V"))]},
    ], out_dir / "trim.png")
    cr = study.cruise
    plots.xy_panels([
        {"title": "Endurance at constant speed", "xlabel": "Speed [m/s]", "ylabel": "Time [min]",
         "series": [("endurance", [c.speed for c in cr], [c.time / 60 for c in cr])]},
        {"title": "Range at constant speed", "xlabel": "Speed [m/s]", "ylabel": "Range [km]",
         "series": [("range", [c.speed for c in cr], [c.distance / 1000 for c in cr])]},
    ], out_dir / "cruise.png")

    # markdown ------------------------------------------------------------
    md: list[str] = []
    add = md.append
    add(f"# 虛擬風洞報告：{b.name}\n")
    add("> 由 `fpvsim tunnel` 自動產生。對象是飛行模擬使用的同一個模型（`dynamics.py`、`rotor_ff.py`），"
        "所以這裡的數字就是模擬飛行時的空氣動力。方法見 docs/tunnel.md。\n")
    add(md_table(["項目", "內容"], [
        ["機體", f"{b.name}（`{rel_path(b.path, Path.cwd())}`）"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(b.path.parent)}`"],
        ["輸入檔雜湊", f"`{b.input_hash()[:16]}`"],
        ["空氣", f"密度 {rho:.4f} kg/m³（{ac.env.altitude:g} m，{ac.env.temperature - 273.15:.1f} °C）"],
        ["全備重量", f"{ac.mass_props.mass * 1000:.0f} g"],
        ["電池狀態", f"SoC {study.soc:.0%}，起始 {ac.battery_start_temperature - 273.15:.0f} °C"],
        ["槳的模型", "斜向氣流葉素模型（rotor_ff.py）" if tun.model.rotor is not None else "軸向係數表 + 動量理論槳盤阻力（沒有槳葉幾何）"],
        ["蒙地卡羅", f"{study.mc.n} 組，種子 {study.seed}" if study.mc else "未執行"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    v_e, v_r = curve.best_speeds()
    ce = _interp_cruise(cr, v_e)
    crr = _interp_cruise(cr, v_r)
    rows = []
    for key in METRICS:
        nominal = study.nominal[key]
        if study.mc:
            lo, med, hi = study.mc.percentiles(key)
            interval = f"{_fmt(key, lo)} – {_fmt(key, hi)}（中位數 {_fmt(key, med)}）"
            infeasible = study.mc.infeasible_fraction(key)
            if infeasible > 0:
                interval += f"；{infeasible:.0%} 樣本無解"
        else:
            interval = "—"
        rows.append([METRICS[key][0], _fmt(key, nominal), interval])
    add(md_table(["項目", "標稱值", "90% 區間（蒙地卡羅）"], rows))
    add("")
    add(f"- 以標稱值計，最省電的速度 {v_e:.1f} m/s 可飛約 {ce[0] / 60:.1f} 分鐘；航程最遠的速度 {v_r:.1f} m/s 約 {crr[1] / 1000:.1f} km"
        f"（定速平飛，從滿電飛到 {ac.criteria.reserve_soc:.0%} 保留電量或電壓下限，見第 5 節）。")
    if curve.v_max_point is not None:
        vp = curve.v_max_point
        add(f"- 最高平飛速度 {curve.v_max:.1f} m/s（{curve.v_max * 3.6:.0f} km/h）時傾角 {vp.tilt * DEG:.0f}°、"
            f"電池輸出 {vp.p_bus:.0f} W（{vp.i_bus:.0f} A）；這是滿電、靜止空氣中的值，電壓下降後會降低。")
    add("")

    add("## 1. 試驗設定\n")
    add("- 天平量測點在重心，力為機體軸（前、右、下），力矩為對重心的機體軸力矩；升力、阻力、側力是同一個力在風軸的分量。")
    add("- 攻角 α 以機頭向下為正（前飛時的前傾），側滑角 β 以風從右方來為正。自由流均勻；真實風洞的洞壁、阻塞與支架修正屬於量測端，不在模型內。")
    add("- 槳的狀態：拆槳（只量機身與零件）、停轉（槳固定不轉）、固定轉速（馬達維持該轉速所需的油門）、配平（第 4 節）。")
    add("- 停轉的槳由斜向氣流模型計算（失速後的平板模型）。" if tun.model.rotor is not None else "- 沒有槳葉幾何：停轉時不計槳的阻力。")
    add("")

    add("## 2. 機身阻力極曲線\n")
    add("阻力面積 D/(½ρV²)，攻角 0° 時各風速：\n")
    add(md_table(["風速 m/s"] + [f"{p.speed:g}" for p in study.polar_off],
                 [["拆槳 cm²"] + [f"{p.cda * 1e4:.1f}" for p in study.polar_off],
                  ["停轉 cm²"] + [f"{p.cda * 1e4:.1f}" for p in study.polar_stopped]]))
    spread = max(p.cda for p in study.polar_stopped) / min(p.cda for p in study.polar_stopped) - 1.0
    add(f"\n拆槳時阻力與速度平方成正比，阻力面積不隨風速變化；停轉的槳在這些風速之間差 {spread:.1%}。以下攻角掃描取 {POLAR_SPEED:g} m/s。\n")
    rows = []
    for po, ps in zip(study.alpha_off, study.alpha_stopped):
        rows.append([f"{po.alpha * DEG:.0f}°", f"{po.cda * 1e4:.1f}", f"{ps.cda * 1e4:.1f}",
                     f"{po.reading.lift:+.2f}", f"{po.reading.moment[1] * 1e3:+.1f}", f"{ps.reading.moment[1] * 1e3:+.1f}"])
    add(md_table(["攻角", "拆槳 cm²", "停轉 cm²", "拆槳升力 N", "拆槳俯仰力矩 N·mm", "停轉俯仰力矩 N·mm"], rows))
    s_x = ac.extras.cda[0] + sum(a[0] for _, a in ac.extras.drag_points)
    s_z = ac.extras.cda[2] + sum(a[2] for _, a in ac.extras.drag_points)
    add(f"\n驗證：α = 0° 拆槳時等於機體 x 向阻力面積總和 {s_x * 1e4:.1f} cm²，α = 90° 時等於 z 向 {s_z * 1e4:.1f} cm²。"
        "攻角 0° 到 90° 之間依模型為兩者以 cos²α、sin²α 加權（各軸獨立的阻力面積）；真實機身的極曲線未必如此，這正是風洞要確認的。\n")
    add("![Polar](polar.png)\n")

    add("## 3. 動力組在斜向氣流中（單顆槳）\n")
    if study.rotor:
        hp = tun.hover
        add(f"固定在懸停轉速 {hp.omega * 60 / (2 * math.pi):.0f} rpm。槳盤攻角以前傾為正：前飛時氣流從推力側穿過槳盤（類似爬升）；"
            "0° 為純水平氣流，90° 為軸向爬升。\n")
        rows = []
        for a in DISK_ALPHAS:
            for spd in (10.0, 20.0):
                r = next(x for x in study.rotor if abs(x.disk_alpha - a) < 1e-9 and abs(x.speed - spd) < 1e-9)
                rows.append([f"{a * DEG:.0f}°", f"{spd:.0f}", f"{r.mu:.2f}", f"{r.lam:.2f}", f"{r.thrust / study.rotor[0].thrust:.3f}",
                             f"{r.h_force:.3f}", f"{r.torque / study.rotor[0].torque:.3f}"])
        add(md_table(["槳盤攻角", "風速 m/s", "μ", "λ", "推力 / 懸停", "H 力 N", "扭矩 / 懸停"], rows))
        add("\n![Rotor](rotor.png)\n")
    else:
        add("這顆槳沒有槳葉幾何，只能用軸向係數表；斜向氣流試驗略過。\n")

    add("## 4. 配平曲線\n")
    add("每個速度求出水平定速飛行的傾角、總油門與前後油門差，使淨力與俯仰力矩為零，馬達在各自的平衡轉速。"
        "滾轉與偏航力矩的殘差列在表中（左右旋槳成對抵消後的剩餘）。\n")
    rows = []
    for p in pts:
        if p.speed % 4 > 1e-6 and p is not pts[-1]:
            continue
        rows.append([f"{p.speed:.0f}", f"{p.tilt * DEG:.1f}°", f"{100 * p.collective:.1f}%", f"{100 * p.pitch_diff:+.2f}%",
                     f"{np.mean(p.omegas) * 60 / (2 * math.pi):.0f}", f"{p.p_bus:.0f}", f"{p.i_bus:.1f}",
                     f"{p.body_drag:.2f} / {p.rotor_drag:.2f}", f"{p.max_mu:.2f}",
                     f"{p.roll_residual * 1e3:+.2f} / {p.yaw_residual * 1e3:+.2f}"])
    add(md_table(["速度 m/s", "傾角", "總油門", "前後油門差", "平均轉速 rpm", "功率 W", "電流 A", "阻力：機身 / 槳 N", "旋翼前進比 μ",
                  "滾轉 / 偏航殘差 N·mm"], rows))
    add("\n前後油門差抵消重心偏移與氣動力矩；負值表示後方馬達較快。\n")
    add("![Trim](trim.png)\n")

    add("## 5. 功率曲線與最佳巡航速度\n")
    from .performance import hover_endurance

    hover = hover_endurance(ac)
    add("定速平飛，從滿電、靜置的電池開始，每 5 秒依電池狀態重新配平，直到保留電量、負載下單芯電壓下限或電池溫度上限；"
        f"電池散熱依空速計算。速度 0 即懸停：{cr[0].time:.0f} s，設計報告的懸停續航（靜態動力系統模型）為 {hover.endurance:.0f} s，"
        f"相差 {cr[0].time / hover.endurance - 1:+.2%}（兩者的時間步長不同，且配平包含前後油門差）。\n")
    rows = []
    for c in cr:
        if c.speed % 4 > 1e-6:
            continue
        rows.append([f"{c.speed:.0f}", f"{c.time / 60:.1f}", f"{c.distance / 1000:.2f}", c.reason_zh])
    add(md_table(["速度 m/s", "續航 min", "航程 km", "結束原因"], rows))
    add(f"\n最低功率的速度 {v_e:.1f} m/s、最低「功率 ÷ 速度」的速度 {v_r:.1f} m/s 由滿電時的功率曲線求得（拋物線內插）；"
        "續航與航程曲線的最大值會因電池放電略有偏移。最高平飛速度在電壓下降後會降低，表中高速點可能因此提早結束（「電壓不足以維持此速度」）。\n")
    add("![Cruise](cruise.png)\n")

    add("## 6. 不確定度\n")
    if study.mc:
        add(f"{study.mc.n} 組蒙地卡羅樣本（與設計報告相同的參數分布），每組重新計算整條配平曲線。摘要的 90% 區間即來自這裡。\n")
    add("單一參數 ±1σ 的影響（其餘取標稱值），各列前五名：\n")
    rows = []
    for metric in ("tilt_20", "v_best_range", "power_10"):
        for bar in study.bars.get(metric, [])[:5]:
            lo, hi = sorted((bar.low, bar.high))
            rows.append([METRICS[metric][0], f"`{bar.key}`", f"{_fmt(metric, lo)} – {_fmt(metric, hi)}", measurement_method(bar.key)])
    add(md_table(["結果", "參數", "−1σ 到 +1σ", "量測方法"], rows))
    add("")

    add("## 7. 建議的實測\n")
    add("1. 拆槳的機身：風速 8–25 m/s、攻角 −10° 到 90°、側滑 ±20°，量阻力面積與俯仰、滾轉力矩（辨識 `frame.cda_*` 與 `drag_center`）。")
    add("2. 單顆動力組在固定轉速下的水平氣流：量 H 力與推力（辨識 `prop.flap_fraction`），再加槳盤攻角 15°、30° 確認斜向氣流模型。")
    add("3. 量測 CSV 的格式與 `fpvsim tunnel --synthetic` 輸出的相同，用 `fpvsim fit-tunnel` 辨識，結果可直接貼回零件檔。")
    add("")

    add("## 8. 模型假設與限制\n")
    add("- 機身阻力為三軸獨立的阻力面積，作用在固定點（機架）與各零件位置；沒有機身升力與側力的交叉項。")
    add("- 槳的斜向氣流係數錨定在軸向曲線，揮舞比例 `flap_fraction` 沒有數據（0 到 1 的均勻分布），是傾角與槳盤阻力不確定度的主要來源之一。")
    add("- 槳與槳之間、槳與機身之間的干擾只以固定的推力比例表示；高速時機臂與機身對槳盤入流的影響沒有模擬。")
    add("- 配平是靜態平衡，不含飛控動態；最高速度以滿電電壓計算。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def _clean(x: float) -> float:
    """Round-trip-safe display value without a negative zero."""
    return 0.0 if abs(x) < 0.05 else x


def _interp_cruise(cr: list[CruiseEndurance], speed: float) -> tuple[float, float]:
    s = np.array([c.speed for c in cr])
    return float(np.interp(speed, s, [c.time for c in cr])), float(np.interp(speed, s, [c.distance for c in cr]))


# ----------------------------------------------------------- fit-tunnel


def generate_fit(build: Build, fit: TunnelFit, source: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ac = build.realize()
    panels = []
    titles = {"fx": ("Body x force", "N"), "fy": ("Body y force", "N"), "fz": ("Body z force", "N"),
              "my": ("Pitching moment", "N m"), "mx": ("Rolling moment", "N m")}
    for name, (measured, model) in fit.residuals.items():
        title, unit = titles[name]
        lim = [float(min(measured.min(), model.min())), float(max(measured.max(), model.max()))]
        panels.append({"title": f"{title}: measured vs model", "xlabel": f"model [{unit}]", "ylabel": f"measured [{unit}]",
                       "series": [("1:1", lim, lim)], "points": [("data", model, measured)]})
    plots.xy_panels(panels, out_dir / "fit.png", ncols=3, panel_size=(3.4, 3.0))
    S_true = {ax: ac.extras.cda[i] + sum(a[i] for _, a in ac.extras.drag_points) for i, ax in enumerate("xyz")}
    p_cda = {ax: build.params[f"frame.cda_{ax}"] if f"frame.cda_{ax}" in build.params else None for ax in "xyz"}
    fv = frame_values(fit, ac)

    md: list[str] = []
    add = md.append
    add(f"# 風洞數據辨識報告：{build.name}\n")
    add("> 由 `fpvsim fit-tunnel` 自動產生。模型與方法見 docs/tunnel.md。\n")
    add(md_table(["項目", "內容"], [
        ["數據", f"`{source}`（拆槳 {fit.n_off} 筆、轉動 {fit.n_spin} 筆）"],
        ["機體", f"{build.name}（`{rel_path(build.path, Path.cwd())}`）"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 1. 辨識結果\n")
    add("最小平方法，HC3 穩健標準誤差。阻力面積為整機總和（機架加上有自己阻力的零件），阻力中心為相對重心的位置。"
        "「模型目前值」是設計檔的標稱值，差距以辨識的標準不確定度為單位。\n")
    rows = []
    for ax, e in fit.cda.items():
        cur = S_true[ax]
        rows.append([f"阻力面積 S_{ax}", f"{e.value * 1e4:.2f} ± {e.u * 1e4:.2f} cm²", f"{cur * 1e4:.2f} cm²",
                     f"{(e.value - cur) / e.u:+.1f}σ" if e.u > 0 else "—"])
    names = {"x": "x 位置（由 z 向阻力的俯仰力矩）", "y": "y 位置（由 z 向阻力的滾轉力矩）", "z": "高度（由 x 向阻力的俯仰力矩，下為正）"}
    for c, e in fit.centre.items():
        rows.append([f"阻力中心 {names[c]}", f"{e.value * 1e3:+.2f} ± {e.u * 1e3:.2f} mm", "—", "—"])
    if fit.flap_fraction is not None:
        e = fit.flap_fraction
        cur = ac.extras.flap_fraction
        rows.append(["槳的揮舞比例 `flap_fraction`", f"{e.value:.3f} ± {e.u:.3f}", f"{cur:.3f}", f"{(e.value - cur) / e.u:+.1f}σ" if e.u > 0 else "—"])
    add(md_table(["參數", "辨識值", "模型目前值", "差距"], rows))
    add("")
    for name, f in fit.fits.items():
        add(f"- `{name}`：{f.n} 筆，殘差 RMS {f.residual_rms:.3g}，R² {f.r2:.4f}")
    if fit.flap_fraction is not None and not (0.0 <= fit.flap_fraction.value <= 1.0):
        add("- **揮舞比例超出 0 到 1**：剛性與自由揮舞兩個極限都無法解釋量到的 H 力，斜向氣流模型本身需要檢討（例如翼型的失速模型），不要直接寫回。")
    add("\n![Fit](fit.png)\n")
    add("## 2. 寫回零件檔\n")
    add("機架的阻力面積 = 辨識的總和 − 各零件自己的阻力面積（取標稱值）；阻力中心換算成機架檔的座標（安裝原點）。"
        "不確定度取辨識的標準誤差，分布為常態；`source = \"measured\"`。\n")
    add("```toml")
    add(f"# frame component file ({rel_path(build.component_files['frame'], Path.cwd())}), [params]")
    for ax in "xyz":
        key = f"cda_{ax}"
        if key in fv:
            e = fv[key]
            unit = p_cda[ax].unit if p_cda[ax] is not None else "cm^2"
            add(f'{key} = {{ value = {e.value * 1e4:.2f}, unit = "cm^2", source = "measured", u = {max(e.u * 1e4, 0.01):.2f}, '
                f'note = "fpvsim fit-tunnel {source.name}" }}' + ("" if unit == "cm^2" else f"  # file uses {unit}"))
    dc = fv["drag_center"]
    add("# top level of the frame file (before the first table)")
    add("drag_center = { value = [" + ", ".join(f"{_clean(x * 1e3):.1f}" for x in dc) + '], unit = "mm" }')
    if fit.flap_fraction is not None:
        e = fit.flap_fraction
        add(f"# prop component file ({rel_path(build.component_files['prop'], Path.cwd())}), [params]")
        add(f'flap_fraction = {{ value = {e.value:.3f}, unit = "1", source = "measured", u = {max(e.u, 0.001):.3f}, '
            f'note = "fpvsim fit-tunnel {source.name}" }}')
    add("```\n")
    add("## 3. 方法\n")
    add("- 拆槳：各軸 F = −½ρ|v|·v_軸·S_軸，俯仰力矩 M_y = −½ρ|v|u·(S_x z_x) + ½ρ|v|w·(S_z x_z)，滾轉力矩同理；每條式子對未知數是線性的。")
    add("- 轉動（固定轉速、水平氣流）：x 向力另外加上各槳的面內力，在斜向氣流模型中對揮舞比例 f 是線性的："
        "H = H_剛性 + f·(H_自由 − H_剛性)。與拆槳的數據一起擬合，共用 S_x。")
    add("- 推力、側力與轉動時的力矩不用於辨識，以免推力模型的誤差混入阻力。")
    add("- 用 `fpvsim tunnel --synthetic` 產生的數據來自同一個模型，只能驗證辨識流程（能否找回已知值），不能確認模型；確認需要真實風洞數據。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
