# Proposal

## Why

目前登入狀態只存在 Streamlit 的 session（`st.session_state`），重新整理瀏覽器頁面或開新分頁就要重新登入，是 README「已知限制」中最影響日常使用的一項。Streamlit 1.66 的 `st.App` 可以在前端伺服器上加自訂 HTTP 路由，讓我們不靠第三方元件就能以 HttpOnly cookie 保存登入，因此現在可以解決。

## What Changes

- 登入成功後，前端伺服器以 HttpOnly、SameSite=Lax 的 cookie 保存 JWT，有效期與 JWT 相同；瀏覽器端 JavaScript 讀不到 token。
- 新的 Streamlit session 開始時（重新整理、開新分頁），若 cookie 中有 token 且後端確認仍有效，直接恢復登入狀態並進入原本的頁面，不需重新輸入帳密。
- 登出、token 過期或帳號停用時，除了清除 session 狀態，也會清除 cookie；過期提示改為在回到登入頁後顯示。
- 前端改由 `st.App` 啟動（新增入口檔），加上兩個自訂路由：一個用一次性票證換取 cookie，一個清除 cookie。JWT 不會出現在網址上。
- 後端 API 不變；前端不新增套件。
- README「已知限制」移除「重新整理需要重新登入」，改為說明登入保存在 cookie 及其行為（多分頁共用、HTTPS 下加 Secure）。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `web-dashboard`：「登入、註冊與登出」改為登入狀態保存在瀏覽器 cookie、重新整理後保持登入、登出清除 cookie；「Session 過期處理」改為同時清除 cookie，並刪除「重新整理後需重新登入是可接受的行為」。

## Impact

- **前端程式**：`frontend/lib/session.py`（恢復登入、登出時導向清除 cookie）、`frontend/app.py`（啟動時嘗試從 cookie 恢復）、`frontend/views/login.py`（登入成功後導向設定 cookie、讀取過期提示）、新增 `st.App` 入口與 cookie 路由模組。
- **部署**：`frontend/entrypoint.sh` 與 pixi 的 frontend `dev` task 改為執行新的入口檔；Compose 健康檢查（`/_stcore/health`）不變。
- **後端**：無變更，仍以 `Authorization: Bearer` 驗證；每次恢復登入會多一次 `GET /users/me`。
- **文件**：README 已知限制、`openspec/specs/web-dashboard`。
