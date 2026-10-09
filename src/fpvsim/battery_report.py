"""Battery identification report (``fpvsim fit-battery``)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import __version__
from .battery_fit import ArrheniusFit, FlightFit, HppcFit
from .plots import MUTED, SERIES, STYLE, _save
from .report import git_version, md_table


def _mohm(x: float) -> str:
    return f"{1000 * x:.3f}"


def _plot_pulses(fit: HppcFit, path: Path) -> None:
    picks = sorted({0, len(fit.pulses) // 2, len(fit.pulses) - 1})
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, len(picks), figsize=(3.4 * len(picks), 3.2), squeeze=False)
        for ax, k in zip(axes[0], picks):
            p = fit.pulses[k]
            t, v, model = p.segment
            ax.plot(t, v / fit.series, color=SERIES[0], linewidth=1.0, label="measured")
            ax.plot(t, model / fit.series, color=SERIES[1], linewidth=1.0, linestyle="--", label="model fit")
            ax.set_title(f"SoC {100 * p.soc:.0f} %")
            ax.set_xlabel("Time [s]")
            ax.set_ylabel("Cell voltage [V]")
        axes[0][0].legend(frameon=False, fontsize=8)
        fig.tight_layout()
        _save(fig, path)


def _plot_soc(fit: HppcFit, reference: dict | None, path: Path) -> None:
    soc = np.array([p.soc for p in fit.pulses]) * 100
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.2))
        ax = axes[0]
        ax.errorbar(soc, [1000 * p.r0 / fit.series for p in fit.pulses], yerr=[1000 * p.r0_se / fit.series for p in fit.pulses],
                    fmt="o", color=SERIES[0], label="R0")
        ax.errorbar(soc, [1000 * p.r1 / fit.series for p in fit.pulses], yerr=[1000 * p.r1_se / fit.series for p in fit.pulses],
                    fmt="s", color=SERIES[1], label="R1")
        ax.set_xlabel("State of charge [%]")
        ax.set_ylabel("Cell resistance [mΩ]")
        ax.set_ylim(bottom=0)
        ax.legend(frameon=False, fontsize=8)
        ax.set_title("Resistance per pulse")
        ax = axes[1]
        ax.plot(100 * fit.ocv_soc, fit.ocv_cell, "o-", color=SERIES[0], label="measured (relaxed)")
        if reference:
            ax.plot(100 * reference["soc"], reference["cell"], color=MUTED, linewidth=1.0, label="design data")
        ax.set_xlabel("State of charge [%]")
        ax.set_ylabel("Open-circuit cell voltage [V]")
        ax.set_title("Open-circuit voltage")
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        _save(fig, path)


def _plot_arrhenius(arr: ArrheniusFit, path: Path) -> None:
    temps = np.array([p[0] for p in arr.points])
    r0 = np.array([p[1] for p in arr.points])
    x = 1000.0 / temps
    line_t = np.linspace(temps.min() - 5, temps.max() + 5, 50)
    line = arr.r0_ref.value * np.exp(arr.activation_energy.value / 8.314462618 * (1 / line_t - 1 / arr.t_ref))
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(5.0, 3.4))
        ax.semilogy(x, 1000 * r0, "o", color=SERIES[0], label="per test")
        ax.semilogy(1000.0 / line_t, 1000 * line, color=SERIES[1], linewidth=1.0, label="Arrhenius fit")
        ax.set_xlabel("1000 / T [1/K]")
        ax.set_ylabel("Cell R0 [mΩ]")
        ax.set_title("Resistance against temperature")
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        _save(fig, path)


def _plot_flight(fit: FlightFit, series: int, path: Path) -> None:
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.0, 3.2))
        ax.plot(fit.t, fit.v_measured / series, color=SERIES[0], linewidth=0.8, label="vbat (log)")
        ax.plot(fit.t, fit.v_model / series, color=SERIES[1], linewidth=0.8, linestyle="--", label="model fit")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Cell voltage [V]")
        ax.set_title("In-flight fit")
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        _save(fig, path)


def generate(out_dir: Path, sources: list[str], fits: list[HppcFit], arrhenius: ArrheniusFit | None,
             flight: FlightFit | None, flight_source: str | None, series: int, design: dict | None = None) -> Path:
    """``design``: the build's current values for comparison (r0_cell, r1_cell, tau1, activation_energy,
    ocv_soc, ocv_cell, name)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    add = md.append
    add("# 電池參數辨識報告\n")
    add("> 由 `fpvsim fit-battery` 自動產生。脈衝放電測試（HPPC）或飛行 log 的數據以 Thevenin 模型擬合，"
        "結果附標準不確定度，可以直接取代零件檔中的估計值。\n")
    add(md_table(["項目", "內容"], [
        ["數據", "、".join(f"`{s}`" for s in sources + ([flight_source] if flight_source else []))],
        ["串聯數", str(series)],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(Path.cwd())}`"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")

    if fits:
        add("## 1. 脈衝放電測試（HPPC）\n")
        add("每個電量點：靜置到電壓穩定（讀開路電壓）→ 放電脈衝 → 靜置看電壓恢復。每個脈衝與它後面的恢復段一起用"
            "Thevenin 模型以非線性最小平方擬合：脈衝邊緣的瞬間壓降決定 R0，脈衝中慢慢增加、靜置時慢慢恢復的部分決定 R1 與 τ1。"
            "開路電壓在一個脈衝的範圍內視為直線。\n")
        rows = []
        for src, f in zip(sources, fits):
            rows.append([f"`{src}`", f"{f.temperature - 273.15:.1f} °C", str(len(f.pulses)),
                         f"{_mohm(f.r0_cell.value)} ± {_mohm(f.r0_cell.u)}", f"{_mohm(f.r1_cell.value)} ± {_mohm(f.r1_cell.u)}",
                         f"{f.tau1.value:.2f} ± {f.tau1.u:.2f}",
                         f"{1000 * max(p.residual_rms for p in f.pulses) / series:.1f} mV"])
        add(md_table(["數據", "溫度", "脈衝數", "單芯 R0 (mΩ)", "單芯 R1 (mΩ)", "τ1 (s)", "最大殘差（單芯 RMS）"], rows))
        add("\n不確定度包含兩部分：單一脈衝擬合的統計誤差，以及不同電量之間的差異。"
            "模型假設內阻不隨電量變化；如果各脈衝的值有系統性的趨勢（真實電池在低電量時內阻通常上升），"
            "這個差異就代表模型本身的誤差。\n")
        # the test nearest the design's reference temperature is the one written back and shown in detail
        t_ref = design.get("t_ref", 298.15) if design else 298.15
        k_main = min(range(len(fits)), key=lambda k: abs(fits[k].temperature - t_ref))
        main = fits[k_main]
        _plot_pulses(main, out_dir / "pulses.png")
        reference = {"soc": design["ocv_soc"], "cell": design["ocv_cell"]} if design else None
        _plot_soc(main, reference, out_dir / "soc.png")
        add(f"`{Path(sources[k_main]).name}`（{main.temperature - 273.15:.0f} °C，最接近設計的參考溫度）的擬合"
            "（低、中、高電量各一個脈衝）：\n")
        add("![Pulse fits](pulses.png)\n")
        add("![Resistance and OCV](soc.png)\n")
        add(md_table(["電量", "開路電壓（單芯）", "R0 (mΩ)", "R1 (mΩ)", "τ1 (s)"], [
            [f"{100 * p.soc:.0f}%", f"{p.ocv / series:.3f} V", f"{_mohm(p.r0 / series)} ± {_mohm(p.r0_se / series)}",
             f"{_mohm(p.r1 / series)} ± {_mohm(p.r1_se / series)}", f"{p.tau:.2f} ± {p.tau_se:.2f}"]
            for p in main.pulses
        ]))
        add("")

    if arrhenius:
        add("## 2. 內阻對溫度\n")
        add("不同溫度的測試以 ln R0 = ln R_ref + (Eₐ/R)(1/T − 1/T_ref) 迴歸，得到 Arrhenius 活化能。\n")
        _plot_arrhenius(arrhenius, out_dir / "arrhenius.png")
        add(md_table(["參數", "數值"], [
            ["活化能 Eₐ", f"{arrhenius.activation_energy.value / 1000:.2f} ± {arrhenius.activation_energy.u / 1000:.2f} kJ/mol"],
            [f"單芯 R0（{arrhenius.t_ref - 273.15:.0f} °C）", f"{_mohm(arrhenius.r0_ref.value)} ± {_mohm(arrhenius.r0_ref.u)} mΩ"],
        ]))
        add("\n![Arrhenius](arrhenius.png)\n")

    if flight:
        add(f"## {3 if fits else 1}. 飛行 log\n")
        add("整段飛行用同一個模型擬合，開路電壓取自設計的 OCV 曲線，電量由電流積分（假設起飛時滿電）。"
            "得到的電阻包含電池到 vbat 量測點之間的線路，而且是飛行中各種溫度與電量的平均，只能當作檢查，不能取代脈衝測試。\n")
        _plot_flight(flight, series, out_dir / "flight.png")
        add(md_table(["參數", "數值"], [
            ["電池 + 線路電阻（整包）", f"{1000 * flight.r_total.value:.2f} ± {1000 * flight.r_total.u:.2f} mΩ"],
            ["R1（整包）", f"{1000 * flight.r1.value:.2f} ± {1000 * flight.r1.u:.2f} mΩ"],
            ["τ1", f"{flight.tau.value:.1f} ± {flight.tau.u:.1f} s"],
            ["殘差（單芯 RMS）", f"{1000 * flight.residual_rms / series:.1f} mV"],
        ]))
        quiet = flight.residual_rms / series < 1e-4
        add(f"\n誤差是{flight.r_total.note}。" + ("模擬的 log 沒有量測雜訊，所以統計誤差接近零。" if quiet else "") + "\n")
        add("![In-flight fit](flight.png)\n")

    if fits:
        add(f"## {4 if flight else 3}. 寫回零件檔\n")
        ref = Path(sources[k_main]).name
        add(f"取最接近設計參考溫度的測試（`{ref}`，{main.temperature - 273.15:.1f} °C）；`r_ref_temperature` 就是它的溫度。\n")
        lines = [
            f'r0_cell = {{ value = {1000 * main.r0_cell.value:.3f}, unit = "mohm", source = "measured", '
            f'u = {1000 * main.r0_cell.u:.3f}, ref = "{ref}", note = "HPPC，{main.temperature - 273.15:.0f} °C" }}',
            f'r1_cell = {{ value = {1000 * main.r1_cell.value:.3f}, unit = "mohm", source = "measured", '
            f'u = {1000 * main.r1_cell.u:.3f}, ref = "{ref}" }}',
            f'tau1 = {{ value = {main.tau1.value:.2f}, unit = "s", source = "measured", u = {main.tau1.u:.2f}, ref = "{ref}" }}',
            f'r_ref_temperature = {{ value = {main.temperature - 273.15:.1f}, unit = "degC", source = "measured", ref = "{ref}" }}',
        ]
        if arrhenius:
            lines.append(f'resistance_activation_energy = {{ value = {arrhenius.activation_energy.value / 1000:.2f}, unit = "kJ/mol", '
                         f'source = "measured", u = {arrhenius.activation_energy.u / 1000:.2f}, ref = "{", ".join(Path(x).name for x in sources)}" }}')
        add("```toml\n[params]\n" + "\n".join(lines) + "\n```\n")
        add("開路電壓的量測點（電量 0% 需要另做完整放電測試）：\n")
        add("```toml\n[ocv]\nsource = \"measured\"\n"
            f"soc = [{', '.join(f'{x:.3f}' for x in main.ocv_soc)}]\n"
            f"cell_voltage = [{', '.join(f'{x:.4f}' for x in main.ocv_cell)}]\n```\n")
        if design:
            add("與設計數據比較：\n")
            rows = [
                ["單芯 R0", f"{_mohm(design['r0_cell'])} mΩ", f"{_mohm(main.r0_cell.value)} ± {_mohm(main.r0_cell.u)} mΩ"],
                ["單芯 R1", f"{_mohm(design['r1_cell'])} mΩ", f"{_mohm(main.r1_cell.value)} ± {_mohm(main.r1_cell.u)} mΩ"],
                ["τ1", f"{design['tau1']:.2f} s", f"{main.tau1.value:.2f} ± {main.tau1.u:.2f} s"],
            ]
            if arrhenius:
                rows.append(["活化能", f"{design['activation_energy'] / 1000:.1f} kJ/mol",
                             f"{arrhenius.activation_energy.value / 1000:.2f} ± {arrhenius.activation_energy.u / 1000:.2f} kJ/mol"])
            add(md_table(["參數", f"設計數據（{design.get('name', '')}）", "辨識結果"], rows))
            if abs(main.temperature - t_ref) > 0.5:
                add(f"\n注意：設計數據的內阻是 {t_ref - 273.15:.0f} °C 的值，辨識結果是 {main.temperature - 273.15:.0f} °C 的值，兩者不能直接比較。\n")
            else:
                add(f"\n兩者都是 {t_ref - 273.15:.0f} °C 的值。\n")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
