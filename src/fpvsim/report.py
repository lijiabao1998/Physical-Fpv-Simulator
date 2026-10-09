"""Design report: one Markdown file plus figures and CSV data.

The report records everything needed to reproduce it (code commit, input
file hash, Monte Carlo seed) and separates what was computed from how far it
can be trusted.
"""

from __future__ import annotations

import datetime as _dt
import math
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import __version__, plots, units
from .design import Build
from .params import Param, Source
from .performance import METRICS, evaluate, full_throttle_burst, full_throttle_point, hover_endurance, hover_point, rating_checks
from .stand import run_stand, write_csv
from .uncertainty import MonteCarloResult, TornadoBar, monte_carlo, tornado

TORNADO_METRICS = ("endurance", "thrust_to_weight", "hover_duty", "auw")
PRIORITY_METRICS = ("endurance", "thrust_to_weight", "hover_duty")
STAND_CELL_VOLTAGES = (4.2, 3.8, 3.5)


def fmt_metric(key: str, value: float, with_unit: bool = True) -> str:
    m = METRICS[key]
    if not math.isfinite(value):
        return "不可行"
    text = format(units.from_si(value, m.unit), m.fmt)
    if not with_unit or m.unit == "1":
        return text
    return f"{text}%" if m.unit == "%" else f"{text} {m.unit}"


_UNIT_SYMBOLS = {"mohm": "mΩ", "ohm": "Ω", "degC": "°C", "g*mm^2": "g·mm²", "kg*m^2": "kg·m²", "N*m": "N·m"}


def unit_symbol(unit: str) -> str:
    return _UNIT_SYMBOLS.get(unit, unit)


def fmt_param(p: Param, value: float | None = None) -> str:
    v = units.from_si(p.value if value is None else value, p.unit)
    text = f"{v:.4g}"
    return text if p.unit == "1" else f"{text} {unit_symbol(p.unit)}"


def fmt_probability(p: float, mc: MonteCarloResult) -> str:
    """Monte Carlo probability with its uncertainty. With no failures (or no
    passes) in n samples, report the one-sided 95 % bound (rule of three)."""
    if p >= 1.0:
        return f"> {1.0 - 3.0 / mc.n:.1%}"
    if p <= 0.0:
        return f"< {3.0 / mc.n:.1%}"
    return f"{p:.1%} ± {mc.probability_stderr(p):.1%}"


def fmt_u_rel(p) -> str:
    """Relative standard uncertainty as a percentage; '—' when the value is
    zero (placement offsets), where a relative figure has no meaning."""
    return f"{p.u_rel:.0%}" if math.isfinite(p.u_rel) else "—"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(lines)


