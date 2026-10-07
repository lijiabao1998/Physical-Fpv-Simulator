# 資料檔格式

所有資料檔都是 TOML。路徑一律相對於檔案本身所在的目錄。

## 參數

物理參數一律寫成表格，不能只寫數字：

```toml
kv = { value = 1750, unit = "rpm/V", source = "nominal", u_rel = 0.025, note = "生產公差估計" }
rm = { value = 82, unit = "mohm", source = "measured", u = 1.5, ref = "2026-10-12 四線法量測紀錄" }
```

| 欄位 | 必填 | 說明 |
|---|---|---|
| `value` | 是 | 數值 |
| `unit` | 是 | 單位，必須是 `src/fpvsim/units.py` 列出的單位之一 |
| `source` | 是 | `measured`、`standard`、`nominal`、`datasheet`、`literature`、`derived`、`estimate`、`synthetic` |
| `u` / `u_rel` | 估計值必填 | 標準不確定度（1σ），`u` 與數值同單位，`u_rel` 為相對值，二擇一 |
| `dist` | 否 | `normal`（預設）或 `uniform` |
| `ref` | 規格書、文獻、實測必填 | 引用或量測紀錄 |
| `note` | 否 | 說明 |

向量（位置）寫成 `{ value = [x, y, z], unit = "mm" }`，座標為 FRD。

## 零件檔（`schema = "fpvsim.component/1"`）

`mass`、`shape`、`cg_offset` 是頂層鍵，**必須寫在第一個 `[表格]` 之前**，否則 TOML 會把它們歸到前一個表格；載入器會偵測這個錯誤。

```toml
schema = "fpvsim.component/1"

mass = { value = 32, unit = "g", source = "estimate", u = 1.5 }
shape = { type = "cylinder", radius = 14.25, height = 18, unit = "mm" }   # point / box / cylinder
cg_offset = { value = [0, 0, -9], unit = "mm" }                          # 相對安裝點，只用於馬達與槳

[meta]
id = "generic-2306-1750kv"
category = "motor"       # frame / motor / prop / esc / battery / avionics
name = "..."

[params]
# 依類別而定的參數，見下表
```

| 類別 | 必要參數 | 其他 |
|---|---|---|
| `motor` | `kv`、`rm`、`i0_ref`、`v_i0_ref`、`i0_speed_fraction`、`rotor_inertia`、`max_current` | |
| `prop` | `diameter`、`pitch`、`spin_inertia` | `[config] blades`；`[coefficients]`（實測）或 `[bemt]`（幾何估計） |
| `esc` | `r_on`、`quiescent_power`、`max_current` | |
| `battery` | `capacity`、`r0_cell`、`r1_cell`、`tau1`、`c_rating` | `[config] series, parallel`；`[ocv] soc, cell_voltage, source` |
| `frame` | `thrust_interference` | `[[rotors]]` 安裝點與轉向；`[[parts]]` 機架零件與 `placements` |
| `avionics` | 無 | `power`（W，穩壓端功率）會計入航電負載 |

槳的實測係數表：

```toml
[coefficients]
source = "measured"
ref = "stand_2026-10-12.csv"
J = [0.0]
ct = [0.1983]
cp = [0.1047]
ct_u_rel = 0.012
cp_u_rel = 0.015
```

`fpvsim fit-prop` 會直接輸出這段內容。

## 組裝檔（`schema = "fpvsim.build/1"`）

```toml
[meta]
spec = "../specs/freestyle-5in-6s.toml"

[components]          # 動力系統：frame、motor、prop、esc、battery 都必填
motor = "../components/motors/generic-2306-1750kv.toml"

[electrical]          # harness_resistance、bec_efficiency
[flight_controller]   # motor_idle

[[parts]]             # 三種寫法
name = "battery"
uses = "battery"                                            # 1. 放置 [components] 中的電池或 ESC
position = { value = [0, 0, -46], unit = "mm" }

[[parts]]
name = "fc"
component = "../components/electronics/generic-fc-30x30.toml"  # 2. 引用零件檔
position = { value = [0, 0, -13], unit = "mm" }

[[parts]]
name = "capacitor"                                          # 3. 直接寫質量
mass = { value = 4, unit = "g", source = "estimate", u = 1 }
position = { value = [-45, 15, 0], unit = "mm" }
```

馬達與槳會自動放在機架的 `[[rotors]]` 安裝點上，加上各自的 `cg_offset`。

## 規格檔（`schema = "fpvsim.spec/1"`）

```toml
[environment]   # altitude、temperature
[endurance]     # reserve_soc、min_cell_voltage

[[requirements]]
id = "R1"
metric = "auw"      # 可用的指標見 src/fpvsim/performance.py 的 METRICS
max = 600           # min 或 max 擇一
unit = "g"
rationale = "..."
```

## 測試數據 CSV

標頭格式為 `名稱 [單位]`，例如：

```
rpm [rpm],thrust [gf],torque [N*m]
8000,128.4,0.0151
```

虛擬推力台輸出的 CSV 也使用這個格式，所以真實與虛擬數據走同一套分析。
