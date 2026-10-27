# Tasks

## 1. 專案骨架與 Docker

- [x] 1.1 建立 `backend/`、`frontend/`、`sample_data/` 目錄結構（依 design.md 決策 1），加入 `.gitignore`（含 `.env`、`.pixi/`、`.superpowers/`、`__pycache__/`）；驗證：目錄與檔案存在
- [x] 1.2 撰寫根目錄 `pixi.toml`（conda-forge 優先、缺少的放 `[pypi-dependencies]`、共用 Python 3.14、`backend`／`test` feature、`backend`／`backend-prod` environments 同一 solve-group、後端 `dev`／`migrate`／`seed`／`test` tasks 設定 `cwd = "backend"`，依 design.md 決策 16）並產生 `pixi.lock`；`[feature.backend.dependencies]` 明確列出 `sqlalchemy >=2.1,<2.2` 與 `greenlet`，asyncmy 放 `[feature.backend.pypi-dependencies]`，`platforms` 含 linux-64、linux-aarch64、osx-arm64；撰寫 `.env.example`（design.md 決策 13 的所有變數，每個附註解）與 `app/core/config.py`（pydantic-settings，`env_file=("../.env", ".env")`）；驗證：`pixi.lock` 含 linux-64 與 linux-aarch64，`cp .env.example .env` 後在 `backend/` 目錄執行 `pixi run -e backend python -c "from app.core.config import settings; print(settings)"` 成功
- [x] 1.3 撰寫 `app/core/logging.py`（stdout 格式 + 請求日誌 middleware）與 `app/main.py`（空 lifespan、`GET /health`）；驗證：本地 `pixi run -e backend dev` 後 `curl localhost:8000/health` 回 200，終端機看得到請求日誌
- [x] 1.4 撰寫根目錄 `.dockerignore` 與後端多階段 `backend/Dockerfile`（build context 為專案根目錄；`build` 階段 `pixi install --locked -e backend-prod`；產生 `pixi shell-hook` 啟用腳本；`runtime` 以 `debian:trixie-slim` 只複製 `.pixi/envs/backend-prod` 到相同路徑與啟用腳本、`backend/` 程式碼、`entrypoint.sh` 先 source 啟用腳本、環境 `bin` 加入 PATH、非 root 執行；`test` 階段安裝 `backend` 環境）與 `entrypoint.sh`；驗證：`docker build` 成功，runtime 映像中沒有 gcc 與 pixi，`python --version` 為 3.14
- [x] 1.5 在根目錄 `pixi.toml` 加入 `frontend` feature 與 environment（獨立 solve-group、`dev` task 設定 `cwd = "frontend"` 與後端位址 `env`）並更新 `pixi.lock`；撰寫多階段 `frontend/Dockerfile`（同後端做法，安裝 `frontend` 環境）與最小 `app.py`（顯示「Hello」）；驗證：本地 `pixi run -e frontend dev` 可開啟頁面，`docker build -f frontend/Dockerfile .` 成功
- [x] 1.6 撰寫 `docker-compose.yml`（db / backend / frontend、build context 為根目錄並以 `dockerfile:` 指定、healthcheck、depends_on、app-net、db_data volume、db 對主機開放 3306、backend／frontend 以 `env_file: .env` 注入變數、frontend healthcheck）；驗證：`cp .env.example .env && docker compose up -d --build` 後三個服務 healthy，8501 與 8000/docs 可開啟
- [x] 1.7 在 README 寫入「技術棧」、「本地運行」（pixi 安裝與 pixi tasks）、「Docker 部署」三節；驗證：照 README 指令在乾淨環境，分別以 pixi 本地運行與 Docker 啟動都成功

## 2. 資料庫層與遷移

- [x] 2.1 撰寫 `app/db/base.py`（DeclarativeBase、created_at/updated_at mixin，以 Python 端 `default`／`onupdate` 產生 UTC 時間，不用 `server_default`）與 `app/db/session.py`（async engine 含連線池參數、async_sessionmaker、`get_db`）；驗證：`/health` 改為同時檢查 DB 連線，DB 停掉時回 503
- [x] 2.2 依 design.md「DB Schema」撰寫四個模型（users、records、metrics、system_logs，含 ENUM、FK、索引；`users.id` 為 UUIDv7，以標準庫 `uuid.uuid7` 為預設值，`records.owner_id`／`system_logs.user_id` 為 UUID 外鍵）；驗證：`python -c "import app.models"` 無錯誤
- [x] 2.3 以 `alembic init -t async` 建立 Alembic，設定 `env.py` 讀 settings 與 `Base.metadata`，autogenerate 初始遷移並人工檢查 ENUM、索引，以及使用者 id 與外鍵欄位為 MariaDB `UUID` 型別（不是 `CHAR(32)`）；驗證：遷移檔中沒有 `sa.text(...)`，`alembic upgrade head` 後資料庫有 4 張表與 `alembic_version`，`SHOW CREATE TABLE users` 顯示 `id` 為 `uuid`，`alembic downgrade base` 可完整回退
- [ ] 2.4 `entrypoint.sh` 加入 `alembic upgrade head`（`set -e`）；驗證：刪除 volume 重新 `up` 後表自動建立
- [x] 2.5 在 compose 加入 `profiles: ["test"]` 的 `db-test` 與 `backend-test`（後端 Dockerfile `test` target，執行 `pixi run -e backend test`），撰寫 `tests/conftest.py`（建立/清除資料表、測試 engine 使用 `NullPool`、pytest-asyncio loop scope 設為 session、AsyncClient 與 WebSocket 用的 TestClient、模擬器停用、建立各角色使用者的 fixture，測試資料庫名稱必須以 `_test` 結尾）；驗證：`docker compose --profile test run --rm backend-test` 執行一個 `/health` 測試通過
- [x] 2.6 README 新增「執行測試」一節；驗證：照文件指令可跑測試

