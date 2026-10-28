# Proposal

## Why

目前資料記錄只能在「編輯／刪除」分頁逐筆選取、確認、刪除，清掉一批測試匯入或錯誤的資料要重複操作很多次。匯入已經可以一次建立上萬筆，刪除卻只能一筆一筆來，兩者落差太大。

## What Changes

- 新增批次刪除 API：一次送出多個記錄 id（最多 100 筆，與每頁筆數上限相同），全部刪除或全部不刪除，與匯入的全有或全無一致。
- 權限沿用單筆刪除的規則：Admin 可刪任何記錄，User 只能刪自己建立的記錄，Viewer 不能刪除。只要其中有一筆不存在或沒有權限，整批都不刪除，並回傳是哪些 id。
- 批次刪除寫入一筆系統日誌，記下刪除筆數與 id。
- 資料記錄頁的表格可勾選多列，下方顯示「刪除選取的 N 筆」並需勾選確認；選取中不是自己建立的記錄會被略過並提示。Viewer 的表格不能勾選，也看不到刪除按鈕。
- 單筆刪除 API 與「編輯／刪除」分頁維持不變。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `data-records`：新增「批次刪除資料記錄」需求。
- `web-dashboard`：「資料記錄頁」加入表格多選與批次刪除。

## Impact

- **後端**：`backend/app/routers/records.py` 新增端點、`backend/app/services/record_service.py` 新增批次刪除、`backend/app/schemas/record.py` 新增請求與回應 schema；新增對應測試。資料庫結構不變。
- **前端**：`frontend/views/records.py` 的表格改為可多選，並新增批次刪除區塊。
- **文件**：README 功能表、`openspec/specs/data-records`、`openspec/specs/web-dashboard`。
