# Physical-Fpv-Simulator

Physics-first FPV simulator built from real physical properties.

這是一個**虛擬研發實驗室**：真實 FPV 研發的每個階段，在這裡都有對應的虛擬儀器，產出和真實研發相同格式的數據、圖表與報告。畫面可以很簡陋，但數據來源、物理模型和分析方法都要能經得起檢驗。

## 原則

- **每個數字都有出處。** 參數必須標明來源（實測、規格書、文獻、估計……）與不確定度，缺一項就無法載入。
- **換零件就是換物理。** 不用「操控 +10%」這類遊戲數值；換馬達、槳或電池，改的是 Kv、內阻、推力係數與質量，結果由方程算出。
- **驗證與確認分開。** 程式有沒有正確解出方程（verification）靠解析解測試；方程符不符合現實（validation）只能靠實測數據。
- **結果附上不確定度。** 報告寫「懸停續航 18 min，90% 區間 13–25 min」，而不是一個看起來很精確的單一數字。
- **可重現。** 報告記錄程式 commit、輸入檔雜湊與隨機種子。

## 研發流程與目前進度

| 階段 | 真實研發在做什麼 | 模擬器裡的對應 | 狀態 |
|---|---|---|---|
| 1. 需求規格 | 定義用途、重量、推重比、續航目標 | 規格檔 `data/specs/` | ✅ |
| 2. 動力匹配 | 推力台測試馬達、槳、電壓組合 | 虛擬推力台、BEMT、系統識別 | ✅ |
| 3. 重量與重心 | 秤重、做重量表、算重心與慣性 | 質量預算 | ✅ |
| 4. 電氣 | 壓降、峰值電流、額定值 | 電池等效電路、額定值檢查 | ✅（溫升待做） |
| 5. 調參 | 看陀螺儀頻譜設濾波、看步階響應調 PID | 雜訊調查、濾波延遲、步階響應量測、增益掃描 | ✅ |
| 6. 飛行測試 | 實飛並錄 log | 6DOF 飛行模擬、Betaflight 式飛控、虛擬 Blackbox、適用範圍監測 | ✅（即時手動飛行待做） |
| 7. 迭代 | 依測試結果修改設計 | 版本檔（只寫變更）、成對蒙地卡羅、各版本相同流程的比較報告 | ✅ |

範例輸出：

- [參考機設計報告](reports/ref-5in-6s-freestyle/report.md)（第 1–4 階段）
- [調參報告](reports/tune-acro-5in-baseline/report.md)（第 5 階段）
- [飛行測試報告：綜合飛行](reports/flight-freestyle/report.md)（第 6 階段）
- [設計迭代：加掛運動相機的三個版本](reports/compare-actioncam/report.md)（第 7 階段）

## 快速開始

需要 Python 3.11 以上。

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                   # 驗證測試

.venv/bin/fpvsim summary data/builds/ref-5in-6s-freestyle.toml
.venv/bin/fpvsim check   data/builds/ref-5in-6s-freestyle.toml   # 檢查參數出處
.venv/bin/fpvsim stand   data/builds/ref-5in-6s-freestyle.toml --voltage 22.2V
.venv/bin/fpvsim report  data/builds/ref-5in-6s-freestyle.toml --out reports/ref-5in-6s-freestyle
```

有實測推力台數據時（CSV 欄位需含單位，例如 `rpm [rpm]`、`thrust [gf]`、`torque [N*m]`）：

```bash
.venv/bin/fpvsim fit-prop my_stand.csv --diameter 5.1in --temperature 22degC --altitude 30m
```

它會輸出辨識出的 Ct、Cp 與不確定度，可以直接貼進槳的零件檔取代 BEMT 估計值。

飛行模擬與調參（說明見 [docs/flight-sim.md](docs/flight-sim.md)）：

```bash
.venv/bin/fpvsim maneuvers
.venv/bin/fpvsim fly  data/builds/ref-5in-6s-freestyle.toml --fc data/fc/acro-5in-baseline.toml --maneuver freestyle
.venv/bin/fpvsim tune data/builds/ref-5in-6s-freestyle.toml --fc data/fc/acro-5in-baseline.toml
```

設計迭代（說明見 [docs/iteration.md](docs/iteration.md)）：

```bash
.venv/bin/fpvsim compare data/builds/ref-5in-6s-freestyle.toml \
    data/builds/ref-5in-6s-freestyle-actioncam-a.toml data/builds/ref-5in-6s-freestyle-actioncam-b.toml \
    data/builds/ref-5in-6s-freestyle-actioncam-c.toml \
    --fc data/fc/acro-5in-baseline.toml
```

## 專案結構

```
src/fpvsim/
  units.py, params.py     單位換算；帶出處與不確定度的參數
  atmosphere.py           ISA 大氣
  mass.py                 質量、重心、慣性張量
  battery.py              LiPo 一階等效電路
  motor.py                BLDC 馬達與 ESC 平均模型
  prop.py, bemt.py        槳係數；葉素動量理論
  powertrain.py           電池→ESC→馬達→槳 的穩態工作點
  design.py               讀取規格、組裝檔、零件檔
  performance.py          懸停、全油門、續航、設計指標
  stand.py                虛擬推力台
  sysid.py                系統識別（由測試數據辨識參數）
  uncertainty.py          蒙地卡羅與敏感度分析
  report.py, plots.py     設計報告
  dynamics.py             6DOF 飛行動力學
  sensors.py, filters.py  陀螺儀模型；數位濾波器
  flightcontroller.py     Betaflight 式 Acro 飛控
  pilot.py, sim.py        自動測試飛手與飛行腳本；多速率模擬迴圈
  blackbox.py             飛行 log
  flightanalysis.py       頻譜、步階響應、延遲
  tuning.py               調參流程
  flight_report.py, tuning_report.py
  compare.py, compare_report.py   設計迭代：版本比較
data/
  specs/                  需求規格
  builds/                 組裝檔（零件與擺放位置）
  components/             零件庫
  fc/                     飛控設定
docs/
  methodology.md          研發方法：V&V、參數出處、不確定度、數據政策
  models.md               每個物理模型的方程、假設與適用範圍
  data-format.md          資料檔格式
  flight-sim.md           飛行模擬、飛控與調參
  iteration.md            設計迭代與版本比較
tests/                    驗證測試
reports/                  產生的報告範例
```

## 數據與版權

零件庫只收錄**通用級距零件**，不使用品牌名稱，數值是標示為「工程估計」的級距典型值，不複製任何廠商或第三方的測試資料表。物理模型依教科書與論文中的方程自行實作；飛控依公開資料描述的 Betaflight 行為獨立撰寫，沒有使用其原始碼。詳見 [docs/methodology.md](docs/methodology.md#7-數據與智慧財產政策)。

本專案採 [MIT 授權](LICENSE)。
