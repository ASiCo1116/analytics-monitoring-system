# data-records Specification

## Purpose
讓使用者手動建立、查詢、修改、刪除與批量匯入資料記錄（標題、數值、分類、時間戳、說明），並保證只有建立者或 Admin 能改動自己的資料。

## Requirements

### Requirement: 建立資料記錄
Admin 與 User SHALL 能建立資料記錄，欄位為：標題（1–200 字元，必填）、數值（浮點數，必填）、分類（1–50 字元，必填）、資料時間戳 recorded_at（選填，未填則為當下 UTC 時間）、說明（選填，最多 1000 字元）。系統 MUST 自動記錄建立者與建立時間。未帶時區的時間（含匯入檔中的 recorded_at）視為系統設定的顯示時區（預設 Asia/Taipei）。

#### Scenario: 建立成功
- **WHEN** User 送出合法的標題、數值與分類
- **THEN** 系統回傳 201 與完整記錄，owner 為該 User，recorded_at 為當下時間

#### Scenario: 欄位驗證失敗
- **WHEN** User 送出空白標題或非數字的數值
- **THEN** 系統回傳 422 並列出錯誤欄位

### Requirement: 查詢資料記錄列表
所有已登入角色 SHALL 能查詢全部資料記錄，並支援：分頁（page 從 1 開始，page_size 預設 20、上限 100）；篩選（分類、數值下限／上限、recorded_at 起訖時間、標題關鍵字）；排序（可依 recorded_at、value、title、category、created_at，升冪或降冪，預設 recorded_at 降冪）。回應 MUST 包含 items、total、page、page_size，每筆含建立者 username。

#### Scenario: 分頁
- **WHEN** 資料共 45 筆，使用者以 page=3、page_size=20 查詢
- **THEN** 回傳 5 筆，total=45

#### Scenario: 篩選與排序組合
- **WHEN** 使用者以 category=cpu、min_value=50、sort=-value 查詢
- **THEN** 只回傳分類為 cpu 且數值 ≥ 50 的記錄，依數值由大到小排列

#### Scenario: 不允許的排序欄位
- **WHEN** 使用者以 sort=password 查詢
- **THEN** 系統回傳 422

### Requirement: 查詢單筆與分類清單
所有已登入角色 SHALL 能依 id 取得單筆資料記錄，並能取得目前所有不重複的分類名稱（供前端篩選下拉選單使用）。

#### Scenario: 記錄不存在
- **WHEN** 使用者查詢不存在的 id
- **THEN** 系統回傳 404

#### Scenario: 取得分類清單
- **WHEN** 使用者呼叫分類清單 API
- **THEN** 系統回傳依字母排序的不重複分類名稱陣列

### Requirement: 修改資料記錄
系統 SHALL 允許建立者本人或 Admin 部分更新資料記錄的標題、數值、分類、recorded_at 與說明；其他人 MUST 收到 403。建立者欄位不可被修改。

#### Scenario: 建立者修改自己的記錄
- **WHEN** User A 修改自己建立的記錄的數值
- **THEN** 系統回傳 200 與更新後的記錄，updated_at 更新

#### Scenario: 修改他人的記錄
- **WHEN** User B 修改 User A 建立的記錄
- **THEN** 系統回傳 403，記錄不變

#### Scenario: Admin 修改任何記錄
- **WHEN** Admin 修改 User A 建立的記錄
- **THEN** 系統回傳 200

### Requirement: 刪除資料記錄
系統 SHALL 允許建立者本人或 Admin 刪除資料記錄，成功時回傳 204；其他人 MUST 收到 403。

#### Scenario: 建立者刪除
- **WHEN** User A 刪除自己建立的記錄
- **THEN** 系統回傳 204，之後查詢該 id 回傳 404

#### Scenario: Viewer 刪除
- **WHEN** Viewer 刪除任一記錄
- **THEN** 系統回傳 403

### Requirement: 批量匯入 CSV/JSON
Admin 與 User SHALL 能上傳 CSV 或 JSON 檔案批量建立資料記錄，建立者為上傳者。CSV 需有標頭 `title,value,category,recorded_at,description`（後兩欄可留空）；JSON 為相同欄位的物件陣列。檔案上限 5 MB、10,000 筆。匯入 MUST 為全有或全無：任一筆驗證失敗則整批不寫入，並回傳每筆錯誤的列號與原因。

#### Scenario: CSV 匯入成功
- **WHEN** User 上傳 50 筆皆合法的 CSV
- **THEN** 系統回傳 201 與 `{imported: 50}`，50 筆記錄的建立者皆為該 User

#### Scenario: 部分資料不合法
- **WHEN** User 上傳的 CSV 第 3 列與第 7 列數值不是數字
- **THEN** 系統回傳 422，列出第 3、7 列的錯誤，資料庫中沒有新增任何記錄

#### Scenario: 不支援的檔案格式
- **WHEN** User 上傳 .xlsx 檔
- **THEN** 系統回傳 415

#### Scenario: 超過筆數上限
- **WHEN** User 上傳 10,001 筆資料
- **THEN** 系統回傳 413，不寫入任何資料
