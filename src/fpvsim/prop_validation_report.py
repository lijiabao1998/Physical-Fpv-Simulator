"""Prop calibration and validation report (``fpvsim validate-prop``)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import math
from pathlib import Path

import numpy as np

from . import plots
from .bemt import coefficient_curves
from .design import Build
from .performance import full_throttle_point, hover_point
from .prop_validation import (ValidationSet, calibrate_airfoil, class_shape, consistency, fit_class, model_values,
                              residuals)
from .report import code_version_text, md_table, rel_path


def _fm(ct: np.ndarray, cp: np.ndarray) -> np.ndarray:
    return ct**1.5 * math.sqrt(2.0 / math.pi) / cp


def generate(vset: ValidationSet, build: Build, out_dir: Path) -> tuple[Path, bool]:
    """Write report.md and validation.png. Returns the report path and whether
    the prop file agrees with the fit."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fit = fit_class(vset)
    ac = build.realize()
    prop = ac.powertrain.prop
    nu = ac.env.kinematic_viscosity
    checks = consistency(build, fit, vset)
    agrees = all(c.ok for c in checks)
    pd = build.params["prop.pitch"].value / build.params["prop.diameter"].value
    group_names = list(dict.fromkeys(s.group for s in vset.series))
    hp, ft = hover_point(ac), full_throttle_point(ac)
    ops = [(name, op, prop.reynolds_number(op.omega, nu) if prop.reynolds else math.nan)
           for name, op in (("懸停", hp), ("滿油門", ft)) if op is not None]

    # ------------------------------------------------------------ figure
    re = np.geomspace(0.8 * fit.re_min, 1.25 * fit.re_max, 120)
    ct_m, cp_m, fm_m = model_values(prop, re)
    ct_band, fm_band, cp_band = fit.band("ct", re), fit.band("fm", re), fit.band("cp", re)
    cp_lo, cp_hi = cp_band[1], cp_band[2]

    def groups(key):
        out = []
        for g in group_names:
            pts = [p for p in vset.points if p.group == g and getattr(p, key) is not None]
            if pts:
                out.append((g, [p.re for p in pts], [getattr(p, key) for p in pts]))
        return out

    vrefs = [(r, {"懸停": "hover", "滿油門": "full"}[n]) for n, _, r in ops if math.isfinite(r)]
    x = np.linspace(0.0, float(prop.curves.J[-1]) / pd, 60)
    g_t, g_p, s_t, s_p = class_shape(vset, x)
    geom, foil = build.prop_blade if build.prop_blade else (None, None)
    bemt_rows = []
    if geom is not None:
        J_b = x * pd
        est = coefficient_curves(geom, foil, J_b)
        cal_foil = calibrate_airfoil(geom, foil, fit.ct_level, fit.fm_level)
        cal = coefficient_curves(geom, cal_foil, J_b)
        bemt_rows = [("BEMT, estimated polar", est), ("BEMT, polar fitted to static level", cal)]
    panels = [
        {"title": "Static thrust coefficient", "xlabel": "Blade Reynolds number Re75", "ylabel": "Ct", "logx": True,
         "band": (re, ct_band[1], ct_band[2], "class +-1 sigma"), "lines": [("model", re, ct_m)], "groups": groups("ct"),
         "vrefs": vrefs},
        {"title": "Static figure of merit", "xlabel": "Blade Reynolds number Re75", "ylabel": "FM", "logx": True,
         "band": (re, fm_band[1], fm_band[2], "class +-1 sigma"), "lines": [("model", re, fm_m)], "groups": groups("fm"),
         "vrefs": vrefs},
        {"title": "Static power coefficient", "xlabel": "Blade Reynolds number Re75", "ylabel": "Cp", "logx": True,
         "band": (re, cp_lo, cp_hi, "class +-1 sigma"), "lines": [("model", re, cp_m)], "groups": groups("cp"),
         "vrefs": vrefs},
        {"title": "Shape over advance ratio", "xlabel": "J / (P/D)", "ylabel": "coefficient / static value",
         "lines": [("Ct, class (data)", x, g_t), ("Cp, class (data)", x, g_p)]
         + [(f"Cp, {name}", x, c.cp / c.cp[0]) for name, c in bemt_rows[:1]],
         "groups": [(f"{s.id} Ct", s.x, s.ct_ratio) for s in vset.shapes] + [(f"{s.id} Cp", s.x, s.cp_ratio) for s in vset.shapes]},
    ]
    plots.band_panels(panels, out_dir / "validation.png")

    # ------------------------------------------------------------ text
    md: list[str] = []
    add = md.append
    prop_file = build.component_files["prop"]
    h = hashlib.sha256(vset.path.read_bytes() + prop_file.read_bytes()).hexdigest()[:16]
    add(f"# 槳的校正與驗證報告：{build.params['prop.diameter'].display_value:g}×{build.params['prop.pitch'].display_value:g} 吋三葉槳（{vset.name}）\n")
    add("> 由 `fpvsim validate-prop` 自動產生。把通用槳的係數與它所代表的這一類槳的公開推力台數據比較：擬合這一類的平均與分散、"
        "檢查零件檔是否與擬合一致，並畫出模型與每一個數據點。方法見 docs/models.md 與 docs/methodology.md §7。\n")
    add(md_table(["項目", "內容"], [
        ["驗證數據", f"`{rel_path(vset.path, Path.cwd())}`（{vset.id}，擷取日期 {vset.retrieved or '—'}）：{len(vset.series)} 組靜態數據、"
                 f"{len(vset.points)} 點，{len(vset.shapes)} 組前進比形狀"],
        ["槳零件檔", f"`{rel_path(prop_file, Path.cwd())}`"],
        ["工作點所用的機體", f"{build.name}（`{rel_path(build.path, Path.cwd())}`），空氣 {ac.env.rho:.3f} kg/m³、"
                     f"動黏度 {nu * 1e6:.2f} mm²/s"],
        ["程式版本", code_version_text()],
        ["輸入檔雜湊（數據 + 零件檔）", f"`{h}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    add(f"- 這一類槳在 Re75 = {fit.re_ref:,.0f}：Ct = {fit.ct_level:.4f} ± {fit.ct_level_u_rel:.1%}、"
        f"FM = {fit.fm_level:.3f} ± {fit.fm_level_u_rel:.1%}（Cp = {fit.cp_level:.4f}），1σ，為一款新槳相對於這一類平均的預測不確定度。")
    add(f"- 雷諾數趨勢：Ct ∝ Re^{fit.ct_exponent:.3f}（± {fit.ct_exponent_u:.3f}，推力數據 Re75 = {fit.re_min:,.0f}–{fit.re_max:,.0f}），"
        f"FM ∝ Re^{fit.fm_exponent:.3f}（± {fit.fm_exponent_u:.3f}，扭矩數據 Re75 = {fit.fm_re_min:,.0f}–{fit.fm_re_max:,.0f}）。")
    for name, op, r in ops:
        outside = not fit.re_min <= r <= fit.re_max or not fit.fm_re_min <= r <= fit.fm_re_max
        add(f"- {name}：{op.rpm:,.0f} rpm，Re75 = {r:,.0f}{'（超出數據範圍的部分保持在邊界值）' if outside else ''}，"
            f"Ct = {prop.ct0 * prop.re_factors(op.omega, nu)[0]:.4f}，FM = {prop.figure_of_merit(op.omega, nu):.3f}。")
    add(f"- 零件檔與擬合{'一致' if agrees else '**不一致**'}（{sum(c.ok for c in checks)}/{len(checks)} 項在捨入誤差內，見第 2 節）。")
    add("")
    add("![Validation](validation.png)\n")

    add("## 1. 數據\n")
    add("每一點都個別引用（來源網址與它在原始資料中的位置記在數據檔裡）；品牌與型號只用來標示受測物。"
        "係數以各數據自己的空氣密度換算，雷諾數 Re75 = Ω (0.75 R) c75 / ν，c75 = "
        f"{vset.chord75 * 1e3:g} mm 對整類槳相同，所以 Re75 實際上是換算後的轉速。\n")
    rows = []
    for s in vset.series:
        n_t = sum(1 for p in s.points if p.torque is not None)
        res = [p.re for p in s.points]
        rows.append([f"`{s.id}`", s.tested, s.rig, f"{len(s.points)} / {n_t}", f"{min(res):,.0f}–{max(res):,.0f}",
                     "是" if s.level else "否（只用於趨勢）", f"[來源]({s.url})"])
    add(md_table(["數據", "受測物", "推力台", "點數（推力 / 扭矩）", "Re75", "用於等級", "出處"], rows))
    add("")
    for s in vset.series:
        notes = [n for n in (s.torque_note if s.torque_points_dropped else "", s.note) if n and n != "同 tyto-wek"]
        for n in notes:
            add(f"- `{s.id}`：{n}")
    add(f"- 推力台之間的系統誤差取 {vset.rig_u_rel:.0%}：{vset.rig_note}")
    add("")
    if vset.excluded:
        add("看過但沒有收錄的數據：\n")
        add(md_table(["數據", "原因"], [[e.get("what", ""), e.get("reason", "")] for e in vset.excluded]))
        add("")

    add("## 2. 擬合\n")
    add(f"每組數據各自以最小平方法擬合 log y = log y_ref + n log(Re/Re_ref)（y = Ct 或 FM，Re_ref = {fit.re_ref:,.0f}）；"
        "同一款槳在同一台推力台上的數據（例如同一頁上的不同馬達）先平均成一組。"
        "這一類的等級是用於等級的各組在 Re_ref 的幾何平均，指數是所有組的平均。"
        "不確定度是一款新槳的預測標準差 s √(1 + 1/n)（n 組、樣本標準差 s），等級另外加上推力台之間的系統誤差。\n")
    rows = []
    for g in group_names:
        ct, fm = fit.ct_groups.get(g), fit.fm_groups.get(g)
        rows.append([f"`{g}`", "是" if vset.group_level(g) else "否",
                     f"{ct.level:.4f}" if ct else "—", f"{ct.exponent:.3f}" if ct else "—",
                     f"{fm.level:.3f}" if fm else "—", f"{fm.exponent:.3f}" if fm else "—", f"{ct.n if ct else 0}"])
    rows.append(["**這一類**", "", f"**{fit.ct_level:.4f}** ± {fit.ct_level_u_rel:.1%}", f"**{fit.ct_exponent:.3f}** ± {fit.ct_exponent_u:.3f}",
                 f"**{fit.fm_level:.3f}** ± {fit.fm_level_u_rel:.1%}", f"**{fit.fm_exponent:.3f}** ± {fit.fm_exponent_u:.3f}", ""])
    add(md_table(["組", "用於等級", "Ct(Re_ref)", "Ct 指數", "FM(Re_ref)", "FM 指數", "組內數據數"], rows))
    add("")
    rig_of = {g: g.split("@")[-1] for g in group_names}  # groups are named product@rig
    ct_rigs = {rig_of[g] for g in fit.level_groups}
    fm_level = [g for g in fit.fm_groups if vset.group_level(g)]
    fm_rigs = {rig_of[g] for g in fm_level}
    add(f"等級的數據來源：Ct 來自 {len(fit.level_groups)} 組、{len(ct_rigs)} 種推力台；FM（因而 Cp）來自 {len(fm_level)} 組有扭矩的數據、"
        f"{len(fm_rigs)} 種推力台" + ("，推力台之間的差異只由系統誤差項代表" if len(fm_rigs) < 2 else "") + "。\n")
    add("零件檔與擬合的比較（零件檔的數值是擬合結果捨入後的值）：\n")
    add(md_table(["項目", "擬合", "零件檔", "容許差", "一致"], [
        [c.name, f"{c.fitted:.5g}", f"{c.in_file:.5g}", f"{c.tolerance:.1%}" if c.relative else f"{c.tolerance:g}", "是" if c.ok else "**否**"]
        for c in checks]))
    add("")

    add("## 3. 前進比的形狀\n")
    add("上面的數據都是靜態（J = 0）。Ct、Cp 隨前進比的變化取自 UIUC 兩款 5 吋三葉槳的風洞數據，各以同轉速的靜態值正規化，"
        "橫軸用 x = J / (P/D) 對齊不同螺距的槳；零件檔的 Ct(J)、Cp(J) 為靜態等級乘上兩款的平均形狀。\n")
    add(md_table(["槳", "P/D", "轉速", "出處"],
                 [[s.tested, f"{s.pitch_over_diameter:.3f}", f"{s.rpm:,.0f} rpm", f"[J>0]({s.url})、[靜態]({s.static_url})"] for s in vset.shapes]))
    add("")
    picks = [0.2, 0.4, 0.5, 0.6, 0.8]
    rows = []
    for xv in picks:
        i = int(np.argmin(np.abs(x - xv)))
        row = [f"{x[i]:.2f}", f"{g_t[i]:.3f} ± {s_t[i]:.3f}", f"{g_p[i]:.3f} ± {s_p[i]:.3f}"]
        for _, c in bemt_rows:
            row += [f"{c.ct[i] / c.ct[0]:.3f}", f"{c.cp[i] / c.cp[0]:.3f}"]
        rows.append(row)
    header = ["x = J/(P/D)", "Ct/Ct₀（數據，平均 ± 半差）", "Cp/Cp₀（數據）"]
    if bemt_rows:
        header += ["Ct/Ct₀（BEMT，估計翼型）", "Cp/Cp₀（BEMT，估計翼型）", "Ct/Ct₀（BEMT，翼型校正到靜態值）", "Cp/Cp₀（BEMT，翼型校正到靜態值）"]
    add(md_table(header, rows))
    add("")
    if bemt_rows:
        add(f"為什麼不直接校正 BEMT：把升力斜率與最小阻力調到重現靜態 Ct 與 FM（升力斜率 {cal_foil.cl_alpha:.2f} /rad、最小阻力 {cal_foil.cd_min:.4f}），"
            f"BEMT 的 Cp 在 x = 0.5 仍比數據高約 {cal.cp[int(np.argmin(np.abs(x - 0.5)))] / cal.cp[0] / g_p[int(np.argmin(np.abs(x - 0.5)))] - 1:.0%}："
            "單一翼型極曲線的 BEMT 無法同時符合靜態效率與前進時的效率（真實的小槳在靜態時有 BEMT 沒有的損失）。"
            "所以軸向係數用數據；BEMT 只提供斜向氣流相對於軸向的變化（rotor_ff.py，錨定在這些曲線上）。\n")

    add("## 4. 模型與數據\n")
    add("模型（零件檔的係數加上雷諾數修正）在各數據點的 Re75 的值，與數據的平均對數差；"
        "z = 差 / 這一類的等級不確定度（|z| < 2 表示這組數據在一款新槳的 95% 預測範圍內）。\n")
    res = residuals(vset, prop)
    rows = []
    for g in group_names:
        r = res[g]
        rows.append([f"`{g}`", f"{r['n_ct']}", f"{math.expm1(r['ct']):+.1%}", f"{r['ct'] / fit.ct_level_u_rel:+.2f}",
                     f"{r['n_fm']}" if r["n_fm"] else "—", f"{math.expm1(r['fm']):+.1%}" if r["n_fm"] else "—",
                     f"{r['fm'] / fit.fm_level_u_rel:+.2f}" if r["n_fm"] else "—"])
    add(md_table(["組", "Ct 點數", "Ct 數據 / 模型 − 1", "z", "FM 點數", "FM 數據 / 模型 − 1", "z"], rows))
    add("")

    add("## 5. 方法與限制\n")
    add("- 通用槳代表的是「這一類槳」，不是某一款產品：等級的不確定度包含不同產品與不同推力台的差異。"
        "買到的槳實測一次（`fpvsim fit-prop`）就能把這些換成那一款槳自己的數值。")
    add("- 雷諾數修正對所有前進比使用同一個倍數；前進比的形狀數據在 Re75 約 2 萬，比這一類的工作範圍低。"
        "沒有 5 吋三葉槳在 Re75 = 3×10⁴–10⁵ 有風速的公開數據。")
    add("- 數據範圍外（Re75 < 下限或 > 上限）係數保持在邊界值，不外插。")
    add("- 推力台的空氣密度多半沒有公布，依各數據檔記載的假設換算（誤差約 ±3%，已涵蓋在推力台系統誤差內）。")
    add("- 斜向氣流（前飛、側風）的變化來自 BEMT 與估計的槳葉幾何，只錨定在這些軸向曲線上，沒有斜向氣流的數據驗證。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path, agrees

