"""Stage 7 comparison report."""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

import numpy as np

from . import __version__, plots, units
from .compare import COMPARE_METRICS, Comparison, summarise_delta
from .performance import METRICS
from .report import fmt_metric, fmt_probability, git_version, md_table, rel_path

AXES = ("roll", "pitch", "yaw")
AXIS_ZH = {"roll": "滾轉", "pitch": "俯仰", "yaw": "偏航"}
KIND_ZH = {"added": "新增", "removed": "移除", "moved": "移動", "replaced": "更換", "component": "更換零件", "value": "改數值"}
FLIGHT_ROWS = (
    ("forward_speed", "前飛段末速度", "m/s", "{:.1f}"),
    ("forward_pitch", "前飛段末傾角", "°", "{:.1f}"),
    ("punch_alt_gain", "衝刺 2 秒內爬升高度", "m", "{:.1f}"),
    ("max_climb", "最大爬升速度", "m/s", "{:.1f}"),
    ("flip_alt_loss", "滾轉翻掉高度", "m", "{:.2f}"),
    ("backflip_alt_loss", "後空翻掉高度", "m", "{:.2f}"),
    ("yaw_rate", "原地自轉平均角速度", "deg/s", "{:.0f}"),
    ("min_cell_voltage", "最低單芯電壓", "V", "{:.2f}"),
    ("peak_current", "最大電流", "A", "{:.0f}"),
    ("mah", "用電量", "mAh", "{:.0f}"),
    ("tracking_roll", "滾轉追蹤誤差 (RMS)", "deg/s", "{:.1f}"),
    ("tracking_pitch", "俯仰追蹤誤差 (RMS)", "deg/s", "{:.1f}"),
    ("saturation", "混控飽和時間", "%", "{:.1%}"),
)


def labels(n: int) -> list[str]:
    return ["base"] + [chr(ord("A") + i) for i in range(n - 1)]


def _verdict(p: float) -> str:
    return "符合" if p >= 0.95 else ("有風險" if p >= 0.5 else "不符合")


def _pct(x: float, signed: bool = False) -> str:
    if not math.isfinite(x):
        return "—"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def _baseline_step(study):
    if study is None:
        return None
    return next((c for c in study.candidates if c.pd == 1.0 and c.d == 1.0), None)


