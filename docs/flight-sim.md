# 飛行模擬與調參（第 5、6 階段）

## 架構

```
自動測試飛手 / 搖桿輸入檔 ──250 Hz──▶ 飛控（4 kHz）──馬達指令──▶ 6DOF 動力學（8 kHz, RK4）
                                      ▲                                  │
                                      └──── 陀螺儀（8 kHz，平均到 4 kHz）◀─┘
                                      └──── 馬達轉速遙測（RPM 濾波用）◀───┘
                                                       │
                                               虛擬 Blackbox（log）
```

| 模組 | 內容 |
|---|---|
| `dynamics.py` | 剛體 6DOF、馬達與 ESC 動態、槳 Ct(J)、槳盤阻力、機身阻力、電池、地面接觸 |
| `sensors.py` | 陀螺儀：白雜訊與鎖定轉速的振動 |
| `filters.py` | PT1/PT2/PT3、biquad 低通與陷波，含精確頻率響應 |
| `flightcontroller.py` | Acro 飛控：Actual rates、PID、濾波、RPM 濾波、airmode 混控 |
| `pilot.py` | 自動測試飛手與飛行腳本；搖桿輸入檔 |
| `sim.py` | 多速率模擬迴圈 |
| `blackbox.py` | 飛行 log |
| `flightanalysis.py` | 頻譜、油門頻譜圖、步階響應（已知步階時刻的直接量測；一般 log 用反卷積）、延遲、追蹤誤差 |
| `tuning.py` | 雜訊調查、濾波比較、增益掃描與建議 |
| `flight_report.py`、`tuning_report.py` | 報告 |

## 使用方式

```bash
fpvsim maneuvers                                   # 列出內建飛行腳本
fpvsim fly  data/builds/ref-5in-6s-freestyle.toml --fc data/fc/acro-5in-baseline.toml --maneuver freestyle
fpvsim fly  data/builds/ref-5in-6s-freestyle.toml --fc data/fc/acro-5in-baseline.toml --sticks my_sticks.csv
fpvsim tune data/builds/ref-5in-6s-freestyle.toml --fc data/fc/acro-5in-baseline.toml
```

`fly` 輸出飛行 log（CSV）與飛行測試報告；`tune` 約需 2–3 分鐘（18 次試飛，平行執行），輸出調參報告與建議的飛控設定檔 `recommended_fc.toml`。

搖桿輸入檔格式（取樣保持，可以用實機 Blackbox 的搖桿數據轉成這個格式）：

```
time [s],roll [1],pitch [1],yaw [1],throttle [1]
0.0,0,0,0,0.16
```

搖桿方向：滾轉與偏航向右為正；俯仰**向前推為正**（機頭向下）；油門 0–1。

## 飛控設定檔

`data/fc/*.toml` 是設定值，不是物理量，所以沒有出處與不確定度。增益使用 Betaflight 的數值尺度。

```toml
[loop]      gyro_rate_hz、pid_rate_hz（陀螺儀頻率必須是 PID 頻率的整數倍）
[rc]        link_rate_hz、setpoint_smoothing_hz、feedforward_smoothing_hz
[rates]     各軸 { center, max, expo }（Actual rates，deg/s）
[pid]       各軸 { p, i, d, f }
[pid_limits]  pidsum_limit、pidsum_limit_yaw、iterm_limit
[filters]   gyro_lowpass、dterm_lowpass（PT1/PT2/PT3/biquad 串接）、rpm_filter { harmonics, q, min_hz }
[mixer]     airmode
```

### 和 Betaflight 的關係

依公開資料獨立實作，沒有使用 Betaflight 的原始碼。

| 項目 | 狀態 |
|---|---|
| Actual rates 曲線 | 依 Betaflight PR #9495 的描述實作：中心靈敏度線性項加上到最大角速度的「楔形」斜坡，由 expo 調整形狀，三個參數互相獨立。測試檢查這些性質。 |
| P、I、D 增益尺度 | 使用 Betaflight 公開的常數（P 0.032029、I 0.244381、D 0.000529）；PID 和以 1000 為滿油門範圍，限制 500 / 400（偏航） |
| D 項 | 作用在濾波後的量測值上 |
| Feedforward | 平滑後的設定值微分；尺度為本專案自訂，Betaflight 的平均、抖動抑制與 boost 沒有實作 |
| 濾波器 | 靜態低通與 RPM 濾波；動態低通、動態陷波沒有實作。PT1 的增益依精確 −3 dB 求解（見 `filters.py`），與常見韌體的近似公式略有不同 |
| 沒有實作 | TPA、anti-gravity、I-term relax、推力線性化、動態 idle、自穩模式（Angle/Horizon） |

