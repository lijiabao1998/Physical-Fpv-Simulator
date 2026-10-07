"""Stage 7 comparison report.

Every sentence of the summary is derived from the numbers in the tables, so
it stays true for any set of versions, not only the example in the repo.
"""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

import numpy as np

from . import __version__, plots, units
from .compare import COMPARE_METRICS, Comparison, summarise_delta
from .performance import METRICS
from .report import fmt_metric, fmt_probability, git_version, md_table, measurement_method, rel_path, verdict

AXES = ("roll", "pitch", "yaw")
AXIS_ZH = {"roll": "滾轉", "pitch": "俯仰", "yaw": "偏航"}
KIND_ZH = {
    "added": "新增零件",
    "removed": "移除零件",
    "moved": "移動",
    "replaced": "更換",
    "component": "更換零件檔",
    "spec": "更換規格",
    "param_added": "新增參數",
    "param_removed": "移除參數",
    "value": "改數值",
}
SCOPE_ZH = {"shared": "共有", "base": "僅基準", "variant": "僅新版本"}
FLIGHT_ROWS = (
    ("forward_speed", "前飛段末速度", "m/s", "{:.1f}"),
    ("forward_pitch", "前飛段末傾角", "°", "{:.1f}"),
    ("flip_alt_loss", "滾轉翻掉高度", "m", "{:.2f}"),
    ("backflip_alt_loss", "後空翻掉高度", "m", "{:.2f}"),
    ("yaw_rate", "原地自轉平均角速度", "deg/s", "{:.0f}"),
    ("punch_alt_gain", "衝刺 2 秒內爬升高度", "m", "{:.1f}"),
    ("max_climb", "最大爬升速度", "m/s", "{:.1f}"),
    ("min_cell_voltage", "最低單芯電壓", "V", "{:.2f}"),
    ("peak_current", "最大電流", "A", "{:.0f}"),
    ("mah", "用電量", "mAh", "{:.0f}"),
    ("tracking_roll", "滾轉追蹤誤差 (RMS)", "deg/s", "{:.1f}"),
    ("tracking_pitch", "俯仰追蹤誤差 (RMS)", "deg/s", "{:.1f}"),
    ("saturation", "混控飽和時間", "%", "{:.1%}"),
)
def labels(n: int) -> list[str]:
    return ["base"] + [chr(ord("A") + i) for i in range(n - 1)]


def _pct(x: float, signed: bool = False) -> str:
    if not math.isfinite(x):
        return "—"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def _signed(value: float, fmt: str, unit: str) -> str:
    """A signed difference in display units; percentages are percentage points."""
    text = format(value, "+" + fmt)
    if unit == "%":
        return f"{text} 個百分點"
    return text if unit == "1" else f"{text} {unit}"


def _baseline_step(study):
    if study is None:
        return None
    return next((c for c in study.candidates if c.pd == 1.0 and c.d == 1.0), None)


