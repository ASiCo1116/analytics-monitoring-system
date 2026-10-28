# Tasks

## 1. st.App 入口與 cookie 路由

- [x] 1.1 新增 `frontend/lib/login_cookie.py`：一次性票證（`secrets.token_urlsafe(32)`，30 秒、取出即刪、存取時清掉過期項目、以 lock 保護）、從 JWT `exp` 計算 `Max-Age`，以及 `GET /session/start`、`GET /session/end` 兩個 Starlette 路由（cookie `ams_session`：HttpOnly、SameSite=Lax、Path=/，HTTPS 時加 Secure）；`pixi run lint` 通過
- [x] 1.2 新增 `frontend/server.py`（`app = st.App("app.py", routes=...)`），`frontend/entrypoint.sh` 與 pixi frontend `dev` task 改為 `streamlit run server.py`；驗證 `pixi run -e frontend dev` 啟動後 `/_stcore/health` 回 200、首頁可開
- [x] 1.3 以 curl 驗證路由：無效或過期票證導回 `/` 且不設 cookie；有效票證回 303 並帶 `Set-Cookie: ams_session=…; HttpOnly; SameSite=lax; Path=/; Max-Age=…`，同一票證第二次使用無效；`/session/end` 回 303 並刪除 cookie，`?expired=1` 時導向 `/?expired=1`

## 2. 登入、恢復與登出流程

- [x] 2.1 `frontend/lib/session.py` 加上導向輔助函式（`st.html(..., unsafe_allow_javascript=True)` 搭配 `location.replace`），登入成功後發票證並導向 `/session/start`；`frontend/views/login.py` 改用新流程，登入失敗不導向；`pixi run lint` 通過
- [x] 2.2 `frontend/app.py`：尚未登入且 `st.context.cookies` 有 `ams_session` 時呼叫 `GET /users/me`，200 恢復登入，401 或停用帳號的 403 導向 `/session/end?expired=1`，連線失敗或 5xx 顯示錯誤但不清 cookie；`pixi run lint` 通過
- [x] 2.3 登出按鈕、`api.request` 的 401／停用 403、WebSocket 1008 改為 `session.end()` 後導向 `/session/end`（過期時帶 `expired=1`）；登入頁改從 `st.query_params["expired"]` 顯示過期提示並移除該參數；`pixi run lint` 通過
- [x] 2.4 更新 README：「已知限制」移除重新整理需重新登入，改為說明登入保存在 HttpOnly cookie、有效期同 JWT、其他分頁在重新整理後才登出、HTTPS 下加 Secure；系統架構圖中前端節點的說明（`session_state 存 JWT`）一併更新

## 3. 整合驗證

- [x] 3.1 `docker compose up -d --build` 後三個服務皆 healthy，並在瀏覽器依 `specs/web-dashboard/spec.md` 的情境逐一驗證：登入成功、登入失敗不設 cookie、重新整理仍在原頁、開新分頁已登入、`document.cookie` 看不到 token、登出後重新整理仍是登入頁、token 過期（暫時把 `JWT_EXPIRE_MINUTES` 設為 1）與帳號停用後重新整理顯示過期提示
- [x] 3.2 `pixi run lint` 與 `docker compose --profile test run --rm --build backend-test` 皆通過（後端未改動，確認沒有回歸）

## Workflow follow-up

- 實作完成並驗證後，以 `/opsx:archive` 封存此 change，將 `web-dashboard` 的 delta 同步到 `openspec/specs/`。
