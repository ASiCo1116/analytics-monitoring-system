# Spec Delta

## Purpose

提供 Admin 專用的管理功能：管理使用者角色與啟用狀態、查詢系統日誌、監控資料庫狀態，以及查詢即時監控資料的歷史紀錄。

## ADDED Requirements

### Requirement: 使用者列表
Admin SHALL 能分頁查詢所有使用者（id、username、email、role、is_active、created_at），可依角色、啟用狀態與 username 關鍵字篩選。

#### Scenario: Admin 查詢使用者
- **WHEN** Admin 呼叫使用者列表 API
- **THEN** 系統回傳分頁結果，不含任何密碼欄位

### Requirement: 修改使用者角色與啟用狀態
Admin SHALL 能修改任一使用者的角色（admin/user/viewer）與啟用狀態。Admin MUST NOT 能修改自己的角色或停用自己，以避免系統失去管理者。每次修改 MUST 寫入系統日誌，記錄修改前後的值。

#### Scenario: 調整角色
- **WHEN** Admin 將某 User 改為 Viewer
- **THEN** 系統回傳 200，該使用者之後的請求以 Viewer 權限判斷，系統日誌新增一筆 role_change

#### Scenario: Admin 停用自己
- **WHEN** Admin 嘗試停用自己或把自己改成 User
- **THEN** 系統回傳 400，資料不變

#### Scenario: 指定的使用者 id 無效
- **WHEN** Admin 以不存在的 UUID 修改使用者
- **THEN** 系統回傳 404
- **WHEN** Admin 以非 UUID 格式的字串修改使用者
- **THEN** 系統回傳 422

### Requirement: 系統日誌記錄
系統 SHALL 將下列事件寫入系統日誌：登入成功、登入失敗、註冊、資料記錄建立／修改／刪除、批量匯入、角色變更、啟用狀態變更、未預期的伺服器錯誤、批次寫入失敗。每筆包含時間、等級（INFO/WARNING/ERROR）、事件類型、訊息、相關使用者（若有）與來源 IP（若有）。寫入系統日誌失敗 MUST NOT 讓原本的請求失敗。

#### Scenario: 登入失敗被記錄
- **WHEN** 有人以錯誤密碼登入 username=alice
- **THEN** 系統日誌新增一筆 WARNING、事件 login_failed，訊息包含 alice

### Requirement: 系統日誌查詢
Admin SHALL 能分頁查詢系統日誌，可依時間範圍、等級、事件類型與使用者篩選，預設依時間降冪排列。

#### Scenario: 只看錯誤
- **WHEN** Admin 以 level=ERROR 查詢
- **THEN** 只回傳 ERROR 等級的日誌，最新的在前

### Requirement: 資料庫狀態監控
Admin SHALL 能查詢資料庫狀態，包含：資料庫是否可連線與回應時間（毫秒）、連線池狀態（大小、使用中、閒置、溢出）、各資料表筆數、即時資料暫存區目前筆數、上次批次寫入時間、筆數與觸發原因（定期或條件）。取得這些資訊 MUST NOT 使用原生 SQL。

#### Scenario: 查看狀態
- **WHEN** Admin 呼叫資料庫狀態 API
- **THEN** 回傳上述所有欄位，資料庫正常時 connected=true

#### Scenario: 資料庫無法連線
- **WHEN** 資料庫暫時無法連線時 Admin 呼叫資料庫狀態 API
- **THEN** 系統回傳 503 `{"detail": "Database unavailable"}`（身分驗證本身需要讀資料庫，因此無法回報細節），不回傳 500 或堆疊資訊

### Requirement: 錯誤處理與執行日誌
API 錯誤回應 SHALL 統一使用 `{"detail": ...}` 格式。未預期的例外 MUST 回傳 500 `{"detail": "Internal server error"}`，回應中 MUST NOT 包含堆疊或內部錯誤訊息，並同時寫入執行日誌與系統日誌（server_error）。後端 SHALL 將每個 HTTP 請求的方法、路徑、狀態碼與耗時輸出到標準輸出。

#### Scenario: 未預期錯誤
- **WHEN** 某個 API 在處理中發生未預期的例外
- **THEN** 客戶端收到 500 `{"detail": "Internal server error"}`，`docker compose logs backend` 可看到完整堆疊，系統日誌新增一筆 server_error

#### Scenario: 請求日誌
- **WHEN** 使用者呼叫任一 API
- **THEN** `docker compose logs backend` 出現一行包含方法、路徑、狀態碼與耗時的記錄

### Requirement: 即時資料歷史查詢
Admin SHALL 能分頁查詢已寫入資料庫的即時監控資料，可依伺服器、指標、時間範圍與「只看異常」篩選，預設依時間降冪排列。非 Admin MUST 收到 403。

#### Scenario: 查詢某伺服器的異常
- **WHEN** Admin 以 server=server-2、anomaly_only=true 查詢
- **THEN** 只回傳 server-2 且 is_anomaly=true 的資料

#### Scenario: User 查詢歷史
- **WHEN** User 呼叫即時資料歷史 API
- **THEN** 系統回傳 403
