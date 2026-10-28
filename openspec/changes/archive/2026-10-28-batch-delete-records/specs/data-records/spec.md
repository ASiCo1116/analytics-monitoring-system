# Spec Delta

## ADDED Requirements

### Requirement: 批次刪除資料記錄
Admin 與 User SHALL 能一次刪除多筆資料記錄，請求帶 1–100 個不重複的記錄 id。權限與單筆刪除相同：Admin 可刪任何記錄，User 只能刪自己建立的記錄，Viewer MUST 收到 403。批次刪除 MUST 為全有或全無：任一 id 不存在則回傳 404，任一筆沒有權限則回傳 403，兩者都列出相關 id，且不刪除任何記錄。成功時回傳刪除筆數，並寫入一筆系統日誌記下筆數與 id。

#### Scenario: 刪除自己的多筆記錄
- **WHEN** User A 批次刪除自己建立的 3 筆記錄
- **THEN** 系統回傳 200 與 `{deleted: 3}`，之後查詢這 3 個 id 都回傳 404

#### Scenario: 包含他人的記錄
- **WHEN** User A 批次刪除 2 筆自己的記錄與 1 筆 User B 的記錄
- **THEN** 系統回傳 403 並列出 User B 那筆的 id，3 筆記錄都沒有被刪除

#### Scenario: 包含不存在的 id
- **WHEN** User A 批次刪除的 id 中有一個不存在
- **THEN** 系統回傳 404 並列出不存在的 id，其他記錄都沒有被刪除

#### Scenario: Admin 刪除任何人的記錄
- **WHEN** Admin 批次刪除 User A 與 User B 建立的記錄
- **THEN** 系統回傳 200，所有指定的記錄都被刪除

#### Scenario: Viewer 批次刪除
- **WHEN** Viewer 批次刪除任何記錄
- **THEN** 系統回傳 403，沒有記錄被刪除

#### Scenario: id 數量或格式不合法
- **WHEN** 請求的 id 清單為空、超過 100 個，或有重複的 id
- **THEN** 系統回傳 422，沒有記錄被刪除

#### Scenario: 系統日誌
- **WHEN** Admin 成功批次刪除 3 筆記錄
- **THEN** 系統日誌新增一筆紀錄，內容包含刪除者、筆數與這 3 個 id
