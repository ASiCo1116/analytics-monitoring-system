# user-auth Specification

## Purpose
讓使用者註冊帳號、登入取得 JWT，並以 Admin / User / Viewer 三種角色決定每個人能執行的操作。

## Requirements

### Requirement: 使用者註冊
系統 SHALL 允許任何人以帳號（username）、Email 與密碼註冊新帳號，新帳號角色一律為 User 且為啟用狀態。使用者 id SHALL 由系統產生，格式為 UUIDv7，API 以標準 36 字元字串表示。username 為 3–50 字元的英數字或底線；密碼至少 8 字元，且 UTF-8 編碼後不超過 72 bytes（bcrypt 的上限）；username 與 Email 皆不可重複。回應 MUST NOT 包含密碼或其雜湊值。

#### Scenario: 註冊成功
- **WHEN** 訪客以未使用過的 username、合法 Email 與 8 字元以上密碼呼叫註冊 API
- **THEN** 系統回傳 201 與使用者資料（id、username、email、role=user、is_active=true），且回應中沒有密碼欄位

#### Scenario: 帳號重複
- **WHEN** 訪客以已存在的 username 或 Email 註冊
- **THEN** 系統回傳 409 `{"detail": "Username or email already registered"}`，不指出是 username 還是 Email 重複

#### Scenario: 輸入不合法
- **WHEN** 訪客以 7 字元密碼或格式錯誤的 Email 註冊
- **THEN** 系統回傳 422 並列出驗證錯誤

#### Scenario: 密碼過長
- **WHEN** 訪客以 UTF-8 編碼後超過 72 bytes 的密碼註冊
- **THEN** 系統回傳 422，不會回傳 500

#### Scenario: 註冊時無法指定角色
- **WHEN** 訪客在註冊請求中附帶 role=admin
- **THEN** 該欄位被忽略，新帳號角色仍為 user

#### Scenario: 使用者 id 為 UUIDv7
- **WHEN** 訪客先後註冊兩個帳號
- **THEN** 兩者回傳的 id 皆為版本 7 的 UUID 字串，且後註冊者的 id 依字串排序大於先註冊者

### Requirement: 使用者登入取得 JWT
系統 SHALL 在帳號密碼正確且帳號為啟用狀態時，回傳 Bearer JWT access token。Token MUST 包含使用者 id 與角色，有效期由環境變數設定（預設 60 分鐘）。登入介面 MUST 相容 OAuth2 password flow，使 Swagger 的 Authorize 按鈕可直接使用。

#### Scenario: 登入成功
- **WHEN** 使用者以正確帳號密碼登入
- **THEN** 系統回傳 200 與 `{access_token, token_type: "bearer"}`

#### Scenario: 密碼錯誤
- **WHEN** 使用者以錯誤密碼或不存在的帳號登入
- **THEN** 系統回傳 401，且錯誤訊息不透露是帳號還是密碼錯誤

#### Scenario: 登入密碼過長
- **WHEN** 使用者以 UTF-8 編碼後超過 72 bytes 的密碼登入
- **THEN** 系統回傳 401，不會回傳 500

#### Scenario: 帳號已停用
- **WHEN** 已被停用的使用者以正確帳號密碼登入
- **THEN** 系統回傳 403

### Requirement: 受保護的 API 需要有效 Token
除註冊、登入與健康檢查外，所有 API SHALL 要求有效的 Bearer token。Token 無效、過期，或其使用者已不存在／已停用時，系統 MUST 回傳 401（停用為 403）。

#### Scenario: 未帶 Token
- **WHEN** 使用者未帶 Authorization header 呼叫任一受保護 API
- **THEN** 系統回傳 401

#### Scenario: Token 過期
- **WHEN** 使用者以已過期的 token 呼叫受保護 API
- **THEN** 系統回傳 401

#### Scenario: 使用者被停用後舊 Token 失效
- **WHEN** Admin 停用某使用者後，該使用者以先前取得的 token 呼叫受保護 API
- **THEN** 系統回傳 403

### Requirement: 查詢目前登入者
系統 SHALL 提供 API 讓已登入使用者取得自己的帳號資料（id、username、email、role、is_active、created_at）。

#### Scenario: 取得自己的資料
- **WHEN** 已登入使用者呼叫「目前使用者」API
- **THEN** 系統回傳該使用者自己的資料

### Requirement: 角色權限規則
系統 SHALL 依角色限制操作：所有角色皆可讀取資料記錄、即時監控與分析資料並下載 Excel；僅 Admin 與 User 可新增與匯入資料記錄；修改與刪除資料記錄僅限建立者本人或 Admin；系統管理功能僅限 Admin。權限不足時 MUST 回傳 403。

#### Scenario: Viewer 嘗試新增
- **WHEN** Viewer 呼叫新增資料記錄 API
- **THEN** 系統回傳 403

#### Scenario: User 嘗試進入管理功能
- **WHEN** User 呼叫任一系統管理 API
- **THEN** 系統回傳 403

#### Scenario: Viewer 可讀取
- **WHEN** Viewer 呼叫資料記錄列表、分析統計或 Excel 下載 API
- **THEN** 系統正常回傳 200