def generate(cmp: Comparison, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    vs = cmp.versions
    tags = labels(len(vs))
    root = Path.cwd()

    # --------------------------------------------------------------- figures
    rows = []
    for metric in COMPARE_METRICS:
        if metric == "cg_offset":  # a few mm from near zero: a relative change says nothing
            continue
        row = {"label": METRICS[metric].label}
        for i in range(1, len(vs)):
            row[tags[i]] = tuple(100 * x for x in summarise_delta(cmp.relative_delta(i, metric)))
        rows.append(row)
    plots.delta_intervals(rows, tags[1:], out_dir / "deltas.png")
    plots.side_views(
        [
            {
                "label": f"{tag}: {v.build.id}" if tag == "base" else tag,
                "items": (ac := v.build.realize()).items,
                "cg": ac.mass_props.cg,
                "thrust_centre": ac.thrust_centroid,
                "prop_z": float(np.mean([i.position[2] for i in ac.items if i.mass_key == "prop.mass"])),
            }
            for tag, v in zip(tags, vs)
        ],
        out_dir / "side_views.png",
    )
    plots.timeseries(
        [
            {
                "title": "Hover endurance: loaded cell voltage",
                "ylabel": "V",
                "series": [(tag, v.endurance.t / 60.0, v.endurance.v_cell) for tag, v in zip(tags, vs)],
            }
        ],
        out_dir / "endurance.png",
        panel_height=2.6,
    )
    if all(v.flight is not None for v in vs):
        def series(fn):
            return [(tag, v.flight.time, fn(v)) for tag, v in zip(tags, vs)]

        plots.timeseries(
            [
                {"title": "Altitude", "ylabel": "m", "series": series(lambda v: v.flight["alt"])},
                {"title": "Speed", "ylabel": "m/s", "series": series(
                    lambda v: np.sqrt(v.flight["vel_n"] ** 2 + v.flight["vel_e"] ** 2 + v.flight["vel_d"] ** 2))},
                {"title": "Pitch attitude", "ylabel": "deg", "series": series(lambda v: v.flight["att_pitch"])},
                {"title": "Cell voltage at the ESC", "ylabel": "V",
                 "series": series(lambda v: v.flight["vbat"] / v.build.battery_series)},
                {"title": "Battery current", "ylabel": "A", "series": series(lambda v: v.flight["current"])},
            ],
            out_dir / "flight.png",
        )
    steps = [_baseline_step(v.tuning) for v in vs]
    if all(steps):
        plots.step_compare(
            [
                {
                    "title": axis.capitalize(),
                    "series": [
                        (tag, np.array(s.metrics["axes"][axis]["step"][0]), np.array(s.metrics["axes"][axis]["step"][1]),
                         np.array(s.metrics["axes"][axis]["step"][2]))
                        for tag, s in zip(tags, steps)
                        if s.metrics["axes"][axis]["step"]
                    ],
                }
                for axis in AXES
            ],
            out_dir / "steps.png",
        )

    # -------------------------------------------------------------- markdown
    md: list[str] = []
    add = md.append
    base = vs[0]
    add("# 設計迭代比較報告\n")
    add("> 由 `fpvsim compare` 自動產生。所有版本用相同的設定分析：同一個隨機種子、相同的蒙地卡羅樣本數、相同的飛控設定與飛行腳本。"
        "蒙地卡羅是**成對**的：第 i 組樣本中，各版本共有的參數取相同的值，所以版本間的差異只反映真正改變的部分。\n")
    add(md_table(["代號", "版本", "設計檔", "相對上一版的變更", "輸入檔雜湊"], [
        [tag, v.build.name, f"`{rel_path(v.build.path, root)}`",
         v.build.lineage[-1]["change"] or ("基準設計" if i == 0 else "—"), f"`{v.build.input_hash()[:12]}`"]
        for i, (tag, v) in enumerate(zip(tags, vs))
    ]))
    add("")
    add(md_table(["項目", "內容"], [
        ["飛控設定", f"{cmp.fc.name}（`{cmp.fc.id}`）"],
        ["蒙地卡羅", f"每個版本 {cmp.samples} 組成對樣本，隨機種子 {cmp.seed}"],
        ["飛行腳本", f"`{cmp.maneuver.name}`：{cmp.maneuver.title}" if cmp.maneuver else "未執行"],
        ["程式版本", f"fpvsim {__version__}，git `{cmp.code_version or git_version(base.build.path.parent)}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")

    # summary
    add("## 摘要\n")
    reqs = base.build.spec.requirements
    for i in range(1, len(vs)):
        v, tag = vs[i], tags[i]
        dm = vs[i].nominal["auw"] - base.nominal["auw"]
        end_lo, end_mid, end_hi = summarise_delta(cmp.relative_delta(i, "endurance"))
        tw_lo, tw_mid, tw_hi = summarise_delta(cmp.relative_delta(i, "thrust_to_weight"))
        failed = [r.id for r in reqs if v.compliance[r.id] < 0.5]
        risky = [r.id for r in reqs if 0.5 <= v.compliance[r.id] < 0.95]
        base_failed = {r.id for r in reqs if base.compliance[r.id] < 0.5}
        newly = [x for x in failed if x not in base_failed]
        line = (f"- **{v.build.name}**：重量 +{units.from_si(dm, 'g'):.0f} g（{_pct(dm / base.nominal['auw'], True)}），"
                f"懸停續航 {_pct(end_mid, True)}（90% 區間 {_pct(end_lo, True)} 至 {_pct(end_hi, True)}），"
                f"推重比 {_pct(tw_mid, True)}，重心偏移 {fmt_metric('cg_offset', v.nominal['cg_offset'])}。")
        if newly:
            line += f"新增不符合的規格：{'、'.join(newly)}。"
        if risky:
            line += f"有風險：{'、'.join(risky)}。"
        add(line)
    feasible_counts = [sum(v.compliance[r.id] >= 0.95 for r in reqs) for v in vs[1:]]
    best = 1 + int(np.argmax(feasible_counts))
    if len(vs) > 2:
        add(f"- **在加改的版本中，版本 {tags[best]} 符合的規格最多**（{feasible_counts[best - 1]} / {len(reqs)} 項）。")
    r1 = next((r for r in reqs if r.metric == "auw"), None)
    if r1 is not None and all(v.compliance[r1.id] < 0.5 for v in vs[1:]):
        add(f"- 所有加改版本都不符合 {r1.id}（{r1.title} {'≤' if r1.kind == 'max' else '≥'} "
            f"{units.from_si(r1.limit, r1.unit):g} {r1.unit}）。這條規格是為不掛運動相機的用途訂的；"
            "要掛相機，應先決定是放寬規格，還是另訂一份「掛相機」的規格，這是產品決策，不是工程問題。")
    if all(steps):
        b_os = steps[0].metrics["axes"]["roll"].get("overshoot", math.nan)
        parts = []
        for i in range(1, len(vs)):
            parts.append(f"版本 {tags[i]} {_pct(steps[i].metrics['axes']['roll'].get('overshoot', math.nan))}")
        add(f"- **控制：** 用相同的基準增益，滾轉超調由基準的 {_pct(b_os)} 變為" + "、".join(parts)
            + "。轉動慣量變大，同樣的增益等於較低的迴路增益；各版本重新調參的建議見第 7 節。")
    add("")

    # 1 changes
    add("## 1. 設計變更\n")
    for i in range(1, len(vs)):
        add(f"**版本 {tags[i]}** 相對基準設計：\n")
        add(md_table(["類型", "項目", "變更前", "變更後"],
                     [[KIND_ZH[c.kind], f"`{c.item}`", c.before, c.after] for c in cmp.changes[i - 1]]))
        add("")

    # 2 requirements
    add("## 2. 規格符合度\n")
    add("每格為符合機率（判定）。所有版本都對照同一份規格：" + f"{base.build.spec.name}。\n")
    add(md_table(["編號", "需求"] + tags, [
        [r.id, r.title] + [f"{fmt_probability(v.compliance[r.id], v.mc)}（{_verdict(v.compliance[r.id])}）" for v in vs]
        for r in reqs
    ]))
    add("")

    # 3 performance
    add("## 3. 性能對照\n")
    add("標稱值為各版本所有參數取標稱值的結果；差異欄是**成對**樣本的差（版本減基準）的中位數與 90% 區間。\n")
    header = ["指標"] + [f"{t} 標稱值" for t in tags] + [f"{t} − base（P5 – P95）" for t in tags[1:]]
    table = []
    for metric in COMPARE_METRICS:
        m = METRICS[metric]
        row = [m.title] + [fmt_metric(metric, v.nominal[metric]) for v in vs]
        for i in range(1, len(vs)):
            lo, mid, hi = summarise_delta(cmp.delta(i, metric))
            scale = units.scale(m.unit)
            unit = "" if m.unit == "1" else (m.unit if m.unit == "%" else f" {m.unit}")
            row.append(f"{mid / scale:+{m.fmt}}{unit}（{lo / scale:+{m.fmt}} – {hi / scale:+{m.fmt}}）")
        table.append(row)
    add(md_table(header, table))
    add("\n![Paired differences](deltas.png)\n")

    # 4 mass
    add("## 4. 質量、重心與慣性\n")
    table = []
    for tag, v in zip(tags, vs):
        ac = v.build.realize()
        mp = ac.mass_props
        prop_z = float(np.mean([i.position[2] for i in ac.items if i.mass_key == "prop.mass"]))
        off = (mp.cg - ac.thrust_centroid) * 1000
        table.append([tag, f"{mp.mass * 1000:.0f} g", f"{off[0]:+.1f} / {off[1]:+.1f} mm",
                      f"{(prop_z - mp.cg[2]) * 1000:+.1f} mm",
                      " / ".join(f"{x * 1000:.3f}" for x in mp.inertia.diagonal()),
                      " / ".join(f"{c * 1e4:.0f}" for c in ac.extras.cda)])
    add(md_table(["版本", "全備重量", "重心偏移（前後 / 左右）", "重心高於槳平面", "Ixx / Iyy / Izz (g·m²)", "阻力面積 x / y / z (cm²)"], table))
    add("\n重心高於槳平面越多，前飛時槳盤阻力造成的抬頭力矩越大，飛控需要更多修正。\n")
    add("![Side views](side_views.png)\n")

    # 5 endurance
    add("## 5. 懸停續航\n")
    add(md_table(["版本", "懸停續航", "結束原因", "懸停電流", "懸停油門"], [
        [tag, fmt_metric("endurance", v.endurance.endurance), v.endurance.reason_zh,
         fmt_metric("hover_current", v.nominal["hover_current"]), fmt_metric("hover_duty", v.nominal["hover_duty"])]
        for tag, v in zip(tags, vs)
    ]))
    add("\n![Endurance](endurance.png)\n")

    # 6 flight
    if all(v.flight is not None for v in vs):
        add("## 6. 飛行測試對照\n")
        add("相同的飛控設定（基準增益）、相同的飛行腳本與隨機種子。\n")
        table = []
        for key, title, unit, fmt in FLIGHT_ROWS:
            if not all(key in v.flight_summary for v in vs):
                continue
            cells = []
            for v in vs:
                value = v.flight_summary[key]
                cells.append(fmt.format(value) + ("" if unit == "%" else f" {unit}"))
            table.append([title] + cells)
        add(md_table(["項目"] + tags, table))
        add("\n![Flight comparison](flight.png)\n")
        crashed = [t for t, v in zip(tags, vs) if v.flight_summary.get("crashed")]
        if crashed:
            add(f"**墜機：** 版本 {'、'.join(crashed)}。\n")

    # 7 control
    if all(steps):
        add("## 7. 控制響應與調參\n")
        add("左邊是所有版本都用**基準增益**時的步階響應（取自各版本調參研究中的基準候選）；下表最後一欄是各版本自己的調參建議。\n")
        add("![Step responses](steps.png)\n")
        table = []
        for tag, v, s in zip(tags, vs, steps):
            ax = s.metrics["axes"]
            rec = v.tuning.recommended
            table.append([tag] + [_pct(ax[a].get("overshoot", math.nan)) for a in ("roll", "pitch")]
                         + [f"{1000 * ax[a]['latency']:.0f} ms" for a in ("roll", "pitch")]
                         + [rec.label if rec else "無符合條件的候選",
                            " / ".join(f"{p.p:.0f}-{p.d:.0f}" for p in rec.cfg.pids[:2]) if rec else "—"])
        add(md_table(["版本", "滾轉超調", "俯仰超調", "滾轉延遲", "俯仰延遲", "調參建議", "建議 P-D（滾轉 / 俯仰）"], table))
        add("")
        edges = [f"版本 {t}（{'、'.join(v.tuning.at_grid_edge)}）" for t, v in zip(tags, vs) if v.tuning.at_grid_edge]
        if edges:
            add(f"建議值落在掃描範圍邊緣的有：{'、'.join(edges)}，下一輪應擴大掃描。\n")

    # 8 next steps
    add("## 8. 下一步\n")
    add("1. 決定掛相機用途的規格（重量上限、續航要求），再用新規格重跑本比較。")
    add("2. 以實測確認最影響結論的估計值：運動相機與相機座的質量（秤重）、相機的阻力面積（風洞或滑行測試）、槳盤阻力係數（定速平飛的傾角）。")
    add("3. 採用的版本依第 7 節的建議重新調參後，再飛一次比較。")
    add("")

    # 9 method
    add("## 9. 方法與限制\n")
    add("- 成對蒙地卡羅：每個參數的亂數流由（種子，參數名稱）決定，所以共有參數在各版本的第 i 組樣本中取值相同；"
        "差異的分布只來自改變的部分與它們引起的非線性效應。")
    add("- 阻力以零件疊加（drag buildup）估計，未計入零件之間的干擾；相機傾角對阻力的影響未計。")
    add("- 相機視為剛性安裝；TPU 軟座的振動隔離與畫面果凍效應不在模型內。")
    add("- 陀螺儀振動模型的振幅沿用基準設計。實際上同樣的不平衡力作用在較大的慣性上，角速度振動會較小，所以加改版本的雜訊估計偏保守。")
    add("- 所有版本使用同一份規格與同一組飛控設定；調參研究另外為每個版本找建議增益。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
