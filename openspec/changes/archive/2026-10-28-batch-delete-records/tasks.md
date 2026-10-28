# Tasks

## 1. 後端批次刪除 API

- [x] 1.1 `backend/app/schemas/record.py` 新增 `RecordBatchDelete`（`ids: list[PositiveInt]`，1–100 筆、不可重複）與 `BatchDeleteResult`（`deleted: int`）；在 `backend/tests/test_record_schemas.py` 加上空清單、超過 100 筆、重複 id、非正整數皆被拒絕的測試並通過
- [x] 1.2 `backend/app/services/record_service.py`：把 `ensure_can_modify` 的規則抽成可回傳 True／False 的 `can_modify`（單筆刪除與修改行為不變），新增 `delete_records`：以 ORM 一次取出記錄、先檢查不存在的 id（404，detail 含 `message` 與 `ids`）、再檢查權限（403，detail 含 `message` 與 `ids`），通過後在同一交易以 `delete(Record).where(Record.id.in_(ids))` 刪除並回傳 `rowcount`；不使用 raw SQL；`pixi run lint` 通過
- [x] 1.3 `backend/app/routers/records.py` 新增 `POST /records/batch-delete`（`Writer` 依賴、回 200 `BatchDeleteResult`、OpenAPI `responses` 註明 403／404 的 detail 格式），成功後寫一筆 `record_batch_delete` 系統日誌（刪除者、筆數、id 清單）
- [x] 1.4 `backend/tests/test_records.py` 依 `specs/data-records/spec.md` 的情境新增測試：刪除自己的多筆、包含他人的記錄（403、全部未刪、列出 id）、包含不存在的 id（404、全部未刪、列出 id）、Admin 刪除任何人的記錄、Viewer 403、系統日誌內容；`docker compose --profile test run --rm --build backend-test` 全部通過

## 2. 前端批次刪除

- [x] 2.1 `frontend/lib/api.py` 的 `error_text` 支援 `{"message", "ids"}` 格式的 detail（顯示訊息與相關 id）；`pixi run lint` 通過
- [x] 2.2 `frontend/views/records.py`：Admin 與 User 的表格改為多選（`on_select="rerun"`、`selection_mode="multi-row"`，`key` 含目前顯示的 id 清單），表格下方加入批次刪除區塊（略過他人記錄的提示、確認勾選框、刪除按鈕、成功訊息「已刪除 N 筆記錄」）；Viewer 的表格維持不能勾選；`pixi run lint` 通過
- [x] 2.3 更新 README 功能表的「資料記錄」列，加上批次刪除

## 3. 整合驗證

- [x] 3.1 `docker compose up -d --build` 後在瀏覽器依 `specs/web-dashboard/spec.md` 的情境逐一驗證：User 勾選 3 筆自己的記錄刪除、選取中包含他人記錄時提示並只刪自己的、未確認時按鈕無法按下、Viewer 的表格不能勾選且沒有批次刪除元件，並在系統管理的系統日誌看到 `record_batch_delete`
- [x] 3.2 `pixi run lint` 與 `docker compose --profile test run --rm --build backend-test` 皆通過

## Workflow follow-up

- 實作完成並驗證後，以 `/opsx:archive` 封存此 change，將 `data-records` 與 `web-dashboard` 的 delta 同步到 `openspec/specs/`。
