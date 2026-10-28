# Spec Delta

## ADDED Requirements

### Requirement: 重新整理後保持登入
登入成功後，介面 SHALL 將登入憑證保存在瀏覽器 cookie，cookie MUST 設為 HttpOnly 與 SameSite=Lax，有效期不超過 token 本身的有效期，經由 HTTPS 存取時 MUST 加上 Secure。token MUST NOT 出現在網址列或瀏覽紀錄中。重新整理頁面或在同一瀏覽器開新分頁時，若 cookie 中的 token 仍有效且帳號仍啟用，介面 SHALL 直接恢復登入狀態，不需重新輸入帳密；若已無效，MUST 清除 cookie 並顯示登入頁。

#### Scenario: 重新整理後仍在登入狀態
- **WHEN** 已登入的使用者在資料記錄頁重新整理瀏覽器頁面
- **THEN** 仍停留在資料記錄頁，側邊欄顯示其名稱與角色，不需重新登入

#### Scenario: 開新分頁
- **WHEN** 已登入的使用者在同一瀏覽器開啟新分頁進入系統
- **THEN** 新分頁直接是登入狀態

#### Scenario: Token 到期後重新整理
- **WHEN** token 到期後使用者重新整理頁面
- **THEN** 顯示登入頁（cookie 與 token 同時到期，瀏覽器不再送出）

#### Scenario: Cookie 中的 token 已失效
- **WHEN** cookie 中的 token 被後端拒絕（例如簽章金鑰已更換），使用者重新整理頁面
- **THEN** 顯示登入頁與過期提示，cookie 被清除

#### Scenario: JavaScript 讀不到 token
- **WHEN** 登入後在瀏覽器開發者工具執行 `document.cookie`
- **THEN** 結果中沒有登入用的 token

## MODIFIED Requirements

### Requirement: 登入、註冊與登出
未登入的使用者 SHALL 只能看到登入／註冊頁。登入成功後進入即時監控頁，側邊欄顯示目前使用者名稱、角色與登出按鈕。登出 MUST 清除該瀏覽器分頁的登入狀態、停止即時資料接收，並清除保存登入的 cookie。註冊成功後提示使用者登入。

#### Scenario: 登入成功
- **WHEN** 使用者在登入頁輸入正確帳號密碼
- **THEN** 進入即時監控頁，側邊欄顯示其名稱與角色

#### Scenario: 登入失敗
- **WHEN** 使用者輸入錯誤密碼
- **THEN** 停留在登入頁並顯示錯誤訊息，不設定 cookie

#### Scenario: 登出
- **WHEN** 使用者點擊登出
- **THEN** 回到登入頁，無法再看到其他頁面

#### Scenario: 登出後重新整理
- **WHEN** 使用者登出後重新整理頁面
- **THEN** 仍是登入頁，不會恢復登入

### Requirement: Session 過期處理
當後端回應 401（token 過期或無效）、因帳號停用回應 403，或 WebSocket 以 close code 1008 拒絕連線時，介面 SHALL 視為登入已結束：清除登入狀態與保存登入的 cookie、停止即時資料接收、回到登入頁並提示「登入已過期或帳號已停用，請重新登入」。一般權限不足的 403 不登出，只顯示錯誤訊息。

#### Scenario: Token 過期
- **WHEN** 使用者的 token 過期後在資料記錄頁按下查詢
- **THEN** 回到登入頁並顯示過期提示

#### Scenario: 帳號被停用後重新整理
- **WHEN** Admin 停用某使用者後，該使用者重新整理頁面
- **THEN** 顯示登入頁與過期提示，不會恢復登入