## 3. 認證、角色與系統日誌

- [x] 3.1 撰寫 `app/core/security.py`（bcrypt 雜湊/驗證、超過 72 bytes 的密碼驗證直接回 False、JWT 簽發/解析），並在 `tests/conftest.py` 加入各角色 token 的 fixture；驗證：單元測試涵蓋雜湊驗證、超長密碼不拋例外、token 過期
- [x] 3.2 撰寫 `services/audit_service.py`（獨立 session、失敗不拋出）；驗證：單元測試確認寫入一筆日誌，以及 DB 錯誤時不拋例外
- [x] 3.3 撰寫 user/auth schemas 與 `routers/auth.py`（register、login 使用 OAuth2PasswordRequestForm）、`routers/users.py`（me），註冊與登入成功/失敗寫入系統日誌；驗證：測試涵蓋 `user-auth` spec 的註冊、登入、帳號停用情境，以及註冊回傳的 id 為版本 7 的 UUID、密碼超過 72 bytes 註冊回 422 且登入回 401、回應中的時間字串以 `Z` 結尾（建立共用的 `UtcDatetime` 輸出型別）
- [x] 3.4 撰寫 `deps.py`（`get_current_user` 每次讀 DB、`require_roles`）；驗證：測試涵蓋未帶 token、過期 token、停用後舊 token 回 403
- [x] 3.5 全域例外處理：未處理例外記 logger 與 `server_error` 系統日誌並回 500；驗證：測試用一個會拋例外的測試路由確認回應不含堆疊
- [x] 3.6 撰寫 `app/seed.py`（三個測試帳號，可重複執行）並加進 `entrypoint.sh`；驗證：重啟兩次後 users 表仍只有 3 個測試帳號；Swagger Authorize 以 admin 登入成功
- [x] 3.7 README 新增「測試帳號」與「API 文件連結」兩節；驗證：文件中的帳密可登入

## 4. 資料記錄模組

- [ ] 4.1 撰寫 record schemas（建立、部分更新、回應含 owner username、分頁回應、排序欄位白名單）；驗證：schema 單元測試拒絕空白標題與不允許的排序欄位
- [ ] 4.2 撰寫 `services/record_service.py` 與 `routers/records.py` 的建立、列表（分頁/篩選/排序）、單筆、分類清單；驗證：測試涵蓋 `data-records` spec 的建立、分頁、篩選排序、404、分類清單情境
- [ ] 4.3 實作 PATCH 與 DELETE 的擁有者檢查，並寫入系統日誌；驗證：測試涵蓋建立者可改、他人 403、Admin 可改、Viewer 刪除 403
- [ ] 4.4 撰寫 `services/import_service.py` 與 `POST /records/import`（CSV/JSON、全有全無、415/413/422）；驗證：測試涵蓋成功、部分錯誤不寫入、格式不支援、超過上限
- [ ] 4.5 建立 `sample_data/records.csv`（約 50 筆、含合法欄位）；驗證：以 user 帳號透過 Swagger 匯入回 201 `{imported: 50}`
- [ ] 4.6 `seed.py` 加入範例資料（records 為空時產生約 200 筆最近 30 天、固定亂數種子）；驗證：首次啟動後有約 200 筆，重啟不增加

## 5. 即時監控模組（後端）

- [ ] 5.1 撰寫 `realtime/simulator.py`（隨機漫步 + 約 1% 尖峰、閾值判斷 `>`）；驗證：單元測試確認一次產生 9 筆、數值在範圍內、等於閾值不算異常
- [ ] 5.2 撰寫 `realtime/buffer.py`（MetricBuffer、asyncio.Event 條件觸發且醒來即 clear、timeout 定期觸發、空暫存區不寫入、失敗放回並等滿一個週期才重試、10,000 筆上限、記錄上次寫入資訊）；驗證：單元測試涵蓋 `realtime-monitoring` spec 的定期、條件、DB 失敗後不提早重試、關閉時 flush 情境
- [ ] 5.3 撰寫 `realtime/manager.py`（ConnectionManager）與 `routers/ws.py`（先 accept 再驗證 query token，失敗以 1008 關閉）；驗證：TestClient 測試無效 token 收到 1008、有效 token 可連線並收到廣播；另以真實 uvicorn 加 websocket-client 手動確認無效 token 收到 close code 1008，而不是 HTTP 403
- [ ] 5.4 在 `main.py` lifespan 啟動模擬器與批次寫入任務、關閉時先取消兩者再執行最後一次 flush，受 `SIMULATOR_ENABLED` 控制；驗證：`docker compose up` 後 30 秒內 metrics 表有資料，`docker compose logs backend` 看得到批次寫入日誌
- [ ] 5.5 撰寫 `GET /api/v1/metrics`（Admin 歷史查詢：伺服器/指標/時間/只看異常/分頁）；驗證：測試涵蓋篩選與 User 403

