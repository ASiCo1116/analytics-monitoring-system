# Design

## Context

- 單筆刪除是 `DELETE /api/v1/records/{id}`：路由用 `Writer` 依賴擋掉 Viewer，`record_service.ensure_can_modify` 檢查建立者或 Admin，成功後寫一筆 `record_delete` 系統日誌。
- 匯入已經是全有或全無，錯誤時用結構化的 `detail` 回傳逐列錯誤。
- 前端資料記錄頁以 `st.dataframe` 顯示目前這一頁（最多 100 筆），單筆刪除在「編輯／刪除」分頁。
- 專案規定不寫 raw SQL，一律用 SQLAlchemy ORM。

## Goals / Non-Goals

**Goals:**

- 一次請求刪除多筆，結果只有「全部刪除」或「全部沒刪」兩種。
- 權限檢查與單筆刪除一致，重用同一套規則。
- 前端直接在表格上勾選，不另開頁面。

**Non-Goals:**

- 依篩選條件刪除（例如「刪除分類為 cpu 的全部記錄」）。這種操作一次可能刪掉大量資料，需要另外設計確認流程。
- 跨頁選取。勾選只針對目前這一頁，換頁或改篩選後選取會清空。
- 復原或垃圾桶。刪除仍是永久刪除，與單筆刪除相同。

## Decisions

### 1. API：`POST /api/v1/records/batch-delete`

請求 `{"ids": [1, 2, 3]}`，成功回 200 `{"deleted": 3}`。

| 狀況 | 回應 |
|---|---|
| 成功 | 200 `{"deleted": n}` |
| Viewer | 403（由 `Writer` 依賴擋下，與單筆刪除相同） |
| 有 id 不存在 | 404 `{"detail": {"message": "Records not found", "ids": [...]}}` |
| 有記錄不是自己建立的（非 Admin） | 403 `{"detail": {"message": "Not enough permissions", "ids": [...]}}` |
| id 清單為空、超過 100 個、有重複或不是正整數 | 422 |

- 不存在的檢查排在權限之前。這樣 User 只會在所有 id 都存在時，才知道哪些記錄不是自己的。
- 上限 100 與列表的 `page_size` 上限相同，前端一頁最多也只有 100 筆可以勾選。

考慮過的其他做法：

- **`DELETE /records` 帶 body**：HTTP 沒有定義 DELETE body 的語意，部分代理伺服器與用戶端會丟掉它，Swagger UI 也不方便測試。
- **`DELETE /records?ids=1,2,3`**：可行，但 100 個 id 會讓網址很長，驗證錯誤也不如 JSON body 清楚。

### 2. 全有或全無的實作

在同一個交易中：

1. `select(Record).where(Record.id.in_(ids))` 一次取出所有記錄。
2. 比對出不存在的 id，有就回 404。
3. 非 Admin 時，找出 `owner_id` 不是自己的記錄，有就回 403。權限判斷沿用 `ensure_can_modify` 的規則，抽成可對單筆回傳 True／False 的函式，單筆與批次共用。
4. `delete(Record).where(Record.id.in_(ids))` 一次刪除，然後 commit。回傳的筆數取自刪除結果的 `rowcount`。

整個流程都是 ORM 語句，沒有 raw SQL。記錄的建立者不能修改，所以第 3 步之後不會有人改變權限。若同時有其他人先刪掉其中幾筆，`rowcount` 會比請求的少，這種情況直接回報實際刪除的筆數。

### 3. Schema

- `RecordBatchDelete`：`ids: list[PositiveInt]`，長度 1–100，並以 validator 拒絕重複的 id。
- `BatchDeleteResult`：`deleted: int`。

### 4. 系統日誌

成功時寫一筆 `record_batch_delete`，內容例如 `admin deleted 3 records: 12, 40, 77`。`system_logs.message` 上限 500 字元，`audit_service.log` 會截斷過長的內容，所以 100 個 id 時尾端的 id 可能不完整。筆數在最前面，一定會保留。

考慮過的其他做法：每筆寫一筆 `record_delete`。最多會一次寫入 100 筆日誌，讓系統日誌頁很難閱讀，所以不採用。

### 5. 前端

- 對 Admin 與 User，表格改為 `st.dataframe(..., on_select="rerun", selection_mode="multi-row")`。Viewer 的表格維持原樣，不能勾選。
- 表格的 `key` 包含目前顯示的 id 清單。換頁、改篩選或刪除後資料改變時，key 也會跟著改，選取就會清空，避免舊的列索引指到新的資料。
- 表格下方：
  - 有勾選時，才顯示批次刪除區塊。
  - 把選取分成「可刪除」（自己的，或 Admin 時全部）與「略過」兩組。有略過的記錄時，用提示說明筆數。
  - 「確認刪除選取的 N 筆」勾選框，加上刪除按鈕。沒有確認時，按鈕不能按。
  - 只送出可刪除的 id。成功後顯示「已刪除 N 筆記錄」並重新載入。
- `api.error_text` 加上對 `{"message", "ids"}` 格式 detail 的處理，顯示訊息與相關 id。例如記錄已被別人先刪掉而回 404 時，能看出是哪幾筆。

## Risks / Trade-offs

- **[誤刪大量資料]：** 一次最多刪 100 筆。→ 需要勾選確認才能按下按鈕，而且只能刪目前這一頁。日誌也會記下刪除了哪些 id，但刪除本身無法復原。
- **[日誌截斷]：** 100 筆時，日誌裡的 id 清單可能不完整。→ 筆數一定會保留；需要完整清單時，可以再拆成較小的批次。
- **[前端沒有自動化測試]：** 表格勾選與確認流程只能在瀏覽器中驗證。→ 後端的規則都有 pytest 測試；前端依規格情境在瀏覽器實際操作驗證。
