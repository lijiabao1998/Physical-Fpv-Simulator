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
from .compare import COMPARE_METRICS, Comparison, forward_drag_split, summarise_delta
from .performance import METRICS
from .report import fmt_metric, fmt_probability, git_version, md_table, measurement_method, rel_path, verdict
from .geometry import PROP_MARGIN, PROP_TIP_MARGIN
from .tuning import DIRECTION_ZH, ff_dominated

AXES = ("roll", "pitch", "yaw")
AXIS_ZH = {"roll": "滾轉", "pitch": "俯仰", "yaw": "偏航"}
KIND_ZH = {
    "added": "新增零件",
    "removed": "移除零件",
    "moved": "移動",
    "replaced": "更換外形",
    "mount": "安裝方式（mounted_on）",
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


def _vibration_bias(tags, acs) -> str:
    """Direction of the vibration-noise error per version, from its inertia
    against the base's: larger on every axis -> conservative."""
    base = np.diag(acs[0].mass_props.inertia)
    verdicts: dict[str, list[str]] = {}
    for tag, ac in zip(tags[1:], acs[1:]):
        inertia = np.diag(ac.mass_props.inertia)
        if np.all(inertia > base):
            key = "的三軸慣量都比基準大，雜訊估計偏保守"
        elif np.all(inertia < base):
            key = "的三軸慣量都比基準小，雜訊估計偏樂觀"
        else:
            key = "的慣量有的軸較大、有的較小，偏差方向不確定"
        verdicts.setdefault(key, []).append(tag)
    return "；".join(f"{'、'.join(t)} {key}" for key, t in verdicts.items())


def _evolution(base, build) -> str:
    """The version's ``extends`` steps after the comparison base, when the
    base is one of its ancestors; otherwise say that it is not derived
    from the base (the changes against the base are in section 1)."""
    root = [str(step["path"]) for step in base.lineage]
    chain = [str(step["path"]) for step in build.lineage]
    if chain[: len(root)] == root:
        steps = build.lineage[len(root):]
        return " → ".join(step["change"] or step["id"] for step in steps) or "與基準相同"
    return "不是由基準衍生的版本（相對基準的變更見第 1 節）"


def _nominal_clearance_failures(ac) -> list[str]:
    """Every part that breaks the prop-clearance rule at its nominal position,
    with the props involved and its worst pair."""
    from .geometry import clearances

    by_part: dict[str, list] = {}
    for c in clearances(ac):
        if c.margin < 0.0:
            by_part.setdefault(c.part, []).append(c)
    out = []
    for part, pairs in sorted(by_part.items(), key=lambda kv: min(c.margin for c in kv[1])):
        worst = min(pairs, key=lambda c: c.margin)
        rotors = "、".join(str(c.rotor + 1) for c in sorted(pairs, key=lambda c: c.rotor))
        out.append(f"`{part}`（第 {rotors} 顆槳：離槳盤邊緣 {_mm(worst.horizontal)}、離槳平面 {_mm(worst.vertical)}，"
                   f"餘量 {_mm(worst.margin, signed=True)}）")
    return out


def _mm(x: float, signed: bool = False) -> str:
    return f"{1000 * x:+.1f} mm" if signed else f"{1000 * x:.1f} mm"


def _clearance_risk(v) -> float:
    """Monte Carlo probability that some part breaks the clearance rule."""
    margin = v.mc.outputs.get("prop_clearance")
    return float(np.mean(margin < 0.0)) if margin is not None else math.nan


def _size_example(vs) -> str:
    """Example sentence for the header, built from the first version's
    actual mass change rather than a fixed number."""
    dm = units.from_si(vs[1].nominal["auw"] - vs[0].nominal["auw"], "g")
    if abs(dm) < 0.5:
        return "例如槳的效率決定了同樣的變更要多耗多少電"
    return f"例如槳的效率決定了{'多' if dm > 0 else '少'} {abs(dm):.0f} g 要{'多耗' if dm > 0 else '省下'}多少電"


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
        "相同的飛控設定與飛行腳本。蒙地卡羅是**成對**的：在第 i 組樣本中，各版本共有的零件（同一個零件檔與零件名稱、同樣數值的參數）"
        "取相同的值，所以差異是逐組直接算出來的，不受兩次獨立抽樣的雜訊干擾。"
        f"但共有零件仍會影響變更的**大小**（{_size_example(vs)}），所以差異的區間也包含它們的不確定度，見第 3 節的敏感度分析。\n")
    add(md_table(["代號", "版本", "設計檔", "相對基準的變更（演進順序）", "輸入檔雜湊"], [
        [tag, v.build.name, f"`{rel_path(v.build.path, root)}`",
         "基準設計" if i == 0 else _evolution(base.build, v.build), f"`{v.build.input_hash()[:12]}`"]
        for i, (tag, v) in enumerate(zip(tags, vs))
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
    add("數值是標稱值的變化；括號裡的區間取自成對蒙地卡羅樣本。成對樣本的中位數與標稱值相差超過 1 個百分點時另外列出"
        "（非線性的指標，例如含重心配平的推重比，標稱值不等於中位數）。\n")
    for i in range(1, len(vs)):
        v = vs[i]
        dm = v.nominal["auw"] - base.nominal["auw"]
        end_nom = v.nominal["endurance"] / base.nominal["endurance"] - 1.0
        tw_nom = v.nominal["thrust_to_weight"] / base.nominal["thrust_to_weight"] - 1.0
        end_lo, end_mid, end_hi = summarise_delta(cmp.relative_delta(i, "endurance"))
        tw_lo, tw_mid, tw_hi = summarise_delta(cmp.relative_delta(i, "thrust_to_weight"))

        def nominal_and_median(nom, mid, lo, hi):
            text = f"{_pct(nom, True)}（90% 區間 {_pct(lo, True)} 至 {_pct(hi, True)}"
            return text + (f"，中位數 {_pct(mid, True)}）" if abs(mid - nom) > 0.01 else "）")

        failed = [r.id for r in reqs if v.compliance[r.id] < 0.5]
        risky = [r.id for r in reqs if 0.5 <= v.compliance[r.id] < 0.95]
        base_failed = {r.id for r in reqs if base.compliance[r.id] < 0.5}
        newly = [x for x in failed if x not in base_failed]
        line = (f"- **{tags[i]}（{v.build.name}）**：全備重量 {units.from_si(dm, 'g'):+.0f} g（{_pct(dm / base.nominal['auw'], True)}），"
                f"懸停續航 {nominal_and_median(end_nom, end_mid, end_lo, end_hi)}，"
                f"推重比 {nominal_and_median(tw_nom, tw_mid, tw_lo, tw_hi)}，"
                f"重心偏移 {fmt_metric('cg_offset', v.nominal['cg_offset'])}。")
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
        ff_roll = [v.tuning.ff_off["axes"]["roll"].get("overshoot", math.nan) if v.tuning.ff_off else math.nan for v in vs]
        if all(map(math.isfinite, ff_roll)):
            effect = [o - o0 for o, o0 in zip(os_roll, ff_roll)]
            line += ("把 F 設為 0 再飛一次，滾轉超調是 " + "、".join(f"{t} {_pct(o)}" for t, o in zip(tags, ff_roll))
                     + "；feedforward 對超調的影響（有 F 減 F = 0）是 "
                     + "、".join(f"{t} {100 * e:+.1f}" for t, e in zip(tags, effect)) + " 個百分點。")
            spread_ff, spread_0 = max(os_roll) - min(os_roll), max(ff_roll) - min(ff_roll)
            order = sorted(range(len(vs)), key=lambda i: ixx[i])
            falls = all(effect[b] <= effect[a] + 0.01 for a, b in zip(order, order[1:]))  # non-increasing with Ixx
            if spread_0 < 0.5 * spread_ff and falls:
                line += ("版本之間的差異主要來自 feedforward：它給的角加速度與 F 除以轉動慣量成正比，"
                         "所以它對超調的影響隨滾轉慣量變大而變小")
                line += ("，在慣量較大的版本甚至變成負的（有 F 時的超調比 F = 0 還低）。"
                         if min(effect) < -0.01 else "。")
        line += "各版本自己的調參建議見第 7 節。"
        add(line)
    failures = cmp.clearance_failures or [{} for _ in vs]
    clear_lines = []
    for t, v, ac, fails in zip(tags, vs, acs, failures):
        nominal = _nominal_clearance_failures(ac)
        risk = _clearance_risk(v)
        if nominal:
            clear_lines.append(f"{t} 在標稱位置就不符合：" + "、".join(nominal))
        elif risk > 0.05:
            main = "、".join(f"`{part}`" for part in fails) or "—"
            clear_lines.append(f"{t} 的標稱位置符合，但考慮安裝位置的不確定度，間隙不足的機率 {_pct(risk)}（{main}）")
    if clear_lines:
        add("- **槳葉間隙（R7）：** " + "；".join(clear_lines) + "（見第 4 節）。")
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
            "列出對續航差與推重比差影響最大的參數（依較大的一側排序）；兩側不對稱時，"
            "表示這個參數的影響是非線性的，例如安裝位置的誤差不論往哪邊偏，都讓重心離中心更遠：\n")
        for i in range(1, len(vs)):
            rows = []
            for metric in ("endurance", "thrust_to_weight"):
                m = METRICS[metric]
                for bar in cmp.sensitivity[i - 1][metric][:4]:
                    unit = "" if m.unit == "1" else f" {m.unit}"
                    lo, hi = (units.from_si(x, m.unit) - units.from_si(bar.nominal, m.unit) for x in (bar.low, bar.high))
                    rows.append([m.title, f"`{bar.key}`", SCOPE_ZH[bar.scope], f"{lo:+{m.fmt}} / {hi:+{m.fmt}}{unit}"])
            add(f"**{tags[i]}**：\n")
            add(md_table(["差異", "參數", "屬於", "差異的改變（−1σ / +1σ）"], rows))
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
    add("\n- 前飛時的阻力力矩：重心高於槳平面時，槳盤阻力作用在重心下方、指向後方，產生**低頭**力矩；"
        "機架本身的阻力作用在機架上的固定點（機架檔的 `drag_center`），重心升高後它也在重心下方，同樣產生低頭力矩；"
        "零件自己的阻力（例如相機）作用在零件位置，裝得比重心高時產生**抬頭**力矩。三者都由飛控修正，且都已包含在飛行模擬中。"
        + ("槳本身另有槳轂力矩（斜向氣流模型）：前進側升力較大造成的滾轉力矩在左右旋成對時互相抵消，俯仰力矩對參考槳很小（docs/models.md）。"
           if base.build.prop_blade is not None else ""))
    add("- Ixz 是滾轉與偏航之間的慣性積（張量形式），不為零時兩軸的運動會互相耦合；裝在高處且偏前的零件會讓它變大。")
    add(f"\n**槳葉間隙：** 每個零件（機架與動力系統以外）要在槳盤外 {_mm(PROP_TIP_MARGIN)} 以上，或離槳平面 {_mm(PROP_MARGIN)} 以上。"
        "餘量是最差的零件在較容易的方向上還能移動多少，負值表示兩條都不滿足。"
        "間隙不足的機率取自蒙地卡羅樣本，包含零件安裝位置的不確定度（`position_u`）。\n")
    add(md_table(["版本", "餘量（標稱值）", "標稱值最接近的零件", "離槳盤邊緣 / 離槳平面", "間隙不足的機率", "不足時的零件（樣本數）"], [
        [tag, _mm(c.margin, signed=True), f"`{c.part}`（第 {c.rotor + 1} 顆槳）",
         f"{_mm(c.horizontal, signed=True)} / {_mm(c.vertical)}", fmt_probability(_clearance_risk(v), v.mc),
         "、".join(f"`{part}` {n}" for part, n in f.items()) or "—"]
        if c is not None else [tag, "—", "—", "—", "—", "—"]
        for tag, v, c, f in zip(tags, vs, cmp.clearance, failures)
    ]))
    add("\n離槳盤邊緣為負值表示零件在俯視圖上位於槳盤範圍內。")
    for t, ac in zip(tags, acs):
        nominal = _nominal_clearance_failures(ac)
        if nominal:
            add(f"{t} 在標稱位置就不符合規則的零件：" + "；".join(nominal) + "。")
    add("")
    add("![Side views](side_views.png)\n")

    # 5 endurance ----------------------------------------------------------
    add("## 5. 懸停續航\n")
    add(md_table(["版本", "懸停續航", "結束原因", "懸停電流", "懸停油門"], [
        [tag, fmt_metric("endurance", v.endurance.endurance), v.endurance.reason_zh,
         fmt_metric("hover_current", v.nominal["hover_current"]), fmt_metric("hover_duty", v.nominal["hover_duty"])]
        for tag, v in zip(tags, vs)
    ]))
    groups: dict[int, list[int]] = {}
    for i, v in enumerate(vs):  # versions with equal weight and equal hover endurance (within 0.1 g, 0.5 s)
        groups.setdefault(round(v.nominal["auw"] * 1e4), []).append(i)
    same = ["、".join(tags[i] for i in g) for g in groups.values()
            if len(g) > 1 and max(vs[i].endurance.endurance for i in g) - min(vs[i].endurance.endurance for i in g) < 0.5]
    add("\n懸停續航取決於重量、動力系統與航電耗電，與重心位置無關"
        + (f"；{'；'.join(same)} 的重量與耗電相同，所以懸停續航相同。\n" if same else "。\n"))
    add("![Endurance](endurance.png)\n")

    # 6 flight -------------------------------------------------------------
    if flown:
        add("## 6. 飛行測試對照\n")
        add("相同的飛控設定（基準增益）、相同的飛行腳本與隨機種子。**這是每個版本一次、所有參數取標稱值的飛行，沒有不確定度。**"
            "阻力面積、槳盤阻力係數、ESC 電流限制與振動等參數只用於模擬飛行（本節與第 7 節的調參）；"
            "它們的不確定度還沒有傳遞到飛行結果。\n")
        table = []
        for key, title, unit, fmt in FLIGHT_ROWS:
            if not all(key in v.flight_summary for v in vs):
                continue
            table.append([title] + [fmt.format(v.flight_summary[key]) + ("" if unit == "%" else f" {unit}") for v in vs])
        add(md_table(["項目"] + tags, table))
        if all("forward_pitch" in v.flight_summary and "forward_speed" in v.flight_summary for v in vs):
            lower = [i for i in range(1, len(vs)) if vs[i].nominal["auw"] > base.nominal["auw"]
                     and vs[i].flight_summary["forward_pitch"] < base.flight_summary["forward_pitch"]]
            if lower:
                speed = base.flight_summary["forward_speed"]
                ratio, shares, per_weight = [], [], {}
                for i in [0] + lower:
                    rotor, body = forward_drag_split(acs[i], speed)
                    shares.append(rotor / (rotor + body))
                    per_weight[i] = (rotor + body) / acs[i].weight
                    ratio.append(f"{tags[i]} {per_weight[i]:.3f}（槳盤阻力占 {rotor / (rotor + body):.0%}）")
                smaller = [i for i in lower if per_weight[i] < per_weight[0]]
                why = ("槳盤阻力大約隨轉速（推力的平方根）增加，比重量增加得慢" if min(shares) > 0.5
                       else "阻力的增加比重量的增加少")
                if smaller == lower:
                    add(f"\n前飛段末傾角：{'、'.join(tags[i] for i in lower)} 比基準重，傾角卻較小。定速前飛時 tan(傾角) ≈ 阻力 ÷ 重量；"
                        f"在 {speed:.1f} m/s 時{why}，所以阻力 ÷ 重量反而變小："
                        + "、".join(ratio) + "（一階估計，旋翼在懸停轉速）。\n")
                else:
                    add(f"\n前飛段末傾角：{'、'.join(tags[i] for i in lower)} 比基準重，傾角卻較小；一階阻力估計（旋翼在懸停轉速）"
                        "的阻力 ÷ 重量是 " + "、".join(ratio) + "，不足以解釋這個差異；前飛段末未必已到定速，應以定速配平曲線（`fpvsim tunnel`）比較。\n")
        add("![Flight comparison](flight.png)\n")
        crashed = [t for t, v in zip(tags, vs) if v.flight_summary.get("crashed")]
        if crashed:
            add(f"**墜機：** {'、'.join(crashed)}。\n")

    # 7 control ------------------------------------------------------------
    if tuned:
        add("## 7. 控制響應與調參\n")
        add("圖中是所有版本都用**基準增益**時的步階響應，取自各版本調參研究中的基準候選。"
            "調參飛行的每一軸都有固定時間的小幅度步階，步階的時刻已知，所以直接在每一次步階量測，不必反卷積；"
            "表中是各次步階的中位數，括號為四分位距；+a → −a 的反向步階（兩倍幅度）與混控飽和的步階不計入。"
            "陰影是各次步階之間的標準差。\n")
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
        ff = [(t, ff_dominated(v.tuning)) for t, v in zip(tags, vs)]
        ff = [(t, axes) for t, axes in ff if axes]
        if ff:
            add("超調主要來自 feedforward 的軸（基準增益下 F 設為 0 再飛一次的對照）："
                + "；".join(f"{t}：" + "、".join(f"{AXIS_ZH[a]} {_pct(o)} → {_pct(o0)}" for a, o, o0, _, _ in axes) for t, axes in ff)
                + "。PD 掃描改變不了這部分，應單獨調整該軸的 F。\n")
        add("各版本的掃描在建議值落在範圍邊緣時會自動擴大。建議值往各方向再走一格會碰到的限制：\n")
        for t, v in zip(tags, vs):
            st = v.tuning
            reasons = "；".join(f"{DIRECTION_ZH[d]}（{n.label}）{reason}" for d, n, reason in st.binding()) or "—"
            ext = f"自動擴大 {st.extension_rounds} 輪（{'、'.join(st.extensions)}）。" if st.extensions else ""
            edge = (f"**仍在掃描範圍邊緣（{'、'.join(st.at_grid_edge)}）**，下一輪應往 {'、'.join(st.widen_towards)}的方向擴大。"
                    if st.at_grid_edge else "")
            add(f"- {t}：{ext}{edge}{reasons}。")
        add("")

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
        drag_key = "prop.flap_fraction" if cmp.base.build.prop_blade is not None else "prop.rotor_drag_factor"
        add(f"{n}. 第 6 節的飛行結果另外取決於阻力面積與槳盤阻力（`{drag_key}`），"
            "它們要由風洞（`fpvsim fit-tunnel`）或飛行測試（定速平飛的傾角對速度、滑行減速）辨識；目前飛行結果沒有不確定度。")
        n += 1
    if tuned:
        add(f"{n}. 採用的版本依第 7 節的建議重新調參後，再飛一次比較。")
    add("")

    # 9 method -------------------------------------------------------------
    add("## 9. 方法與限制\n")
    add("- 成對蒙地卡羅：每個參數的亂數流由（種子，物品身分）決定：零件檔的參數以零件檔（id 與檔案內容）加上零件名稱為身分，"
        "其他參數以名稱、數值、不確定度、分布與來源為身分。所以同一個零件在各版本的第 i 組樣本中取值相同；"
        "換了零件檔、改了檔案內容或數值、或用了新的零件名稱，就視為不同的物品，誤差彼此獨立。")
    add("- 差異的區間包含共有參數的影響：它們不會被成對抽樣消去，因為變更的效果大小本身就取決於它們（見第 3 節敏感度）。")
    add("- 阻力以零件疊加估計：機架的阻力作用在機架上的固定點（`drag_center`，估計值），零件的阻力作用在零件位置；"
        "零件之間的干擾、相機傾角對阻力的影響，以及電池移動造成的機架阻力中心變化都未計。")
    add("- 相機視為剛性安裝；TPU 軟座的振動隔離與畫面果凍效應不在模型內。相機在前槳上方時對進氣的遮擋也未計。")
    add("- 陀螺儀振動模型的振幅以角速度表示、只隨轉速變化，所以各版本沿用同一組數值。實際上同樣的不平衡力作用在較大的慣性上，"
        "角速度振動會較小：" + _vibration_bias(tags, acs) + "。")
    add("- 推重比只計入維持水平所能用的推力：重心偏離推力中心時，靠近重心那側的馬達先到滿載。")
    add("- 零件可以標示 `mounted_on`（例如相機座綁在電池上）：它的安裝位置誤差等於母零件的誤差加上自己相對母零件的誤差。")
    add("- 所有版本使用同一份規格；若版本的規格不同，`fpvsim compare` 會拒絕比較。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
