# 設計迭代（第 7 階段）

真實研發改一個設計時，會先寫清楚改了什麼（工程變更），再用和原設計完全相同的方法重新評估，最後把差異和它的不確定度一起交給做決定的人。`fpvsim compare` 照這個流程進行。

## 版本檔：只寫變更

```toml
schema = "fpvsim.build/1"

[meta]
extends = "ref-5in-6s-freestyle.toml"      # 基準設計（相對路徑以本檔為準）
id = "ref-5in-6s-freestyle-actioncam-b"
name = "版本 B：相機裝在上板前端、電池後移"
change = "加掛全尺寸運動相機（上板前端），電池後移 20 mm"
remove_parts = []                          # 要移除的零件名稱

[[parts]]                                  # 同名：取代基準的零件（這裡是把電池往後移）
name = "battery"
uses = "battery"
position = { value = [-20, 0, -46], unit = "mm" }

[[parts]]                                  # 新名稱：新增零件
name = "action_camera"
component = "../components/payloads/generic-action-camera-full.toml"
position = { value = [40, 0, -60.5], unit = "mm" }
```

合併規則：

- `[[parts]]` 依名稱合併：同名的零件取代基準的零件，新名稱則新增。
- `remove_parts` 移除零件。
- `[components]`、`[electrical]`、`[flight_controller]` 以鍵覆蓋。
- 版本可以再被別的版本 `extends`；循環引用會報錯。
- 報告列出每個版本的完整演進（lineage），輸入檔雜湊涵蓋整條鏈上的所有檔案。

## 零件阻力疊加

零件可以帶自己的阻力面積 `cda_x`、`cda_y`、`cda_z`，寫在零件檔的 `[params]` 或直接寫在 `[[parts]]` 裡。機體的阻力面積 = 機架的值 + 各零件的值（drag buildup）。這是一階估計：零件之間的干擾不計，零件的安裝角度也不計。

## 成對比較

用兩次獨立的蒙地卡羅比較兩個版本時，差異會被兩邊各自的抽樣雜訊淹沒。fpvsim 的抽樣以參數為單位：每個參數的亂數流由（種子，參數名稱）決定。因此在第 i 組樣本中，各版本共有的參數（馬達、槳、電池……）取相同的值，只有新增或改變的參數不同。這就是「共同亂數」（common random numbers）方法，版本差異是逐組直接算出來的。

`tests/test_variants.py` 用一個嚴格的檢查驗證這件事：成對樣本中，版本 A 與基準的全備重量差，**每一組都恰好等於**該組抽到的相機質量加相機座質量。

## 比較內容

```bash
fpvsim compare data/builds/ref-5in-6s-freestyle.toml \
               data/builds/ref-5in-6s-freestyle-actioncam-a.toml \
               data/builds/ref-5in-6s-freestyle-actioncam-b.toml \
               --fc data/fc/acro-5in-baseline.toml
```

第一個檔是基準，其餘是要比較的版本。每個版本都會：

1. 列出相對基準的設計變更：新增、移除、移動的零件，更換的零件檔，改了數值的參數。
2. 做靜態分析與規格符合度，使用成對蒙地卡羅。
3. 以相同飛控設定（基準增益）、相同腳本與種子試飛。
4. 執行調參研究：先看基準增益在新機體上的表現，再找出它自己的建議增益。

選項 `--no-fly`、`--no-tune` 可以跳過較慢的部分。完整比較三個版本約需 10 分鐘。

## 這次的範例：加掛運動相機

| 版本 | 變更 |
|---|---|
| base | 參考機（不掛相機） |
| A | 全尺寸運動相機綁在電池前端，電池不動（最快的改法） |
| B | 相機裝在上板前端，電池後移 20 mm 讓重心回到推力中心 |

結果見 [reports/compare-actioncam/report.md](../reports/compare-actioncam/report.md)。