def generate(cmp: Comparison, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    vs = cmp.versions
    tags = labels(len(vs))
    root = Path.cwd()
    acs = [v.build.realize() for v in vs]

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
                "items": ac.items,
                "cg": ac.mass_props.cg,
                "thrust_centre": ac.thrust_centroid,
                "prop_z": float(np.mean([i.position[2] for i in ac.items if i.mass_key == "prop.mass"])),
            }
            for tag, v, ac in zip(tags, vs, acs)
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
        xlabel="Hover time [min]",
    )
    flown = all(v.flight is not None for v in vs)
    if flown:
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
    tuned = all(steps)
    if tuned:
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
    reqs = base.build.spec.requirements
    add("# 設計迭代比較報告\n")
    add("> 由 `fpvsim compare` 自動產生。所有版本用相同的設定分析：同一個隨機種子、相同的蒙地卡羅樣本數、同一份規格、"
        "相同的飛控設定與飛行腳本。蒙地卡羅是**成對**的：在第 i 組樣本中，各版本共有的零件（同一個零件檔、同樣數值的參數）"
        "取相同的值，所以差異是逐組直接算出來的，不受兩次獨立抽樣的雜訊干擾。"
        "但共有零件仍會影響變更的**大小**（例如槳的效率決定了多 165 g 要多耗多少電），所以差異的區間也包含它們的不確定度，見第 3 節的敏感度分析。\n")
    add(md_table(["代號", "版本", "設計檔", "相對基準的變更（演進順序）", "輸入檔雜湊"], [
        [tag, v.build.name, f"`{rel_path(v.build.path, root)}`",
         " → ".join(step["change"] or step["id"] for step in v.build.lineage[1:]) or "基準設計",
         f"`{v.build.input_hash()[:12]}`"]
        for tag, v in zip(tags, vs)
    ]))
    add("")
    add(md_table(["項目", "內容"], [
        ["規格", f"{base.build.spec.name}（`{base.build.spec.id}`），所有版本相同"],
        ["飛控設定", f"{cmp.fc.name}（`{cmp.fc.id}`），所有版本相同"],
        ["蒙地卡羅", f"每個版本 {cmp.samples} 組成對樣本，隨機種子 {cmp.seed}"],
        ["飛行腳本", f"`{cmp.maneuver.name}`：{cmp.maneuver.title}" if cmp.maneuver else "未執行"],
        ["程式版本", f"fpvsim {__version__}，git `{cmp.code_version or git_version(base.build.path.parent)}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")

    # summary --------------------------------------------------------------
    add("## 摘要\n")
    for i in range(1, len(vs)):
        v = vs[i]
        dm = v.nominal["auw"] - base.nominal["auw"]
        end_lo, end_mid, end_hi = summarise_delta(cmp.relative_delta(i, "endurance"))
        _, tw_mid, _ = summarise_delta(cmp.relative_delta(i, "thrust_to_weight"))
        failed = [r.id for r in reqs if v.compliance[r.id] < 0.5]
        risky = [r.id for r in reqs if 0.5 <= v.compliance[r.id] < 0.95]
        base_failed = {r.id for r in reqs if base.compliance[r.id] < 0.5}
        newly = [x for x in failed if x not in base_failed]
        line = (f"- **{tags[i]}（{v.build.name}）**：全備重量 {units.from_si(dm, 'g'):+.0f} g（{_pct(dm / base.nominal['auw'], True)}），"
                f"懸停續航 {_pct(end_mid, True)}（90% 區間 {_pct(end_lo, True)} 至 {_pct(end_hi, True)}），"
                f"推重比 {_pct(tw_mid, True)}，重心偏移 {fmt_metric('cg_offset', v.nominal['cg_offset'])}。")
        if newly:
            line += f"新增不符合的規格：{'、'.join(newly)}。"
        if risky:
            line += f"有風險：{'、'.join(risky)}。"
        add(line)
    if len(vs) > 2:
        counts = [sum(v.compliance[r.id] >= 0.95 for r in reqs) for v in vs[1:]]
        best = max(counts)
        leaders = [tags[i + 1] for i, c in enumerate(counts) if c == best]
        if len(leaders) == 1:
            add(f"- 在變更後的版本中，**{leaders[0]} 符合的規格最多**（{best} / {len(reqs)} 項）。")
        else:
            add(f"- 變更後的版本中，{'、'.join(leaders)} 符合的規格一樣多（{best} / {len(reqs)} 項）。")
    for r in reqs:
        if base.compliance[r.id] >= 0.95 and all(v.compliance[r.id] < 0.5 for v in vs[1:]):
            add(f"- 所有變更後的版本都不符合 {r.id}（{r.title}）。若這條規格是為變更前的用途訂的，"
                "應先決定是放寬它，還是為新用途另訂規格；這是產品決策，不是工程問題。")
    if tuned:
        os_roll = [s.metrics["axes"]["roll"].get("overshoot", math.nan) for s in steps]
        ixx = [ac.mass_props.inertia[0, 0] for ac in acs]
        parts = "、".join(f"{tags[i]} {_pct(os_roll[i])}" for i in range(1, len(vs)))
        line = f"- **控制：** 用相同的基準增益，滾轉超調在基準為 {_pct(os_roll[0])}，{parts}。"
        consistent = all((ixx[i] > ixx[0]) == (os_roll[i] < os_roll[0]) for i in range(1, len(vs)))
        if consistent and all(ixx[i] > ixx[0] for i in range(1, len(vs))):
            line += "轉動慣量變大，同樣的增益等於較低的迴路增益，所以超調變小。"
        line += "各版本自己的調參建議見第 7 節。"
        add(line)
    clear_issues = [(tags[i], p) for i, problems in enumerate(cmp.clearance) for p in problems]
    if clear_issues:
        add("- **幾何檢查：** " + "；".join(f"{t} 的 `{p.part}` 與第 {p.rotor + 1} 顆槳的槳平面只差 {1000 * p.gap:.1f} mm"
                                          for t, p in clear_issues) + "（見第 4 節）。")
    add("")

    # 1 changes ------------------------------------------------------------
    add("## 1. 設計變更\n")
    for i in range(1, len(vs)):
        add(f"**{tags[i]}** 相對基準設計：\n")
        add(md_table(["類型", "項目", "變更前", "變更後"],
                     [[KIND_ZH[c.kind], f"`{c.item}`", c.before, c.after] for c in cmp.changes[i - 1]]))
        add("")

    # 2 requirements -------------------------------------------------------
    add("## 2. 規格符合度\n")
    add("每格為符合機率（判定）。判定：≥ 95% 符合，50–95% 有風險，< 50% 不符合；"
        "與門檻相差不到兩倍蒙地卡羅標準誤差時標為「臨界」，換一個隨機種子可能落在另一邊。"
        "零件的安裝位置有標示不確定度時（例如電池與相機的 `position_u`），重心相關的機率已包含它。\n")
    add(md_table(["編號", "需求"] + tags, [
        [r.id, r.title] + [f"{fmt_probability(v.compliance[r.id], v.mc)}（{verdict(v.compliance[r.id], v.mc)}）" for v in vs]
        for r in reqs
    ]))
    add("")

    # 3 performance --------------------------------------------------------
    add("## 3. 性能對照\n")
    add("標稱值為各版本所有參數取標稱值的結果。差異欄是**成對**樣本的差（版本減基準）：中位數與 90% 區間；"
        "百分比指標的差以百分點表示。下圖是同樣的差異換算成相對變化。\n")
    header = ["指標"] + [f"{t} 標稱值" for t in tags] + [f"{t} − base（P5 – P95）" for t in tags[1:]]
    table = []
    for metric in COMPARE_METRICS:
        m = METRICS[metric]
        title = m.title + ("（大小；方向見第 4 節）" if metric == "cg_offset" else "")
        row = [title] + [fmt_metric(metric, v.nominal[metric]) for v in vs]
        for i in range(1, len(vs)):
            lo, mid, hi = summarise_delta(cmp.delta(i, metric))
            scale = units.scale(m.unit)
            row.append(f"{_signed(mid / scale, m.fmt, m.unit)}（{lo / scale:+{m.fmt}} – {hi / scale:+{m.fmt}}）")
        table.append(row)
    add(md_table(header, table))
    add("\n![Paired differences](deltas.png)\n")
    if cmp.sensitivity:
        add("### 差異的敏感度\n")
        add("每次只把一個參數移動 ±1σ，看差異（版本減基準）改變多少。共有參數在兩個版本同時移動，和成對抽樣一致。"
            "列出對續航差與推重比差影響最大的參數：\n")
        for i in range(1, len(vs)):
            rows = []
            for metric in ("endurance", "thrust_to_weight"):
                m = METRICS[metric]
                for bar in cmp.sensitivity[i - 1][metric][:4]:
                    half = abs(units.from_si(bar.high, m.unit) - units.from_si(bar.low, m.unit)) / 2
                    rows.append([m.title, f"`{bar.key}`", SCOPE_ZH[bar.scope], f"±{half:{m.fmt}}" + ("" if m.unit == "1" else f" {m.unit}")])
            add(f"**{tags[i]}**：\n")
            add(md_table(["差異", "參數", "屬於", "對差異的影響 (±1σ)"], rows))
            add("")

    # 4 mass ---------------------------------------------------------------
    add("## 4. 質量、重心與慣性\n")
    table = []
    for tag, ac in zip(tags, acs):
        mp = ac.mass_props
        prop_z = float(np.mean([i.position[2] for i in ac.items if i.mass_key == "prop.mass"]))
        off = (mp.cg - ac.thrust_centroid) * 1000
        drag = [ac.extras.cda[k] + sum(areas[k] for _, areas in ac.extras.drag_points) for k in range(3)]
        table.append([tag, f"{mp.mass * 1000:.0f} g", f"{off[0]:+.1f} / {off[1]:+.1f} mm",
                      f"{(prop_z - mp.cg[2]) * 1000:+.1f} mm",
                      " / ".join(f"{x * 1000:.3f}" for x in mp.inertia.diagonal()),
                      f"{mp.inertia[0, 2] * 1000:+.3f}",
                      " / ".join(f"{c * 1e4:.0f}" for c in drag)])
    add(md_table(["版本", "全備重量", "重心偏移（前 + / 右 +）", "重心高於槳平面", "Ixx / Iyy / Izz (g·m²)",
                  "Ixz (g·m²)", "阻力面積 x / y / z (cm²)"], table))
    add("\n- 重心高於槳平面時，前飛的槳盤阻力作用在重心下方、指向後方，會產生**低頭**力矩，傾向加大前傾；"
        "零件自己的阻力（例如相機）作用在零件位置，裝得越高，前飛時的抬頭力矩越大。兩者都由飛控修正，且都已包含在飛行模擬中。")
    add("- Ixz 是滾轉與偏航之間的慣性積（張量形式），不為零時兩軸的運動會互相耦合；裝在高處且偏前的零件會讓它變大。")
    problems = [(tags[i], p) for i, ps in enumerate(cmp.clearance) for p in ps]
    if problems:
        add("- **槳葉間隙檢查未通過：** " + "；".join(
            f"{t} 的 `{p.part}` 在第 {p.rotor + 1} 顆槳的槳盤範圍內，離槳平面 {1000 * p.gap:.1f} mm" for t, p in problems)
            + "（門檻 10 mm）。")
    else:
        add("- 槳葉間隙檢查通過：沒有零件位於槳盤範圍內且離槳平面不到 10 mm。")
    add("\n![Side views](side_views.png)\n")

    # 5 endurance ----------------------------------------------------------
    add("## 5. 懸停續航\n")
    add(md_table(["版本", "懸停續航", "結束原因", "懸停電流", "懸停油門"], [
        [tag, fmt_metric("endurance", v.endurance.endurance), v.endurance.reason_zh,
         fmt_metric("hover_current", v.nominal["hover_current"]), fmt_metric("hover_duty", v.nominal["hover_duty"])]
        for tag, v in zip(tags, vs)
    ]))
    add("\n懸停續航只取決於重量與動力系統，與重心位置無關，所以重量相同的版本續航相同。\n")
    add("![Endurance](endurance.png)\n")

    # 6 flight -------------------------------------------------------------
    if flown:
        add("## 6. 飛行測試對照\n")
        add("相同的飛控設定（基準增益）、相同的飛行腳本與隨機種子。**這是每個版本一次、所有參數取標稱值的飛行，沒有不確定度。**"
            "阻力面積、槳盤阻力係數、ESC 電流限制與振動等參數只影響這一節；它們的不確定度還沒有傳遞到飛行結果。\n")
        table = []
        for key, title, unit, fmt in FLIGHT_ROWS:
            if not all(key in v.flight_summary for v in vs):
                continue
            table.append([title] + [fmt.format(v.flight_summary[key]) + ("" if unit == "%" else f" {unit}") for v in vs])
        add(md_table(["項目"] + tags, table))
        add("\n前飛段末傾角：重量變大但阻力增加較少時，維持同樣速度需要的傾角反而較小。\n")
        add("![Flight comparison](flight.png)\n")
        crashed = [t for t, v in zip(tags, vs) if v.flight_summary.get("crashed")]
        if crashed:
            add(f"**墜機：** {'、'.join(crashed)}。\n")

    # 7 control ------------------------------------------------------------
    if tuned:
        add("## 7. 控制響應與調參\n")
        add("圖中是所有版本都用**基準增益**時的步階響應，取自各版本調參研究中的基準候選。"
            "調參飛行的每一軸都有固定時間的小幅度步階（不讓混控飽和），步階的時刻已知，所以直接在每一次步階量測，不必反卷積；"
            "表中是 12 次步階的中位數，括號為四分位距。陰影是各次步階之間的標準差。\n")
        add("![Step responses](steps.png)\n")
        table = []
        for tag, v, s in zip(tags, vs, steps):
            ax = s.metrics["axes"]
            rec = v.tuning.recommended

            def os(a):
                return f"{_pct(ax[a].get('overshoot', math.nan))}（{_pct(ax[a].get('overshoot_spread', math.nan))}）"

            unsettled = [AXIS_ZH[a] for a in AXES if ax[a].get("settled", 1.0) < 1.0]
            table.append([tag, os("roll"), os("pitch"), os("yaw"),
                          f"{1000 * ax['roll'].get('rise_time', math.nan):.0f} / {1000 * ax['pitch'].get('rise_time', math.nan):.0f} ms",
                          "、".join(unsettled) or "—",
                          rec.label if rec else "無符合條件的候選",
                          " / ".join(f"{p.p:.0f}-{p.d:.0f}" for p in rec.cfg.pids[:2]) if rec else "—"])
        add(md_table(["版本", "滾轉超調", "俯仰超調", "偏航超調", "上升時間（滾 / 俯）", "未安定的軸",
                      "調參建議", "建議 P-D（滾轉 / 俯仰）"], table))
        add("")
        edges = [f"{t}（{'、'.join(v.tuning.at_grid_edge)}）" for t, v in zip(tags, vs) if v.tuning.at_grid_edge]
        if edges:
            add(f"建議值落在掃描範圍邊緣的有：{'、'.join(edges)}，下一輪應往該方向擴大掃描。\n")

    # 8 next steps ---------------------------------------------------------
    add("## 8. 下一步\n")
    n = 1
    shared_fail = [r.id for r in reqs if base.compliance[r.id] >= 0.95 and all(v.compliance[r.id] < 0.5 for v in vs[1:])]
    if shared_fail:
        add(f"{n}. 決定 {'、'.join(shared_fail)} 是否適用於變更後的用途，必要時另訂規格，再用新規格重跑本比較。")
        n += 1
    if cmp.sensitivity:
        top = []
        for bars in cmp.sensitivity:
            for metric in ("endurance", "thrust_to_weight"):
                for bar in bars[metric][:3]:
                    if bar.key not in top:
                        top.append(bar.key)
        add(f"{n}. 最影響版本差異的估計值（第 3 節敏感度）：" + "；".join(f"`{k}` — {measurement_method(k)}" for k in top) + "。")
        n += 1
    if flown:
        add(f"{n}. 第 6 節的飛行結果另外取決於阻力面積與槳盤阻力係數（`prop.rotor_drag_factor`），"
            "它們只能由飛行測試辨識（定速平飛的傾角對速度、滑行減速）；目前飛行結果沒有不確定度。")
        n += 1
    if tuned:
        add(f"{n}. 採用的版本依第 7 節的建議重新調參後，再飛一次比較。")
    add("")

    # 9 method -------------------------------------------------------------
    add("## 9. 方法與限制\n")
    add("- 成對蒙地卡羅：每個參數的亂數流由（種子，零件身分）決定：零件檔的參數以零件檔的 id 為身分，其他參數以名稱、數值與不確定度為身分。"
        "所以同一個零件在各版本的第 i 組樣本中取值相同；換了零件或改了數值，就視為不同的物品，誤差彼此獨立。")
    add("- 差異的區間包含共有參數的影響：它們不會被成對抽樣消去，因為變更的效果大小本身就取決於它們（見第 3 節敏感度）。")
    add("- 阻力以零件疊加估計：機架的阻力作用在重心，零件的阻力作用在零件位置；零件之間的干擾與相機傾角對阻力的影響未計。")
    add("- 相機視為剛性安裝；TPU 軟座的振動隔離與畫面果凍效應不在模型內。相機在前槳上方時對進氣的遮擋也未計。")
    add("- 陀螺儀振動模型的振幅沿用基準設計。實際上同樣的不平衡力作用在較大的慣性上，角速度振動會較小，所以變更後版本的雜訊估計偏保守。")
    add("- 推重比只計入維持水平所能用的推力：重心偏離推力中心時，靠近重心那側的馬達先到滿載。")
    add("- 所有版本使用同一份規格；若版本的規格不同，`fpvsim compare` 會拒絕比較。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
