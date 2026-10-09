"""Battery selection report (``fpvsim battery-sweep``)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from . import __version__, plots
from .battery_sweep import SweepPoint, binding, recommend
from .design import Build
from .report import fmt_metric, git_version, md_table, rel_path

ROWS = ("auw", "thrust_to_weight", "endurance", "full_throttle_time", "prop_clearance", "hover_max_temperature")


def _band(points: list[SweepPoint], key: str, scale: float = 1.0):
    lo = [p.mc.percentiles(key)[0] * scale for p in points]
    med = [p.mc.percentiles(key)[1] * scale for p in points]
    hi = [p.mc.percentiles(key)[2] * scale for p in points]
    return lo, med, hi


def generate(build: Build, points: list[SweepPoint], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    reqs = build.spec.requirements
    caps = [p.capacity_mah for p in points]
    base = next((p for p in points if abs(p.ratio - 1.0) < 1e-9), None)
    rec = recommend(points)
    limits = {r.metric: r for r in reqs}

    panels = []
    for key, title, ylabel, scale in (("endurance", "Hover endurance", "min", 1 / 60), ("thrust_to_weight", "Thrust-to-weight", "1", 1.0),
                                      ("auw", "All-up weight", "g", 1000.0), ("full_throttle_time", "Full-throttle burst", "s", 1.0)):
        lo, med, hi = _band(points, key, scale)
        panel = {"title": title, "xlabel": "Capacity [mAh]", "ylabel": ylabel,
                 "series": [("median", caps, med), ("5 %", caps, lo), ("95 %", caps, hi)]}
        if key in limits:
            panel["refs"] = [(limits[key].limit * scale, f"{limits[key].id} limit")]
        panels.append(panel)
    panels.append({"title": "Probability of meeting every requirement", "xlabel": "Capacity [mAh]", "ylabel": "P",
                   "series": [("all requirements", caps, [p.p_all for p in points])], "ylim": (0, 1.02)})
    panels.append({"title": "Prop clearance margin", "xlabel": "Capacity [mAh]", "ylabel": "mm",
                   "series": [("median", caps, _band(points, "prop_clearance", 1000)[1]),
                              ("5 %", caps, _band(points, "prop_clearance", 1000)[0])], "refs": [(0.0, "R7")]})
    plots.xy_panels(panels, out_dir / "sweep.png")

    md: list[str] = []
    add = md.append
    add(f"# 電池選型報告：{build.name}\n")
    add("> 由 `fpvsim battery-sweep` 自動產生。同一系列電池（同電芯、同工法）在不同容量下的縮放，縮放律與限制見 docs/battery.md。\n")
    fam = points[0].build.params
    add(md_table(["項目", "內容"], [
        ["機體", f"{build.name}（`{rel_path(build.path, Path.cwd())}`）"],
        ["基準電池", f"`{rel_path(build.component_files['battery'], Path.cwd())}`，{base.capacity_mah if base else points[0].capacity_mah / points[0].ratio:.0f} mAh"],
        ["縮放參數", f"固定質量 {fam['battery_family.overhead_mass'].display_value:g} ± {fam['battery_family.overhead_mass'].display_u:g} g；"
                 f"內阻指數 {fam['battery_family.resistance_exponent'].value:g} ± {fam['battery_family.resistance_exponent'].u:g}"],
        ["蒙地卡羅", f"每個容量 {points[0].mc.n} 組，種子 {points[0].mc.seed}；各容量使用相同的樣本（成對比較）"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
        ["輸入檔雜湊", f"`{build.input_hash()[:16]}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    bind = binding(points, reqs)
    add(f"- **建議容量：{rec.capacity_mah:.0f} mAh**，符合全部規格的機率 {rec.p_all:.0%}"
        "（在機率最高的容量中，取懸停續航中位數最長者）。")
    smaller = [p for p in points if p.capacity < rec.capacity]
    larger = [p for p in points if p.capacity > rec.capacity]
    if smaller:
        s = smaller[-1]
        add(f"- 往小一級（{s.capacity_mah:.0f} mAh）：符合機率 {s.p_all:.0%}，"
            + (f"低於 95% 的規格：{'、'.join(bind[f'{s.capacity_mah:.0f}'])}。" if bind[f"{s.capacity_mah:.0f}"] else "各規格都在 95% 以上。"))
    if larger:
        g = larger[0]
        add(f"- 往大一級（{g.capacity_mah:.0f} mAh）：符合機率 {g.p_all:.0%}，"
            + (f"低於 95% 的規格：{'、'.join(bind[f'{g.capacity_mah:.0f}'])}。" if bind[f"{g.capacity_mah:.0f}"] else "各規格都在 95% 以上。"))
    if base is not None:
        add(f"- 驗證：基準容量的掃描點與設計報告的標稱值相同（懸停續航 {fmt_metric('endurance', base.nominal['endurance'])}）。")
    add("")

    add("## 1. 各容量的結果\n")
    add("標稱值，括號內為 90% 區間（蒙地卡羅 5% 到 95%）。\n")
    rows = []
    for p in points:
        row = [f"{p.capacity_mah:.0f}", f"{p.nominal['auw'] * 1000:.0f}",
               " × ".join(f"{x * 1000:.0f}" for x in p.size)]
        for key in ROWS[1:]:
            lo, _, hi = p.mc.percentiles(key)
            row.append(f"{fmt_metric(key, p.nominal[key])}（{fmt_metric(key, lo, False)} – {fmt_metric(key, hi, False)}）")
        row.append(f"{p.p_all:.0%}")
        rows.append(row)
    add(md_table(["容量 mAh", "全備重量 g", "尺寸 mm", "推重比", "懸停續航", "全油門持續", "槳葉間隙餘量", "懸停最高電池溫度",
                  "符合全部規格"], rows))
    add("\n![Sweep](sweep.png)\n")

    add("## 2. 各規格的符合機率\n")
    rows = []
    for r in reqs:
        rows.append([f"{r.id} {r.title}"] + [f"{p.compliance[r.id]:.0%}" for p in points])
    rows.append(["**全部**"] + [f"**{p.p_all:.0%}**" for p in points])
    add(md_table(["規格"] + [f"{c:.0f} mAh" for c in caps], rows))
    add("")
    if len(points) > 1:
        e = [p.nominal["endurance"] for p in points]
        m = [p.nominal["auw"] for p in points]
        rows = []
        for i in range(1, len(points)):
            gain = (e[i] - e[i - 1]) / ((m[i] - m[i - 1]) * 1000)
            rows.append([f"{caps[i - 1]:.0f} → {caps[i]:.0f}", f"{(m[i] - m[i - 1]) * 1000:+.0f} g", f"{e[i] - e[i - 1]:+.0f} s",
                         f"{gain:.2f} s/g"])
        add("**邊際效益**（標稱值）：每多一克電池換到的懸停時間。\n")
        add(md_table(["容量", "質量增加", "懸停續航增加", "每克"], rows))
        add("")

    add("## 3. 方法與假設\n")
    add("- 縮放律（容量比 r = C/C₀）：容量 × r；質量 = 固定質量 + (基準質量 − 固定質量) × r；內阻 × r^(−n)；尺寸每邊 × r^(1/3)；"
        "對流散熱 × r^(2/3)；熱容量隨質量；標示 C 數不變。")
    add("- 電池底面（靠機架的一面）固定，較大的電池往上長；`mounted_on` 電池的零件（綁帶、相機座）跟著頂面移動。")
    add("- 每個樣本的縮放後數值由該樣本的基準電池參數與縮放參數計算，所以各容量是成對比較；r = 1 時與設計報告完全相同。")
    add("- 只換電池，其他零件不變；飛控增益、動力系統都沒有重新最佳化。實際選型時，較重的電池可能需要重新調參。")
    add("- 真實電池系列的縮放未必如此規則（例如不同容量用不同電芯、外形只改長度）；有兩種以上容量的實測質量與內阻時，應以它們取代縮放律。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