所以 Betaflight 的設定可以當作起點，但調參結果不保證能一對一套用到實機。

## 自動測試飛手

測試飛行需要有人在打桿之間把飛機穩住。自動測試飛手看著真實狀態（位置、速度、姿態），用位置與高度保持算出想要的姿態，再換算成 Acro 模式的搖桿量（反查 rates 曲線）。飛行腳本覆蓋某些軸的搖桿時，其他軸仍由測試飛手控制；覆蓋結束時，測試飛手就在當下的位置保持。

它是測試工具，不是人類飛手模型，也不是飛機的一部分。

## 飛行 log 欄位

| 欄位 | 說明 | 真機可得 |
|---|---|---|
| `rc_*` | 搖桿 | ✓ |
| `setpoint_*` | 平滑後的設定角速度 | ✓ |
| `gyro_raw_*`、`gyro_*` | 未濾波與濾波後陀螺儀 | ✓ |
| `p_*`、`i_*`、`d_*`、`f_*` | PID 各項（1000 = 滿油門範圍） | ✓ |
| `motor_*`、`rpm_*` | 馬達指令（%）、轉速遙測 | ✓ |
| `vbat`、`current`、`mah` | 電池電壓、電流、用電量 | ✓ |
| `pos_*`、`alt`、`vel_*`、`att_*`、`rate_*` | 真實位置、速度、姿態、角速度 | 模擬限定 |
| `motor_current_*`、`thrust_*` | 各馬達相電流、推力 | 模擬限定 |
| `saturated`、`on_ground`、`descent_ratio`、`max_advance_ratio`、`tip_mach`、`soc` | 混控飽和與模型適用範圍監測 | 模擬限定 |

真機可得的欄位可以用相同的分析工具處理實機 Blackbox 數據（需先轉成同樣的欄位名稱與單位）。

## 模型適用範圍監測

飛行報告會列出每種狀況占飛行時間的比例：

| 監測 | 門檻 | 原因 |
|---|---|---|
| 下降進入自身尾流 | 軸向下降速度 > 0.5 倍懸停誘導速度 | 動量理論失效；渦環狀態與 propwash 沒有模擬 |
| 前進比超出槳係數表 | J ≥ 表格最大值 | 係數以最後一點外插 |
| 槳尖馬赫數 | > 0.7 | 未計入壓縮性 |
| 混控飽和 | 任一馬達到 0% 或 100% | 飛行限制，不是模型問題 |
| 接觸地面 | — | 接地模型簡化 |

## 調參流程（`fpvsim tune`）

1. **雜訊調查**：飛油門掃描，以 PID 迴圈頻率記錄。看未濾波陀螺儀頻譜對油門的變化，比較三種濾波設定（基準、關閉 RPM 濾波、RPM 濾波搭配較輕的低通）的濾波後陀螺儀、D 項與馬達輸出雜訊，以及濾波延遲。
2. **增益掃描**：P 與 D 一起乘上「PD 倍數」，D 再另外乘上「D 倍數」，共 15 組。每組飛同一段調參飛行：每一軸固定時間的小幅度正反向步階（不讓混控飽和）。步階時刻已知，所以在每一次步階直接量測，取中位數；雜訊只在最後一段平飛油門爬升中量測，因為步階本身的訊號也落在同一個頻帶。

   步階響應的量法曾經出錯：早期版本用反卷積處理整段飛行，會把測試飛手的小修正也當成步階，結果隨亂數種子在 13% 到 27% 之間跳動；全幅度打桿則讓混控飽和，量到的是非線性響應。現在的做法以無雜訊、小幅度的直接步階測試為真值驗證過。
3. **建議**：在超調與雜訊條件內，選追蹤誤差最小的一組。如果建議值落在掃描範圍邊緣，報告會提醒擴大掃描。

調參報告中雜訊的**絕對數值**取決於估計的振動參數，尚未確認；不同設定之間的**相對比較**才有意義。用實機的未濾波陀螺儀 log 辨識振動參數後，絕對數值才能採信。