def git_version(cwd: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
        return commit + ("（工作區有未提交的修改）" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "無法取得（不在 git 儲存庫中）"


def rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def verdict(p: float, mc: MonteCarloResult | None = None) -> str:
    """符合 (>= 95 %), 有風險 (50-95 %), 不符合 (< 50 %); a probability within
    two Monte Carlo standard errors of a threshold is marked as borderline,
    because another seed could put it on the other side."""
    label = "符合" if p >= 0.95 else ("有風險" if p >= 0.5 else "不符合")
    if mc is None:
        return label
    if p >= 1.0:  # no failures: the rule-of-three bound may still lie below 95 % for small n
        borderline = 1.0 - 3.0 / mc.n < 0.95
    elif p <= 0.0:  # no passes: likewise against the 50 % threshold
        borderline = 3.0 / mc.n > 0.5
    else:
        se = mc.probability_stderr(p)
        borderline = any(abs(p - t) < 2.0 * se for t in (0.95, 0.5))
    return f"{label}（臨界）" if borderline else label


_MEASUREMENT_METHODS = (
    ("prop.ct_scale", "推力台量測靜態推力，以 `fpvsim fit-prop` 辨識 Ct"),
    ("prop.cp_scale", "推力台量測扭矩（或電流與轉速），以 `fpvsim fit-prop` 辨識 Cp"),
    ("motor.rm", "四線法（Kelvin）量測線間電阻"),
    ("motor.i0", "無槳空載測試，至少兩個電壓"),
    ("motor.kv", "無槳空載測試：轉速對電壓"),
    ("battery.capacity", "定電流放電到截止電壓，量測放出電量"),
    ("battery.r", "脈衝放電測試（HPPC）量測瞬間與極化壓降"),
    ("battery.tau1", "脈衝放電測試（HPPC）量測電壓恢復曲線"),
    ("frame.thrust_interference", "推力台對比：有機臂遮擋與無遮擋"),
    ("electrical.harness_resistance", "四線法量測電源線與接頭電阻"),
    ("electrical.bec_efficiency", "量測穩壓器輸入與輸出功率"),
    (".power", "量測該模組的工作電流"),
    (".mass", "電子秤秤重"),
    (".offset_", "量測實際安裝位置（每次安裝）"),
    (".cda_", "風洞或滑行減速測試"),
    ("frame.cda", "風洞或滑行減速測試"),
    ("prop.rotor_drag_factor", "定速平飛：傾角對速度"),
    ("prop.flap_fraction", "風洞：槳在斜向氣流中的 H 力（`fpvsim fit-tunnel`），或定速平飛的傾角對速度"),
)


def measurement_method(key: str) -> str:
    for pattern, method in _MEASUREMENT_METHODS:
        if key.startswith(pattern) or (pattern.startswith(".") and pattern in key):
            return method
    return "依參數性質設計量測"


@dataclass
class ReportResult:
    path: Path
    nominal: dict[str, float]
    mc: MonteCarloResult


def generate(build: Build, out_dir: Path, n_samples: int = 1000, seed: int = 1) -> ReportResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path.cwd()
    ac = build.realize()
    nominal = evaluate(ac)
    mc = monte_carlo(build, n=n_samples, seed=seed)
    _, bars = tornado(build, list(TORNADO_METRICS))
    hover = hover_point(ac)
    full = full_throttle_point(ac)
    run = hover_endurance(ac)
    burst = full_throttle_burst(ac)
    design_points = [(dp, monte_carlo(build, n=n_samples, seed=seed, overrides=dp.overrides),
                      evaluate(build.realize(dp.overrides))) for dp in build.spec.design_points]
    mp = ac.mass_props
    pt = ac.powertrain
    prop = pt.prop
    spec = build.spec

    # ------------------------------------------------------------ figures and data
    stand_series = []
    for v_cell in STAND_CELL_VOLTAGES:
        voltage = v_cell * ac.battery.series
        rows = run_stand(ac, voltage)
        write_csv(rows, out_dir / f"stand_{voltage:.1f}V.csv")
        stand_series.append((f"{voltage:.1f} V ({v_cell:.1f} V/cell)", rows))
    plots.stand_curves(stand_series, out_dir / "stand.png")
    plots.endurance(run, ac.criteria.min_cell_voltage, ac.criteria.reserve_soc, out_dir / "endurance.png")
    plots.burst(burst, ac.criteria.burst_cell_voltage, ac.battery.max_temperature - 273.15, out_dir / "burst.png")
    plots.layout(ac.items, mp.cg, ac.thrust_centroid, [r.position for r in ac.rotors], prop.radius, out_dir / "layout.png")
    groups = Counter()
    for item in ac.items:
        groups[item.group] += item.mass
    plots.mass_breakdown(list(groups.items()), out_dir / "mass.png")
    hist_panels = []
    for req in spec.requirements:
        m = METRICS[req.metric]
        unit = req.unit
        hist_panels.append(
            {
                "values": np.array([units.from_si(v, unit) for v in mc.outputs[req.metric]]),
                "title": f"{req.id}  {m.label}",
                "unit": "" if unit == "1" else f"[{unit}]",
                "limit": units.from_si(req.limit, unit),
                "nominal": units.from_si(nominal[req.metric], unit),
            }
        )
    plots.histograms(hist_panels, out_dir / "monte_carlo.png")
    for key in ("endurance", "thrust_to_weight"):
        m = METRICS[key]
        plots.tornado(
            [_scaled_bar(b, m.unit) for b in bars[key]],
            units.from_si(nominal[key], m.unit),
            f"Sensitivity of {m.label.lower()} to +/-1 sigma of each input",
            m.label + ("" if m.unit == "1" else f" [{m.unit}]"),
            out_dir / f"tornado_{key}.png",
        )

    # ------------------------------------------------------------------ markdown
    md: list[str] = []
    add = md.append
    sources = Counter(p.source for p in build.params)
    n_req = len(spec.requirements)
    probs = {req.id: mc.probability_of_compliance(req) for req in spec.requirements}
    n_ok = sum(1 for p in probs.values() if p >= 0.95)

    add(f"# 設計報告：{build.name}\n")
    add("> 由 `fpvsim report` 自動產生，請勿手動修改。所有數字都能追溯到 `data/` 下的輸入檔；"
        "用同一個 commit、同一組輸入與同一個隨機種子重跑，會得到相同結果。\n")
    add(md_table(
        ["項目", "內容"],
        [
            ["設計檔", f"`{rel_path(build.path, root)}`"],
            ["規格", f"{spec.name}（`{spec.id}`）"],
            ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
            ["輸入檔雜湊 (SHA-256)", f"`{build.input_hash()[:16]}`"],
            ["蒙地卡羅", f"{mc.n} 組樣本，隨機種子 {mc.seed}"],
            ["環境", f"氣壓高度 {ac.env.altitude:.0f} m，氣溫 {ac.env.temperature - 273.15:.1f} °C，"
                     f"空氣密度 {ac.env.rho:.4f} kg/m³"],
            ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ],
    ))
    add("")

    add("## 摘要\n")
    add(build.description + "\n")
    add(f"- 全備重量 **{fmt_metric('auw', nominal['auw'])}**，靜態推重比 **{fmt_metric('thrust_to_weight', nominal['thrust_to_weight'])}**，"
        f"懸停馬達輸出 **{fmt_metric('hover_duty', nominal['hover_duty'])}**，懸停續航 **{fmt_metric('endurance', nominal['endurance'])}**（標稱值）。")
    add(f"- {n_req} 項規格中，有 {n_ok} 項在不確定度下的符合機率達 95% 以上（見第 1 節）。")
    failing = [c for c in rating_checks(ac) if not c.passes and "僅供參考" not in c.title]
    if failing:
        add("- 額定值檢查有 " + "、".join(c.title for c in failing) + " 超標（見第 6 節）。")
    add(f"- 滿電全油門可持續 **{burst.duration:.1f} s**，限制是{burst.reason_zh}（見第 6 節）。")
    if design_points:
        parts = []
        for dp, dp_mc, _ in design_points:
            ok = sum(dp_mc.probability_of_compliance(r) >= 0.95 for r in spec.requirements)
            bad = [r.id for r in spec.requirements if dp_mc.probability_of_compliance(r) < 0.5]
            parts.append(f"{dp.name} {ok}/{n_req} 項符合" + (f"（{'、'.join(bad)} 不符合）" if bad else ""))
        add("- **設計點：** " + "；".join(parts) + "（見第 7 節）。")
    estimate_share = (sources[Source.ESTIMATE] + sources[Source.DERIVED]) / len(build.params)
    add(f"- **可信度：** {len(build.params)} 個參數中有 {estimate_share:.0%} 是工程估計或模型推導，"
        f"沒有任何實測值（{_source_summary(sources)}）。"
        "因此本報告是**設計階段的預測**：它已通過程式驗證（verification），但尚未用實測數據確認（validation）。"
        "第 8 節列出最值得先量測的參數。\n")

    add("## 1. 規格符合度\n")
    add("符合機率是蒙地卡羅樣本中滿足需求的比例，± 為抽樣標準誤差；所有樣本都符合時，以 95% 信心的單邊界限表示"
        "（三法則：失敗機率 < 3/n）。判定：≥ 95% 為「符合」，50–95% 為「有風險」，< 50% 為「不符合」；"
        "與門檻相差不到兩倍標準誤差時標為「臨界」，換一個隨機種子可能落在另一邊。\n")
    rows = []
    for req in spec.requirements:
        p5, p50, p95 = mc.percentiles(req.metric)
        op = "≥" if req.kind == "min" else "≤"
        limit = units.from_si(req.limit, req.unit)
        unit = "" if req.unit == "1" else (req.unit if req.unit == "%" else f" {req.unit}")
        rows.append([
            req.id,
            req.title,
            f"{op} {limit:g}{unit}",
            fmt_metric(req.metric, nominal[req.metric]),
            f"{fmt_metric(req.metric, p5, False)} – {fmt_metric(req.metric, p95)}",
            fmt_probability(probs[req.id], mc),
            verdict(probs[req.id], mc),
        ])
    add(md_table(["編號", "需求", "門檻", "標稱值", "90% 區間 (P5–P95)", "符合機率", "判定"], rows))
    add("")
    for req in spec.requirements:
        if req.rationale:
            add(f"- **{req.id}**：{req.rationale}")
    add("\n![Monte Carlo distributions](monte_carlo.png)\n")

    add("## 2. 關鍵性能\n")
    add("標稱值使用所有參數的標稱值；P5、P50、P95 來自蒙地卡羅。\n")
    rows = []
    for key, m in METRICS.items():
        p5, p50, p95 = mc.percentiles(key)
        rows.append([m.title, fmt_metric(key, nominal[key]), fmt_metric(key, p5), fmt_metric(key, p50), fmt_metric(key, p95)])
    add(md_table(["指標", "標稱值", "P5", "P50", "P95"], rows))
    add("")

    add("## 3. 質量預算\n")
    add(f"全備重量 **{fmt_metric('auw', nominal['auw'])}**，不含電池 **{fmt_metric('dry_mass', nominal['dry_mass'])}**。"
        f"機體座標為 FRD（x 前、y 右、z 下），原點在馬達安裝面的馬達中心。\n")
    add("![Mass by group](mass.png)\n")
    rows = []
    by_key: dict[str, list] = {}
    for item in ac.items:
        by_key.setdefault(item.mass_key, []).append(item)
    for key, its in sorted(by_key.items(), key=lambda kv: -sum(i.mass for i in kv[1])):
        p = build.params[key]
        total = sum(i.mass for i in its)
        name = its[0].name.split("[")[0] + (f" ×{len(its)}" if len(its) > 1 else "")
        rows.append([
            name, its[0].group, f"{total * 1000:.1f} g", f"{total / mp.mass:.1%}",
            f"±{p.display_u:.3g} {unit_symbol(p.unit)}" + (" 每件" if len(its) > 1 else "") if p.uncertain else "—",
            p.source.label_zh,
        ])
    add(md_table(["零件", "分組", "質量", "占比", "不確定度 (1σ)", "來源"], rows))
    add("")
    offset = (mp.cg - ac.thrust_centroid) * 1000
    add(f"- 重心位置：x = {mp.cg[0] * 1000:.1f} mm，y = {mp.cg[1] * 1000:.1f} mm，z = {mp.cg[2] * 1000:.1f} mm")
    add(f"- 重心相對推力中心：前後 {offset[0]:+.1f} mm、左右 {offset[1]:+.1f} mm；"
        f"懸停時需要的前後推力差約 {_pitch_trim(ac):.1%}")
    prop_plane = np.mean([i.position[2] for i in ac.items if i.mass_key == "prop.mass"]) * 1000
    add(f"- 重心在槳平面{'下方' if mp.cg[2] * 1000 > prop_plane else '上方'} {abs(mp.cg[2] * 1000 - prop_plane):.1f} mm（影響前飛時的俯仰耦合，留待飛行動力學階段使用）")
    moments, axes = mp.principal()
    add("\n慣性張量（對重心，機體軸，g·m²；非對角項為負的慣性積）：\n")
    add("```")
    for row in mp.inertia * 1000:
        add("  ".join(f"{v:9.4f}" for v in row))
    add("```")
    add(f"主慣性矩：{', '.join(f'{m * 1000:.4f}' for m in moments)} g·m²。\n")
    add("![Layout](layout.png)\n")

    add("## 4. 動力匹配：虛擬推力台\n")
    add(f"單顆馬達加槳，穩壓電源（遙測補償，源阻抗為 0），空氣密度 {ac.env.rho:.4f} kg/m³。"
        "對應真實推力台的靜態測試；原始數據在 `stand_*.csv`，欄位格式和 `fpvsim fit-prop` 讀取的格式相同。\n")
    add("![Thrust stand](stand.png)\n")
    rows_25 = stand_series[0][1]
    picks = [r for r in rows_25 if round(100 * r.duty) % 10 == 0 and r.duty > 0]
    add(f"**{stand_series[0][0]}** 的數據：\n")
    add(md_table(
        ["馬達輸出", "轉速 (rpm)", "推力 (gf)", "電流 (A)", "電功率 (W)", "效率 (gf/W)", "驅動效率", "槳尖馬赫"],
        [[f"{100 * r.duty:.0f}%", f"{units.from_si(r.omega, 'rpm'):.0f}", f"{units.from_si(r.thrust, 'gf'):.0f}",
          f"{r.current:.1f}", f"{r.p_elec:.0f}", f"{units.from_si(r.specific_thrust, 'gf/W'):.2f}",
          f"{r.drive_efficiency:.0%}", f"{r.tip_mach:.2f}"] for r in picks],
    ))
    add("")
    ct_p, cp_p = build.params["prop.ct_scale"], build.params["prop.cp_scale"]
    add(f"槳的靜態係數：Ct₀ = {prop.ct0:.4f}，Cp₀ = {prop.cp0:.4f}，靜態效率因數 FM = {prop.figure_of_merit():.3f}。"
        f"來源：{build.prop_curve_source.label_zh}（{ct_p.ref}），模型不確定度 Ct ±{ct_p.u:.0%}、Cp ±{cp_p.u:.0%} (1σ)。"
        "BEMT 未計入旋流與低雷諾數效應，已知會高估小槳的效率，所以 Cp 的不確定度設得較大。\n")

    add("## 5. 懸停與續航\n")
    if hover:
        add(md_table(
            ["項目", "數值"],
            [
                ["懸停馬達輸出（ESC duty）", f"{hover.duty:.1%}"],
                ["懸停搖桿油門（扣除 idle {:.1%}）".format(ac.motor_idle), fmt_metric("hover_throttle", nominal["hover_throttle"])],
                ["懸停轉速", f"{hover.rpm:.0f} rpm"],
                ["單顆槳推力", f"{units.from_si(hover.thrust, 'gf'):.0f} gf"],
                ["單顆馬達電流 / 電壓（馬達側平均值）", f"{hover.i_motor:.2f} A / {hover.v_motor:.2f} V"],
                ["總電流 / 匯流排電壓", f"{hover.i_bus:.2f} A / {hover.v_bus:.2f} V"],
                ["總電功率（含航電 {:.1f} W）".format(pt.p_aux), f"{hover.p_bus:.1f} W"],
                ["軸功率（四顆）", f"{hover.p_shaft:.1f} W"],
                ["驅動效率（ESC + 馬達）", f"{hover.drive_efficiency:.1%}"],
                ["懸停效率", fmt_metric("hover_efficiency", nominal["hover_efficiency"])],
                ["槳盤負載", fmt_metric("disk_loading", nominal["disk_loading"])],
            ],
        ))
    else:
        add("**無法懸停：** 滿電狀態下推力不足或電壓不足。")
    add("")
    if hover:
        add(f"ESC 是降壓轉換器，所以馬達側電流大於電池側：每顆馬達從電池端只取 duty × 馬達電流 = "
            f"{hover.duty * hover.i_motor:.2f} A。\n")
    add(f"懸停續航 **{fmt_metric('endurance', run.endurance)}**，結束原因：{run.reason_zh}"
        f"（保留電量 {ac.criteria.reserve_soc:.0%}，負載下單芯電壓下限 {ac.criteria.min_cell_voltage:.2f} V）。"
        "這是穩定懸停的上限值；實際飛行有機動與修正，耗電會明顯更高。\n")
    add("![Hover endurance](endurance.png)\n")

    add("## 6. 電氣檢查\n")
    if full:
        sag = ac.battery.ocv(1.0) - full.v_bus
        add(f"滿電、靜止全油門的瞬間（極化壓降尚未建立）：總電流 {full.i_bus:.1f} A，"
            f"匯流排電壓 {full.v_bus:.2f} V（單芯 {full.v_bus / ac.battery.series:.2f} V，壓降 {sag:.2f} V），"
            f"轉速 {full.rpm:.0f} rpm，單顆推力 {units.from_si(full.thrust, 'gf'):.0f} gf。\n")
    rows = [[c.title, f"{c.value:.1f} {c.unit}", f"{c.limit:.0f} {c.unit}",
             ("通過" if c.passes else "超標") if "僅供參考" not in c.title else ("低於標示" if c.passes else "高於標示"), c.note]
            for c in rating_checks(ac)]
    add(md_table(["檢查", "全油門值", "額定", "結果", "說明"], rows))
    add("")
    rise = burst.end_temperature - ac.battery_start_temperature
    add(f"**全油門可持續時間：** 從滿電、{ac.battery_start_temperature - 273.15:.0f} °C 開始靜止全油門，"
        f"電流 {burst.current:.0f} A，**{burst.duration:.1f} s** 後{burst.reason_zh}"
        f"（電池溫度上升 {rise:.0f} K；限制：電池 {ac.battery.max_temperature - 273.15:.0f} °C、"
        f"瞬間單芯電壓 {ac.criteria.burst_cell_voltage:.2f} V、保留電量 {ac.criteria.reserve_soc:.0%}）。"
        "這取代了以標示 C 數判斷電流上限：電池能放多大電流，取決於它在那段時間內的發熱與壓降。"
        f"熱容量 {ac.battery.heat_capacity:.0f} J/K，懸停時的散熱 {ac.battery.ha_hover:.2f} W/K；"
        "實際飛行中的衝刺通常只有 1–3 秒，之間有散熱，所以這是連續全油門的上限。\n")
    add("![Full-throttle burst](burst.png)\n")

    add("## 7. 設計點（最差工況）\n")
    if not design_points:
        add("規格沒有列出設計點（`[[design_points]]`），只評估了標準工況。\n")
    else:
        add("規格要求設計在下列工況下也要符合需求。每個設計點都用同樣的樣本數與隨機種子重跑蒙地卡羅，"
            "只把工況（氣溫、海拔、電池起飛溫度與循環次數）換掉。\n")
        conditions = [["標準工況", f"{ac.env.temperature - 273.15:.0f} °C", f"{ac.env.altitude:.0f} m",
                       f"{ac.battery_start_temperature - 273.15:.0f} °C", f"{ac.battery.cycles:.0f}", "規格的基本條件"]]
        for dp, _, _ in design_points:
            dac = build.realize(dp.overrides)
            conditions.append([dp.name, f"{dac.env.temperature - 273.15:.0f} °C", f"{dac.env.altitude:.0f} m",
                               f"{dac.battery_start_temperature - 273.15:.0f} °C", f"{dac.battery.cycles:.0f}", dp.rationale])
        add(md_table(["設計點", "氣溫", "海拔", "電池起飛溫度", "電池循環次數", "說明"], conditions))
        add("")
        header = ["編號", "需求", "標準工況"] + [dp.name for dp, _, _ in design_points]
        rows = []
        for r in spec.requirements:
            row = [r.id, r.title, f"{fmt_probability(probs[r.id], mc)}（{verdict(probs[r.id], mc)}）"]
            for _, dp_mc, _ in design_points:
                p = dp_mc.probability_of_compliance(r)
                row.append(f"{fmt_probability(p, dp_mc)}（{verdict(p, dp_mc)}）")
            rows.append(row)
        add(md_table(header, rows))
        add("")
        keys = ("thrust_to_weight", "endurance", "full_throttle_time", "full_throttle_cell_voltage", "hover_current")
        add(md_table(["指標（標稱值）", "標準工況"] + [dp.name for dp, _, _ in design_points],
                     [[METRICS[k].title, fmt_metric(k, nominal[k])] + [fmt_metric(k, dn[k]) for _, _, dn in design_points]
                      for k in keys]))
        add("\n低溫時內阻依 Arrhenius 關係變大（壓降與發熱增加）；高海拔時空氣密度低，同樣推力需要更高轉速；"
            "老化電池的容量較小、內阻較大。低溫下電化學反應變慢造成的容量損失沒有建模，只計入內阻的變化，"
            "所以冬季的續航可能偏樂觀。\n")

    add("## 8. 不確定度與敏感度\n")
    add(f"蒙地卡羅：{len(build.params.uncertain())} 個不確定參數各自依分布抽樣（彼此獨立），重跑完整分析 {mc.n} 次。"
        "相同零件（四顆馬達、四支機臂）共用一個參數，視為完全相關。\n")
    add("敏感度（龍捲風圖）：每次只把一個參數移動 ±1σ，其餘維持標稱值。條越長，代表該參數的不確定度對結果影響越大。\n")
    add("![Endurance sensitivity](tornado_endurance.png)\n")
    add("![Thrust-to-weight sensitivity](tornado_thrust_to_weight.png)\n")
    add("### 建議優先量測\n")
    add("依參數對續航、推重比與懸停油門的相對影響加總排序。先量測前幾項，最能縮小預測的不確定度。\n")
    add(md_table(["順序", "參數", "目前來源", "目前不確定度", "對續航影響 (±1σ)", "對推重比影響 (±1σ)", "建議量測方法"],
               _priorities(build, bars, nominal)))
    add("")

    add("## 9. 模型假設與適用範圍\n")
    add("完整說明見 `docs/models.md`。本報告用到的模型與它們的限制：\n")
    add(md_table(
        ["模型", "可信度", "主要假設與限制"],
        [
            ["質量、重心、慣性", "高（取決於零件數據）", "零件以均勻密度的幾何體近似；同型零件數值完全相關"],
            ["ISA 大氣", "高", "對流層；忽略濕度（< 1%）"],
            ["馬達與 ESC 平均模型", "中", "忽略繞組電感與開關損耗；空載損耗對轉速為仿射；未計溫升造成的電阻變化"],
            ["槳靜態係數 (BEMT)", "中低，尚未確認", "忽略旋流、雷諾數與壓縮性；翼型與弦長是估計值"],
            ["機臂遮擋", "低", "以固定推力比例表示"],
            ["電池一階等效電路與熱模型", "中", "內阻隨溫度依 Arrhenius 變化，集總熱容與對流散熱；老化以循環次數線性近似；"
             "忽略低溫與放電倍率對容量的電化學影響、OCV 的溫度係數；OCV 曲線與熱參數是典型值"],
            ["懸停與全油門", "—", "靜態、無前飛速度；不含姿態控制與陣風修正的額外耗電"],
        ],
    ))
    add("")

    add("## 10. 參數來源總表\n")
    add("所有參數。數值以資料檔中的單位顯示；不確定度為標準不確定度 (1σ)。"
        "轉動慣量、阻力、ESC 電流限制、接地與振動等參數只用於飛行模擬（`fpvsim fly`、`fpvsim tune`），"
        "不影響本報告的穩態分析，所以它們在敏感度分析中的影響為零。\n")
    rows = []
    for p in sorted(build.params, key=lambda p: p.key):
        rel = "" if not math.isfinite(p.u_rel) else f"（{p.u_rel:.0%}{'，均勻' if p.dist == 'uniform' else ''}）"
        u = "—" if not p.uncertain else f"±{p.display_u:.3g}{rel or ('（均勻）' if p.dist == 'uniform' else '')}"
        rows.append([f"`{p.key}`", fmt_param(p), u, p.source.label_zh, " ".join(x for x in (p.note, p.ref) if x)])
    add(md_table(["參數", "數值", "不確定度", "來源", "說明"], rows))
    add("")
    if len(build.model_inputs):
        add("BEMT 的輸入（只在載入時計算一次；它們的不確定度由上表的 `prop.ct_scale`、`prop.cp_scale` 代表）：\n")
        add(md_table(["參數", "數值", "來源", "說明"],
                   [[f"`{p.key}`", fmt_param(p), p.source.label_zh, p.note] for p in build.model_inputs]))
        add("")
    add("陣列數據：\n")
    add(md_table(["數據", "來源", "說明"], [[f"`{t.name}`", t.source.label_zh, " ".join(x for x in (t.note, t.ref) if x)] for t in build.tables]))
    add("")

    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return ReportResult(path, nominal, mc)


def _scaled_bar(bar: TornadoBar, unit: str) -> TornadoBar:
    return TornadoBar(bar.key, units.from_si(bar.low, unit), units.from_si(bar.high, unit))


def _source_summary(sources: Counter) -> str:
    return "、".join(f"{s.label_zh} {n}" for s, n in sorted(sources.items(), key=lambda kv: -kv[1]))


def _pitch_trim(ac) -> float:
    """Front/rear thrust difference needed to hold a level hover with the CG offset in x."""
    xs = [r.position[0] for r in ac.rotors]
    arm = (max(xs) - min(xs)) / 2
    return abs(ac.mass_props.cg[0] - ac.thrust_centroid[0]) / arm if arm > 0 else 0.0


def _priorities(build: Build, bars, nominal) -> list[list[str]]:
    scores: dict[str, float] = {}
    spans: dict[tuple[str, str], tuple[float, float]] = {}
    for metric in PRIORITY_METRICS:
        ref = abs(nominal[metric]) or 1.0
        for b in bars[metric]:
            if math.isfinite(b.span):
                scores[b.key] = scores.get(b.key, 0.0) + b.span / ref
                spans[(b.key, metric)] = (b.low, b.high)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    ranked = [(k, s) for k, s in ranked if build.params[k].source is not Source.MEASURED][:8]
    rows = []
    for i, (key, _) in enumerate(ranked, 1):
        p = build.params[key]
        effects = []
        for metric in ("endurance", "thrust_to_weight"):
            lo, hi = spans.get((key, metric), (math.nan, math.nan))
            m = METRICS[metric]
            effects.append(f"±{abs(units.from_si(hi, m.unit) - units.from_si(lo, m.unit)) / 2:{m.fmt}}"
                           + ("" if m.unit == "1" else f" {m.unit}"))
        rows.append([str(i), f"`{key}`", p.source.label_zh, fmt_u_rel(p) if math.isfinite(p.u_rel) else f"±{p.display_u:.3g} {p.unit}",
                     effects[0], effects[1], measurement_method(key)])
    return rows
