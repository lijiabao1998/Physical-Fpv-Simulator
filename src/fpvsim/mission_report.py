"""Mission endurance report (``fpvsim mission``)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np

from . import plots
from .design import Build
from .flight_report import envelope, wind_text
from .flightcontroller import FcConfig
from .mission import MissionResult, lap_table
from .report import code_version_text, md_table, rel_path


def generate(build: Build, cfg: FcConfig, result: MissionResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    log = result.log
    # a reduced copy (10 Hz, battery, power and flight path): the full log of a whole pack is tens of MB
    every = max(1, int(round(log.rate / 10.0)))
    keep = ["time", "rc_throttle", "vbat", "current", "mah", "soc", "batt_temp", "alt", "vel_n", "vel_e", "vel_d", "airspeed",
            *[c for c in log.columns if c.startswith("motor_") and not c.startswith("motor_current")],
            *[c for c in log.columns if c.startswith("rpm_")]]
    log.write_csv(out_dir / "mission_log.csv", keep, every)
    ac = build.realize(log.meta.get("overrides") or None)
    cells = ac.battery.series
    t = log.time
    v_cell = log["vbat"] / cells
    width = max(1, int(round(log.rate)))
    # trailing 1 s average, what the stop condition uses (shorter flights: the average so far)
    csum = np.cumsum(np.concatenate([[0.0], v_cell]))
    k = np.arange(1, len(v_cell) + 1)
    lo = np.maximum(k - width, 0)
    avg = (csum[k] - csum[lo]) / (k - lo)
    energy = float(np.trapezoid(log["vbat"] * log["current"], t)) / 3600.0
    power = log["vbat"] * log["current"]
    laps = lap_table(result, cells)
    v_min = ac.criteria.min_cell_voltage

    plots.timeseries([
        {"title": "Cell voltage at the ESC", "ylabel": "V", "series": [("instant", t, v_cell), ("1 s average", t, avg)],
         "refs": [(v_min, "limit")]},
        {"title": "Battery current", "ylabel": "A", "series": [("current", t, log["current"])]},
        {"title": "State of charge", "ylabel": "%", "series": [("SoC", t, 100 * log["soc"])],
         "refs": [(100 * ac.criteria.reserve_soc, "reserve")]},
        {"title": "Battery temperature", "ylabel": "degC", "series": [("pack", t, log["batt_temp"])]},
        {"title": "Altitude", "ylabel": "m", "series": [("altitude", t, log["alt"])]},
    ], out_dir / "mission.png")

    md: list[str] = []
    add = md.append
    add(f"# 任務續航報告：{build.name}\n")
    add("> 由 `fpvsim mission` 自動產生。6DOF 模擬重複飛同一段飛行腳本，從滿電飛到電池用盡；方法見 docs/battery.md。"
        "`mission_log.csv` 是 10 Hz 的精簡 log（電池、油門、轉速與飛行路徑）。\n")
    add(md_table(["項目", "內容"], [
        ["機體", f"{build.name}（`{rel_path(build.path, Path.cwd())}`）"],
        ["飛控設定", f"{cfg.name}（`{cfg.id}`）；陀螺儀與 PID 迴圈 {cfg.pid_rate:g} Hz"],
        ["每圈", f"`{log.meta.get('input')}` 腳本 {result.lap_duration:g} s，之後前飛下降回到起始高度再開始下一圈"],
        ["風", wind_text(log.meta)],
        ["槳的斜向氣流係數表", f"`{log.meta['rotor_tables']}`（rotor_ff.py，輸入與求解器的雜湊）" if log.meta.get("rotor_tables")
         else "未使用（槳沒有葉片幾何，用軸向係數表）"],
        ["物理更新率", f"{result.physics_rate:g} Hz（RK4），記錄 {log.rate:g} Hz"],
        ["程式版本", code_version_text()],
        ["輸入檔雜湊", f"`{log.meta.get('input_hash')}`"],
        ["參數覆寫", ", ".join(f"`{k}` = {v:g}" for k, v in (log.meta.get("overrides") or {}).items()) or "無"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    add(md_table(["項目", "數值"], [
        ["任務時間", f"{result.time:.0f} s（{result.time / 60:.1f} min），{result.laps:.1f} 圈"],
        ["結束原因", result.reason_zh],
        ["懸停續航（設計報告）", f"{result.hover_endurance:.0f} s" + (f"；任務時間為其 {result.time / result.hover_endurance:.0%}"
                                                                    if result.hover_endurance > 0 else "（同樣的限制在起飛時就已達到）")],
        ["用電量", f"{log['mah'][-1]:.0f} mAh（剩餘 {100 * log['soc'][-1]:.0f}%），{energy:.1f} Wh"],
        ["平均功率 / 平均電流", f"{power.mean():.0f} W / {log['current'].mean():.1f} A"],
        ["最大電流", f"{log['current'].max():.0f} A"],
        ["最低單芯電壓（瞬間 / 1 秒平均）", f"{v_cell.min():.2f} / {avg.min():.2f} V（下限 {v_min:.2f} V）"],
        ["電池溫度（起飛 → 最高）", f"{log['batt_temp'][0]:.1f} → {log['batt_temp'].max():.1f} °C"],
    ]))
    add("")
    add("![Mission](mission.png)\n")
    add("## 1. 各圈\n")
    add(md_table(["圈", "開始 s", "長度 s", "開始高度 m", "最高高度 m", "用電 mAh", "平均功率 W", "最低單芯電壓（1 秒平均）", "最高電池溫度"], [
        [f"{r['lap']}" + ("" if r["complete"] else "（未完成）"), f"{r['start']:.0f}", f"{r['length']:.0f}", f"{r['start_alt']:.1f}",
         f"{r['max_alt']:.0f}", f"{r['mah']:.0f}", f"{r['power']:.0f}", f"{r['min_cell_avg']:.2f} V", f"{r['max_temp']:.1f} °C"]
        for r in laps
    ]))
    add("")
    add("## 2. 模型適用範圍\n")
    add("整段任務超出模型適用範圍的時間比例（與飛行測試報告相同的監測）：\n")
    j_max = float(ac.powertrain.prop.curves.J[-1])
    rows = [[e.title, f"{e.fraction:.1%}", "—" if e.first is None else f"{e.first:.1f} s", e.note]
            for e in envelope(log, j_max, oblique=ac.powertrain.prop.blade is not None)]
    add(md_table(["狀態", "時間比例", "第一次出現", "影響"], rows))
    add("")
    add("渦環狀態區的時間主要來自腳本的收油下墜與其後的改出（腳本刻意測試這一段）；飛回起始高度的下降以前飛進行，"
        "低空速時下降率限制在 0.4 倍懸停誘導速度。\n")
    add("## 3. 驗證\n")
    soc_mah = (1.0 - log["soc"][-1]) * ac.battery.capacity / 3.6
    diff = f"相差 {log['mah'][-1] / soc_mah - 1:+.2%}" if soc_mah > 1e-9 else "（任務太短，沒有可比較的用電）"
    add(f"- 電荷一致性：記錄的用電量（模擬迴圈每個物理步長以前向歐拉累加電流）{log['mah'][-1]:.1f} mAh，電池模型以 RK4 積分的電量變化 {soc_mah:.1f} mAh，"
        f"{diff}。兩者都在物理步長上積分同一個模擬電流，所以這只檢查積分方法的一致性，不能檢查物理模型本身。")
    add("")
    add("## 4. 方法與限制\n")
    add("- 結束條件：保留電量、單芯電壓的 1 秒平均值達到下限（相當於 OSD 低電壓警告；衝刺時的瞬間壓降不算）、電池溫度上限、墜機。")
    add("- 測試飛手每圈開始時依電池目前的狀態重新估計懸停油門，就像真人飛手會隨電壓下降加油門；它不代表真人的飛行風格。")
    starts = [r["start_alt"] for r in laps[1:]]
    climb = f"每圈最高比開始高約 {np.median([r['max_alt'] - r['start_alt'] for r in laps]):.0f} m" if laps else "衝刺會爬升數十公尺"
    add(f"- {climb}；腳本結束後測試飛手以 2 倍懸停誘導速度的空速飛向起點、以最多 1 倍懸停誘導速度下降"
        f"（空速低於懸停誘導速度時降到 0.4 倍），回到起始高度 {log['alt'][0]:.0f} m 以上 1 m 內才開始下一圈"
        + (f"（各圈開始高度 {min(starts):.1f}–{max(starts):.1f} m）" if starts else "")
        + f"。這次任務的高度範圍 {log['alt'].min():.0f}–{log['alt'].max():.0f} m。空氣密度固定在規格的高度。")
    add("- 物理以 4 kHz 計算（陀螺儀與 PID 迴圈也是 4 kHz），以減少計算時間；調參與飛行測試報告用 8 kHz。")
    add("- 沒有馬達溫升（銅損使電阻上升、磁鐵升溫使 Kt 下降），長時間大電流飛行時會讓結果偏樂觀（見 docs/physics-roadmap.md）。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