## 6. 資料分析模組

- [ ] 6.1 撰寫 analytics schemas（source、篩選驗證：metrics 必填 metric、start ≤ end、預設時間範圍）；驗證：測試涵蓋兩個 422 情境
- [ ] 6.2 撰寫 `services/analytics_service.py` 的 summary、groups、trend（`func.date_format` 分桶）與對應路由；驗證：測試以已知資料驗證 count/sum/avg/max/min、空資料回 null、依分類與依伺服器分組、依小時趨勢
- [ ] 6.3 撰寫 `services/excel_service.py` 與 `GET /analytics/export`（四個工作表、明細上限 10,000 筆並註明）；驗證：測試以 openpyxl 讀回確認有四個工作表、Viewer 可下載

## 7. 系統管理模組（後端）

- [ ] 7.1 撰寫 `GET /admin/users` 與 `PATCH /admin/users/{user_id}`（自我保護、寫入 role_change/user_status_change 日誌）；驗證：測試涵蓋調整角色後權限立即改變、Admin 停用自己回 400、不存在的 UUID 回 404、非 UUID 格式回 422
- [ ] 7.2 撰寫 `GET /admin/logs`（篩選與分頁）；驗證：測試確認錯誤登入後可用 action=login_failed 查到
- [ ] 7.3 撰寫 `GET /admin/db-status`（連線狀態與回應時間、連線池、各表筆數、暫存區、上次寫入資訊，不用原生 SQL）；驗證：測試確認欄位齊全；手動停掉 db 時任一受保護 API（含此端點）回 503 而非 500
- [ ] 7.4 以 `grep -rn "text(" backend/app` 確認沒有原生 SQL，並跑完整後端測試；驗證：grep 無結果、所有測試通過

## 8. Streamlit 前端

- [ ] 8.1 撰寫 `lib/api.py`（帶 token、401 清除 session）與 `app.py`（st.navigation 依登入狀態與角色組頁面、側邊欄使用者資訊與登出）、`views/login.py`（登入/註冊分頁）；驗證：手動以三個帳號登入，選單符合 `web-dashboard` spec；登出回登入頁
- [ ] 8.2 撰寫 `lib/ws_listener.py`（daemon 執行緒、deque、自動重連、close）；驗證：登入後在 Python console 確認 deque 每秒增加
- [ ] 8.3 撰寫 `lib/charts.py` 與 `views/monitor.py`（`@st.fragment(run_every=1)`、數值卡片、折線圖含閾值線與紅色異常點、柱狀圖、告警清單、連線狀態、指標切換）；驗證：手動觀察 1 分鐘內圖表每秒更新；把 `THRESHOLD_CPU` 設 50 重啟後看到紅色標示；切換頁面再回來資料仍在
- [ ] 8.4 撰寫 `views/records.py`（篩選、分頁表格、新增表單、編輯/刪除、匯入並顯示逐列錯誤，依角色隱藏）；驗證：以 viewer 看不到操作元件；以 user 匯入 `sample_data/records.csv` 成功、匯入錯誤檔看到列號
- [ ] 8.5 撰寫 `views/analytics.py`（來源切換、篩選、統計卡片、分組柱狀圖、趨勢折線圖、Excel 下載）；驗證：下載的檔案可用 Excel/LibreOffice 開啟且數字與畫面一致
- [ ] 8.6 撰寫 `views/admin.py`（使用者管理 data_editor + 儲存、日誌、DB 狀態、即時資料歷史四個分頁）；驗證：手動把 user 改成 viewer 後以該帳號重新登入看到 Viewer 介面
- [ ] 8.7 Token 過期處理：將 `JWT_EXPIRE_MINUTES=1` 測試；驗證：過期後操作回到登入頁並顯示過期提示

## 9. 文件與整合驗證

- [ ] 9.1 README 補齊「專案介紹」、「系統架構圖」（複製 design.md 的 Mermaid 架構圖與 ER 圖）、「已知限制與改進方向」；驗證：推到 GitHub 後 Mermaid 圖正確顯示
- [ ] 9.2 全新環境端對端驗證：`docker compose down -v` → 照 README 從頭操作，逐一走過 7 個 spec 的主要情境（含 down/up 後資料保留）；驗證：所有情境符合，問題修正後重跑
- [ ] 9.3 執行 `openspec validate realtime-analytics-monitoring-system --strict` 並確認 tasks 全部勾選；驗證：validate 通過

## Workflow follow-up

- 推送至 GitHub 前確認 `.env` 與 `.pixi/` 未被提交、`pixi.lock` 已提交。
- 實作完成並通過 code review 後封存此 change（`/opsx:archive`）。
