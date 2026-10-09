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

`mass`、`shape`、`cg_offset`、`drag_center` 是頂層鍵，**必須寫在第一個 `[表格]` 之前**，否則 TOML 會把它們歸到前一個表格；載入器會偵測這個錯誤。

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
| `prop` | `diameter`、`pitch`、`spin_inertia`；有 `[bemt]` 槳葉幾何時 `flap_fraction`，沒有時 `rotor_drag_factor`（只能二擇一） | `[config] blades`；`[coefficients]`（實測）或 `[bemt]`（幾何估計），兩者都有時軸向用實測、斜向氣流用幾何 |
| `esc` | `r_on`、`quiescent_power`、`max_current`、`drive_current_limit`、`brake_current_limit` | |
| `battery` | `capacity`、`r0_cell`、`r1_cell`、`tau1`、`c_rating`、`r_ref_temperature`、`resistance_activation_energy`、`specific_heat`、`ha_hover`、`ha_ref`、`ha_speed`、`max_temperature`、`capacity_fade`、`resistance_growth` | `[config] series, parallel`；`[ocv] soc, cell_voltage, source` |
| `frame` | `thrust_interference`、`cda_x/y/z`（作用在頂層鍵 `drag_center`）、`contact_stiffness`、`contact_damping`、`ground_friction`、`vib_amp_1/2/3`、`vib_ref_speed`、`vib_exponent`、`vib_yaw_ratio` | `[[rotors]]` 安裝點與轉向；`[[contacts]]` 地面接觸點（至少 3 個）；`[[parts]]` 機架零件與 `placements` |
| `avionics` | 無 | `power`（W，穩壓端功率）會計入航電負載；飛控板需有 `gyro_noise_density` |

組裝檔的 `[flight_controller]` 需要 `board`（飛控板的零件名稱）與 `motor_idle`。

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

零件可以帶阻力面積 `cda_x`、`cda_y`、`cda_z`（零件檔的 `[params]`，或行內零件的鍵），作用在零件自己的位置；機架本身的阻力作用在機架檔的 `drag_center`。

零件的安裝位置可以標示標準不確定度 `position_u = { value = [ux, uy, uz], unit = "mm", source = ..., note = ... }`。疊裝在另一個零件上的零件寫 `mounted_on = "<零件名稱>"`：它會跟著母零件的位置誤差一起移動，自己的 `position_u` 則是相對母零件的誤差。

### 版本檔

`[meta] extends = "<基準組裝檔>"` 讓組裝檔只寫變更：同名 `[[parts]]` 取代、新名稱新增、`remove_parts = [...]` 移除；`[components]`、`[electrical]`、`[flight_controller]` 以鍵覆蓋；`change` 寫一句變更說明。詳見 [iteration.md](iteration.md)。

## 規格檔（`schema = "fpvsim.spec/1"`）

```toml
[environment]   # altitude、temperature；選填 battery_temperature（起飛時的電池溫度，預設等於氣溫）、battery_cycles（預設 0）
[endurance]     # reserve_soc、min_cell_voltage、burst_cell_voltage（全油門時允許的瞬間單芯電壓）

[[requirements]]
id = "R1"
metric = "auw"      # 可用的指標見 src/fpvsim/performance.py 的 METRICS
max = 600           # min 或 max 擇一
unit = "g"
rationale = "..."

[[design_points]]   # 選填：設計也要在這些工況下符合需求，設計報告會逐一評估
id = "winter"
name = "冬季"
temperature = { value = 0, unit = "degC", source = "nominal" }          # 可用 altitude、temperature、
battery_temperature = { value = 5, unit = "degC", source = "nominal" }  # battery_temperature、battery_cycles
rationale = "..."
```

設計點只寫了 `temperature` 而沒寫 `battery_temperature` 時，視為電池已經放到和氣溫相同。

## 測試數據 CSV

標頭格式為 `名稱 [單位]`，例如：

```
rpm [rpm],thrust [gf],torque [N*m]
8000,128.4,0.0151
```

虛擬推力台輸出的 CSV 也使用這個格式，所以真實與虛擬數據走同一套分析。
