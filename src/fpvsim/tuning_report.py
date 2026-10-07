"""Stage 5 tuning report."""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

import numpy as np

from . import __version__, plots
from . import flightanalysis as fa
from .design import Build
from .filters import chain_response, group_delay, make_lowpass
from .flightcontroller import dump_fc_config
from .report import git_version, md_table, rel_path
from .tuning import NOISE_BAND, TuningStudy, filter_delay

AXES = ("roll", "pitch", "yaw")
AXIS_ZH = {"roll": "滾轉", "pitch": "俯仰", "yaw": "偏航"}


def _pct(x: float) -> str:
    return "—" if not math.isfinite(x) else f"{100 * x:.1f}%"


def _ms(x: float) -> str:
    return "—" if not math.isfinite(x) else f"{1000 * x:.1f} ms"


def generate(build: Build, study: TuningStudy, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = study.baseline
    fs = cfg.pid_rate
    base_noise = study.noise_runs[0]
    log = base_noise["log"]
    fmax = 0.5 * log.rate

    # --------------------------------------------------------------- figures
    throttle = np.mean([log[f"motor_{i}"] for i in range(len(build.rotors))], axis=0)
    tmap = fa.throttle_map(log["gyro_raw_roll"], throttle, log.rate)
    plots.throttle_noise_map(tmap, out_dir / "throttle_map.png", "Raw gyro (roll) noise vs throttle", fmax)

    gyro_series = [("raw gyro", *fa.psd(log["gyro_raw_roll"], log.rate), "raw")]
    motor_series = []
    for run in study.noise_runs:
        lg = run["log"]
        gyro_series.append((run["label_en"], *fa.psd(lg["gyro_roll"], lg.rate), "filtered"))
        motor_series.append((run["label_en"], *fa.psd(lg["motor_0"], lg.rate), "filtered"))
    plots.spectra(
        [
            {"title": "Roll gyro: raw and after filtering", "ylabel": "PSD [dB re (deg/s)²/Hz]", "series": gyro_series},
            {"title": "Motor 1 output", "ylabel": "PSD [dB re %²/Hz]", "series": motor_series},
        ],
        out_dir / "spectra.png",
        fmax,
    )
    f = np.logspace(0, math.log10(0.49 * fs), 400)
    lighter = study.noise_runs[2]["cfg"]
    chains = []
    for label, specs in (
        ("gyro, baseline", cfg.gyro_lowpass),
        ("gyro, lighter", lighter.gyro_lowpass),
        ("D-term, baseline", cfg.dterm_lowpass),
        ("D-term, lighter", lighter.dterm_lowpass),
    ):
        h = chain_response([make_lowpass(s.kind, s.cutoff, fs) for s in specs], f, fs)
        chains.append((label, h, group_delay(h, f)))
    plots.bode(chains, f, out_dir / "filters.png")

    base = next((c for c in study.candidates if c.pd == 1.0 and c.d == 1.0), None)
    rec = study.recommended
    plots.pareto(
        [
            {
                "label": c.label,
                "x": c.metrics["motor_noise"],
                "y": c.metrics["tracking_rp"],
                "feasible": c.feasible,
                "highlight": "recommended" if c is rec else ("baseline" if c is base else None),
            }
            for c in study.candidates
        ],
        out_dir / "pareto.png",
        f"Motor-output noise, {NOISE_BAND[0]:.0f}-{NOISE_BAND[1]:.0f} Hz RMS [%]",
        "Roll/pitch tracking error RMS [deg/s]",
    )
    if base and rec:
        panels = []
        for axis in AXES:
            series = []
            for label, cand in (("baseline", base), ("recommended", rec)):
                step = cand.metrics["axes"][axis]["step"]
                if step:
                    series.append((label, np.array(step[0]), np.array(step[1]), np.array(step[2])))
            panels.append({"title": axis.capitalize(), "series": series})
        plots.step_compare(panels, out_dir / "steps.png")

    if rec:
        (out_dir / "recommended_fc.toml").write_text(
            dump_fc_config(rec.cfg, f"{cfg.id}-tuned", f"{cfg.name}（調參建議 {rec.label}）",
                           f"fpvsim tune recommendation: {rec.label} applied to {cfg.id}"),
            encoding="utf-8",
        )

    # -------------------------------------------------------------- markdown
    md: list[str] = []
    add = md.append
    add(f"# 調參報告：{build.name}\n")
    add("> 由 `fpvsim tune` 自動產生。每次試飛使用相同的隨機種子與飛行腳本，所以候選設定之間的差異只來自設定本身。\n")
    add(md_table(["項目", "內容"], [
        ["機體", f"`{rel_path(build.path, Path.cwd())}`"],
        ["基準飛控設定", f"{cfg.name}（`{cfg.id}`）"],
        ["試飛次數", f"雜訊調查 {len(study.noise_runs)} 次，增益掃描 {len(study.candidates)} 次"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
        ["輸入檔雜湊", f"`{build.input_hash()[:16]}`"],
        ["隨機種子", str(study.seed)],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")

    add("## 摘要\n")
    no_rpm = study.noise_runs[1]["metrics"]["motor_noise"]
    with_rpm = base_noise["metrics"]["motor_noise"]
    add(f"- **RPM 濾波是最重要的濾波器：** 關閉它，馬達輸出雜訊從 {with_rpm:.3f}% 升到 {no_rpm:.3f}%（{no_rpm / with_rpm:.0f} 倍）。")
    if rec and base:
        bm, rm = base.metrics, rec.metrics
        bo = {a: bm["axes"][a].get("overshoot", math.nan) for a in ("roll", "pitch")}
        ro = {a: rm["axes"][a].get("overshoot", math.nan) for a in ("roll", "pitch")}
        add(f"- **建議增益：** {rec.label}。滾轉超調 {_pct(bo['roll'])} → {_pct(ro['roll'])}，"
            f"俯仰超調 {_pct(bo['pitch'])} → {_pct(ro['pitch'])}，"
            f"追蹤誤差 {bm['tracking_rp']:.1f} → {rm['tracking_rp']:.1f} deg/s，"
            f"馬達輸出雜訊 {bm['motor_noise']:.3f}% → {rm['motor_noise']:.3f}%。設定檔：`recommended_fc.toml`。")
        if bo["roll"] - bo["pitch"] > 0.05:
            inertia = build.realize().mass_props.inertia * 1000
            add(f"- **滾轉比俯仰更容易超調**（基準設定 {_pct(bo['roll'])} 對 {_pct(bo['pitch'])}），"
                f"與兩軸慣性不同一致（Ixx = {inertia[0, 0]:.2f}、Iyy = {inertia[1, 1]:.2f} g·m²，"
                "同樣的增益在慣性較小的軸上等於較高的迴路增益）。本次掃描對三軸使用相同倍數，下一輪應分軸調整。")
    elif not rec:
        add("- **沒有候選設定符合條件。** 請擴大掃描範圍或放寬條件。")
    if study.at_grid_edge:
        add(f"- **建議值落在掃描範圍邊緣（{'、'.join(study.at_grid_edge)}）**，更好的設定可能在範圍外，下一輪應往該方向擴大掃描。")
    worst = max(study.candidates, key=lambda c: c.metrics["motor_noise"])
    add(f"- 增益最高的設定（{worst.label}）馬達雜訊 {worst.metrics['motor_noise']:.3f}%，是基準的 "
        f"{worst.metrics['motor_noise'] / base.metrics['motor_noise']:.0f} 倍：增益再往上就會碰到雜訊放大的懸崖。" if base else "")
    add("- **可信度：** 振動模型的振幅是估計值，所以雜訊的**絕對數值**尚未確認；"
        "但同一個模型下，不同設定之間的**相對比較**是有意義的。用實機的未濾波陀螺儀 log 辨識振動參數後，絕對數值才能採信。\n")

    add("## 1. 雜訊調查\n")
    add(f"油門掃描飛行（從低油門爬到全油門再收回，保持水平），以 PID 迴圈頻率 {log.rate:g} Hz 記錄。"
        "下圖是未濾波陀螺儀的頻譜對油門：隨油門移動的斜線是馬達轉速的諧波（1 倍、2 倍與葉片通過頻率）。\n")
    add("![Throttle map](throttle_map.png)\n")
    add("![Spectra](spectra.png)\n")
    rows = []
    for run in study.noise_runs:
        m = run["metrics"]
        c = run["cfg"]
        rows.append([
            run["label"],
            f"{m['axes']['roll']['gyro_raw_noise']:.2f}",
            f"{m['axes']['roll']['gyro_noise']:.3f}",
            f"{m['axes']['roll']['dterm_noise']:.2f}",
            f"{m['motor_noise']:.3f}",
            _ms(filter_delay(c.gyro_lowpass, fs)),
            _ms(filter_delay(c.gyro_lowpass + c.dterm_lowpass, fs)),
        ])
    add(md_table(["濾波設定", "原始陀螺儀 (deg/s)", "濾波後陀螺儀 (deg/s)", "D 項 (PID 單位)", "馬達輸出 (%)",
                  "陀螺儀濾波延遲", "D 項總延遲"], rows))
    add(f"\n雜訊為 {NOISE_BAND[0]:.0f}–{NOISE_BAND[1]:.0f} Hz 的 RMS（滾轉軸；馬達為四顆平均）。延遲為 50 Hz 的群延遲；"
        "D 項總延遲包含陀螺儀濾波與 D 項濾波。RPM 濾波的陷波器很窄，在 50 Hz 附近幾乎不增加延遲。\n")

    add("## 2. 濾波器\n")
    add("![Filters](filters.png)\n")
    rpm_hz = np.mean([np.median(log[f"rpm_{i}"]) for i in range(len(build.rotors))]) / 60.0
    add(f"RPM 濾波：每顆馬達 {cfg.rpm_harmonics} 個諧波的陷波器，Q = {cfg.rpm_q:g}，最低 {cfg.rpm_min_hz:g} Hz。"
        f"以這次飛行的轉速中位數（{rpm_hz * 60:.0f} rpm）為例，陷波中心在 "
        + "、".join(f"{h * rpm_hz:.0f} Hz" for h in range(1, cfg.rpm_harmonics + 1)) + "。\n")

    add("## 3. 增益掃描\n")
    add("以基準設定為中心，P 與 D 一起乘上「PD 倍數」，D 再另外乘上「D 倍數」，I 與 F 不變。"
        "每個候選飛同一段調參飛行（三軸打桿），步階響應由飛行數據以反卷積求得；雜訊只在最後一段平飛油門爬升中量測，"
        "因為打桿本身的訊號也落在同一個頻帶。\n")
    add(f"**判定規則：** {study.rule}\n")
    rows = []
    for c in study.candidates:
        m = c.metrics
        ax = m["axes"]
        mark = "★ 建議" if c is rec else ("基準" if c is base else "")
        rows.append([
            c.label + (f"（{mark}）" if mark else ""),
            _pct(ax["roll"].get("overshoot", math.nan)),
            _pct(ax["pitch"].get("overshoot", math.nan)),
            _ms(ax["roll"].get("rise_time", math.nan)),
            f"{m['tracking_rp']:.1f}",
            f"{m['motor_noise']:.3f}",
            f"{100 * m['saturation']:.1f}%",
            "符合" if c.feasible else "不符合",
        ])
    add(md_table(["候選", "滾轉超調", "俯仰超調", "滾轉上升時間", "追蹤誤差 (deg/s)", "馬達雜訊 (%)", "混控飽和", "條件"], rows))
    add("")
    add("![Pareto](pareto.png)\n")
    if base and rec:
        add("基準與建議設定的步階響應（陰影為各分析視窗之間的 ±1 標準差）：\n")
        add("![Step responses](steps.png)\n")
        add(md_table(["軸", "基準超調", "建議超調", "基準上升時間", "建議上升時間", "基準延遲", "建議延遲"], [
            [AXIS_ZH[a], _pct(base.metrics["axes"][a].get("overshoot", math.nan)), _pct(rec.metrics["axes"][a].get("overshoot", math.nan)),
             _ms(base.metrics["axes"][a].get("rise_time", math.nan)), _ms(rec.metrics["axes"][a].get("rise_time", math.nan)),
             _ms(base.metrics["axes"][a]["latency"]), _ms(rec.metrics["axes"][a]["latency"])]
            for a in AXES
        ]))
        add("")

    add("## 4. 建議設定\n")
    if rec:
        add(md_table(["軸", "基準 P / I / D / F", "建議 P / I / D / F"], [
            [AXIS_ZH[a], " / ".join(f"{v:.0f}" for v in (b.p, b.i, b.d, b.f)), " / ".join(f"{v:.0f}" for v in (r.p, r.i, r.d, r.f))]
            for a, b, r in zip(AXES, cfg.pids, rec.cfg.pids)
        ]))
        add("\n完整設定已寫入 `recommended_fc.toml`，可以直接用 `fpvsim fly --fc` 試飛。")
    add("\n下一步：")
    if study.at_grid_edge:
        add(f"1. 以建議值為中心、往 {'、'.join(study.at_grid_edge)} 增加的方向擴大掃描。")
    add(f"{2 if study.at_grid_edge else 1}. 用實機錄一段未濾波陀螺儀的 Blackbox log，辨識振動參數，讓雜訊的絕對數值可以採信。")
    add(f"{3 if study.at_grid_edge else 2}. 在建議設定下，評估「RPM 濾波 + 較輕的低通」能否在雜訊可接受時換到更低的延遲。\n")

    add("## 5. 方法與限制\n")
    add("- 步階響應：把飛行數據切成 1 秒、重疊 50% 的視窗，只用打桿量夠大的視窗，以 Wiener 反卷積求設定值到陀螺儀的脈衝響應，累加成步階響應後平均。"
        "此方法已用已知系統驗證（tests/test_flight.py）。")
    add("- 飛控依 Betaflight 的結構獨立實作（Actual rates、PID 數值尺度、D 項作用在量測值、RPM 濾波、airmode）；"
        "feedforward 的尺度、動態濾波、TPA、anti-gravity、I-term relax 等與 Betaflight 不同或沒有實作，所以調參結果是起點，不保證能一對一套用到實機。")
    add("- 振動只進入陀螺儀量測；機架共振與彈性沒有模擬。")
    add("- 試飛由自動測試飛手執行，它是測試工具，不代表人類飛手。")
    path = out_dir / "report.md"
    path.write_text("\n".join(m for m in md if m is not None) + "\n", encoding="utf-8")
    return path
