# Proposal

## Why

需要一套「即時資料分析與監控系統」：即時觀察多台伺服器的運作指標並在超過閾值時告警，同時讓使用者管理手動資料記錄、進行統計分析與匯出報表，並依角色控管權限。系統要能以 `docker compose up` 一鍵啟動，程式碼以可讀、易維護為優先。因此本提案的取捨原則是：需求範圍內的每一項都要做到且可被實際驗證，但不額外加功能，寫法以「清楚、貼近官方文件」優先於「抽象、炫技」。

模擬資料的主題選定為「伺服器監控指標」（多台伺服器的 CPU／記憶體／溫度），讓分類、閾值告警等需求有自然的語意。

## What Changes

從零建立整個系統：

- **後端（FastAPI）**：RESTful API（`/api/v1`）、JWT 認證、三種角色（Admin / User / Viewer）權限控制、Pydantic 驗證、Swagger 文件、統一錯誤處理與日誌。
- **資料庫（MariaDB 11.7）**：使用者 id 採用 UUIDv7，其餘資料表使用自增整數主鍵；全部透過 SQLAlchemy 2.1 async ORM（asyncmy driver）存取，Alembic 管理遷移，Engine 連線池管理；共四張表：`users`、`records`、`metrics`、`system_logs`。
- **即時監控**：後端背景任務每秒產生 3 台伺服器 × 3 種指標的模擬數值，超過閾值即標記異常，經 WebSocket 推送給已登入的前端，並以「每 10 秒或累積滿 N 筆」條件批次寫入 `metrics` 表。
- **資料管理**：使用者手動建立的資料記錄（`records`）支援 CRUD、分頁／篩選／排序、CSV/JSON 批量匯入；修改與刪除僅限建立者或 Admin。
- **資料分析**：可對「資料記錄」或「即時監控資料」做統計（筆數、總計、平均、最大、最小）、時間範圍查詢、分類聚合、趨勢圖，並可下載 Excel。
- **系統管理（Admin）**：使用者列表與角色／啟用狀態管理、系統日誌查詢、資料庫狀態監控、即時資料歷史查詢。
- **前端（Streamlit）**：多頁面應用（登入、即時監控、資料記錄、資料分析、系統管理），依角色顯示頁面，即時圖表每秒更新。
- **套件管理（pixi）**：專案根目錄一份 `pixi.toml`，以 feature／environment 區分前端、後端與測試依賴（conda-forge 優先，缺的從 PyPI），提交 `pixi.lock`，本地開發與 Docker 映像使用同一份鎖定版本；常用指令定義為 pixi tasks。
- **部署**：前後端各一個多階段 Dockerfile，Docker Compose 編排 `db`、`backend`、`frontend` 三個容器，Volume 持久化資料庫；後端啟動時自動遷移並建立測試帳號。
- **文件與範例**：README（專案介紹、技術棧、本地運行、Docker 部署、API 文件連結、測試帳號）、`.env.example`、CSV 範例、Mermaid 系統架構圖。

## Capabilities

### New Capabilities

- `user-auth`: 使用者註冊、登入取得 JWT、身分驗證，以及 Admin / User / Viewer 三種角色的權限規則。
- `data-records`: 使用者手動資料記錄的建立、查詢（分頁／篩選／排序）、修改、刪除與 CSV/JSON 批量匯入，含擁有者權限限制。
- `realtime-monitoring`: 模擬伺服器指標的即時產生、閾值異常標記、WebSocket 推送，以及定期／條件觸發的批次持久化。
- `data-analytics`: 針對資料記錄或即時監控資料的統計、時間範圍查詢、分類聚合、趨勢序列與 Excel 匯出。
- `system-admin`: Admin 專用的使用者管理、系統日誌查詢、資料庫狀態監控與即時資料歷史查詢。
- `web-dashboard`: Streamlit 網頁介面的登入／登出、依角色的多頁面導覽、Session 狀態與即時圖表更新。
- `deployment`: 以 Docker Compose 一鍵啟動整套系統，含自動遷移、測試帳號建立、資料持久化與環境變數設定。

### Modified Capabilities

（無，這是全新專案）

## Impact

- **新程式碼**：`backend/`（FastAPI 應用、Alembic、測試）、`frontend/`（Streamlit 應用）、根目錄 `pixi.toml`／`pixi.lock`、`docker-compose.yml`、`.env.example`、`sample_data/`、`README.md`。
- **對外介面**：REST API `http://localhost:8000/api/v1/...`、WebSocket `ws://localhost:8000/ws/metrics`、Swagger `http://localhost:8000/docs`、前端 `http://localhost:8501`。
- **主要相依套件**（以 pixi 安裝，conda-forge 優先，沒有的從 PyPI 取得）：python 3.14、fastapi、uvicorn、sqlalchemy 2.1、greenlet、asyncmy（PyPI）、alembic、pydantic-settings、PyJWT、bcrypt、openpyxl、python-multipart、email-validator；前端 streamlit、requests、websocket-client、plotly；測試 pytest、pytest-asyncio、httpx。
- **執行環境**：Docker 與 Docker Compose v2；MariaDB 11.7 官方映像；本地開發另需 pixi。
