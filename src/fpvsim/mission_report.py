"""Mission endurance report (``fpvsim mission``)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np

from . import __version__, plots
from .design import Build
from .flight_report import wind_text
from .flightcontroller import FcConfig
from .mission import MissionResult, lap_table
from .report import git_version, md_table, rel_path


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
    avg = np.convolve(v_cell, np.ones(width) / width, mode="same")
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
        ["每圈", f"`{log.meta.get('input')}`，{result.lap_duration:g} s"],
        ["風", wind_text(log.meta)],
        ["物理更新率", f"{result.physics_rate:g} Hz（RK4），記錄 {log.rate:g} Hz"],
        ["程式版本", f"fpvsim {__version__}，git `{git_version(build.path.parent)}`"],
        ["輸入檔雜湊", f"`{log.meta.get('input_hash')}`"],
        ["參數覆寫", ", ".join(f"`{k}` = {v:g}" for k, v in (log.meta.get("overrides") or {}).items()) or "無"],
        ["產生時間 (UTC)", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")],
    ]))
    add("")
    add("## 摘要\n")
    add(md_table(["項目", "數值"], [
        ["任務時間", f"{result.time:.0f} s（{result.time / 60:.1f} min），{result.laps:.1f} 圈"],
        ["結束原因", result.reason_zh],
        ["懸停續航（設計報告）", f"{result.hover_endurance:.0f} s；任務時間為其 {result.time / result.hover_endurance:.0%}"],
        ["用電量", f"{log['mah'][-1]:.0f} mAh（剩餘 {100 * log['soc'][-1]:.0f}%），{energy:.1f} Wh"],
        ["平均功率 / 平均電流", f"{power.mean():.0f} W / {log['current'].mean():.1f} A"],
        ["最大電流", f"{log['current'].max():.0f} A"],
        ["最低單芯電壓（瞬間 / 1 秒平均）", f"{v_cell.min():.2f} / {avg[width // 2:len(avg) - width // 2].min():.2f} V（下限 {v_min:.2f} V）"],
        ["電池溫度（起飛 → 最高）", f"{log['batt_temp'][0]:.1f} → {log['batt_temp'].max():.1f} °C"],
    ]))
    add("")
    add("![Mission](mission.png)\n")
    add("## 1. 各圈\n")
    add(md_table(["圈", "開始 s", "用電 mAh", "平均功率 W", "最低單芯電壓（1 秒平均）", "最高電池溫度"], [
        [f"{r['lap']}" + ("" if r["complete"] else "（未完成）"), f"{r['start']:.0f}", f"{r['mah']:.0f}", f"{r['power']:.0f}",
         f"{r['min_cell_avg']:.2f} V", f"{r['max_temp']:.1f} °C"] for r in laps
    ]))
    add("")
    add("## 2. 驗證\n")
    soc_mah = (1.0 - log["soc"][-1]) * ac.battery.capacity / 3.6
    add(f"- 電荷守恆：記錄的用電量（∫I dt）{log['mah'][-1]:.1f} mAh，電池模型的電量變化 {soc_mah:.1f} mAh，"
        f"相差 {log['mah'][-1] / soc_mah - 1:+.2%}（記錄取樣的離散化）。")
    add("")
    add("## 3. 方法與限制\n")
    add("- 結束條件：保留電量、單芯電壓的 1 秒平均值達到下限（相當於 OSD 低電壓警告；衝刺時的瞬間壓降不算）、電池溫度上限、墜機。")
    add("- 測試飛手每圈開始時依電池目前的狀態重新估計懸停油門，就像真人飛手會隨電壓下降加油門；它不代表真人的飛行風格。")
    add("- 每圈的衝刺讓高度增加，之後就地懸停；模型的空氣密度固定在規格的高度（無風時高度不影響結果）。")
    add("- 物理以 4 kHz 計算（陀螺儀與 PID 迴圈也是 4 kHz），以減少計算時間；調參與飛行測試報告用 8 kHz。")
    add("- 沒有馬達溫升（銅損使電阻上升、磁鐵升溫使 Kt 下降），長時間大電流飛行時會讓結果偏樂觀（見 docs/physics-roadmap.md）。")
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
