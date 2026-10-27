# Design

## 系統架構圖

```mermaid
flowchart LR
    browser["👤 瀏覽器"]

    subgraph net["Docker network: app-net"]
        direction LR
        subgraph fe["frontend 容器 :8501"]
            st["Streamlit 多頁面應用<br/>session_state 存 JWT"]
            wsc["WebSocket 接收執行緒<br/>（每個使用者 session 一條）"]
        end

        subgraph be["backend 容器 :8000（1 個 uvicorn worker）"]
            api["REST API /api/v1<br/>JWT + 角色檢查"]
            wsr["WebSocket /ws/metrics"]
            gen["模擬器背景任務<br/>每秒 3 台 × 3 指標"]
            hub["ConnectionManager<br/>廣播給所有連線"]
            buf["MetricBuffer<br/>記憶體暫存區"]
            writer["批次寫入背景任務<br/>每 10 秒 或 滿 100 筆"]
        end

        db[("db 容器 :3306<br/>MariaDB 11.7")]
    end

    vol[("volume: db_data")]

    browser -- "HTTP :8501" --> st
    browser -. "Swagger :8000/docs" .-> api
    st -- "REST (requests)" --> api
    wsc <-- "WebSocket" --> wsr
    gen --> hub --> wsr
    gen --> buf --> writer
    api -- "SQLAlchemy async ORM<br/>asyncmy + 連線池" --> db
    writer -- "ORM 批次寫入" --> db
    db --- vol
```

### 即時資料流

```mermaid
sequenceDiagram
    participant G as 模擬器（每秒）
    participant M as ConnectionManager
    participant B as MetricBuffer
    participant W as 批次寫入任務
    participant DB as MariaDB
    participant F as Streamlit 接收執行緒

    G->>G: 產生 9 筆指標並判斷 is_anomaly
    G->>M: broadcast(批次)
    M-->>F: {"type":"metrics","data":[...]}
    G->>B: add(批次)
    alt 暫存 ≥ 100 筆（條件觸發）
        B->>W: 喚醒
    end
    W->>W: 等待「喚醒」或「10 秒到」
    W->>B: 取出全部
    W->>DB: session.add_all() + commit
    alt 寫入失敗
        W->>B: 放回暫存區，下次重試
    end
```

## DB Schema

```mermaid
erDiagram
    users ||--o{ records : "建立"
    users ||--o{ system_logs : "觸發（可為空）"

    users {
        UUID id PK "UUIDv7"
        VARCHAR(50) username UK
        VARCHAR(255) email UK
        VARCHAR(255) hashed_password
        ENUM role "admin | user | viewer"
        BOOLEAN is_active
        DATETIME created_at
        DATETIME updated_at
    }

    records {
        BIGINT id PK
        VARCHAR(200) title
        DOUBLE value
        VARCHAR(50) category
        TEXT description "nullable"
        DATETIME recorded_at "資料時間戳"
        UUID owner_id FK
        DATETIME created_at
        DATETIME updated_at
    }

    metrics {
        BIGINT id PK
        VARCHAR(50) server
        ENUM metric "cpu | memory | temperature"
        DOUBLE value
        DOUBLE threshold "產生當下的閾值"
        BOOLEAN is_anomaly
        DATETIME recorded_at
    }

    system_logs {
        BIGINT id PK
        ENUM level "INFO | WARNING | ERROR"
        VARCHAR(50) action
        VARCHAR(500) message
        UUID user_id FK "nullable"
        VARCHAR(45) ip_address "nullable"
        DATETIME created_at
    }
```

### 欄位與索引說明

**時區規則**：

- 資料庫一律存 **UTC**（naive `DATETIME`，由應用程式保證是 UTC），API 回傳 ISO 8601 並帶 `Z`，前端轉成 `APP_TIMEZONE`（預設 `Asia/Taipei`）顯示。
- 所有時間欄位（含 `created_at`／`updated_at`）都由應用程式以 `datetime.now(UTC)` 產生後去掉 tzinfo 寫入（模型的 Python 端 `default`／`onupdate`），不使用資料庫的 `NOW()`，避免受 MariaDB session 時區影響，遷移檔也不會出現 `sa.text('now()')`。
- 輸出：Pydantic v2 序列化 naive datetime 不會帶時區，因此回應中的時間欄位統一使用一個輸出型別（例如 `UtcDatetime`），把 naive UTC 補上 UTC 時區後序列化成以 `Z` 結尾的字串，所有回應 schema 共用。
- API 收到的時間（POST/PATCH 的 `recorded_at`、CSV/JSON 匯入、查詢參數 `start`/`end`）若帶時區就照時區轉 UTC；**沒帶時區則視為 `APP_TIMEZONE`**，因為人手寫的 CSV 和前端輸入都是台灣時間。轉換集中在一個 Pydantic 型別（例如 `LocalDatetime`）裡，所有 schema 共用。
- 趨勢分桶（hour/day）依 `APP_TIMEZONE` 切：查詢時以 `func.convert_tz(recorded_at, '+00:00', '+08:00')` 先轉成當地時間再 `date_format`。位移字串由 Python `zoneinfo` 依 `APP_TIMEZONE` 算出當下 offset（用固定 offset 是因為 MariaDB 官方映像沒有載入時區名稱表）。台灣沒有夏令時間，所以沒有問題；有夏令時間的時區在切換日會差 1 小時，記為已知限制。
- 因此後端也讀 `APP_TIMEZONE`。

**users**

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID PK（MariaDB 原生 `UUID` 型別，16 bytes） | UUIDv7，由後端產生 |
| username | VARCHAR(50), UNIQUE, NOT NULL | 3–50 字元英數字或底線 |
| email | VARCHAR(255), UNIQUE, NOT NULL | |
| hashed_password | VARCHAR(255), NOT NULL | bcrypt 雜湊 |
| role | ENUM('admin','user','viewer'), NOT NULL, 預設 'user' | |
| is_active | BOOLEAN, NOT NULL, 預設 true | 停用＝不能登入、舊 token 失效 |
| created_at / updated_at | DATETIME, NOT NULL | Python 端 `default`／`onupdate` 產生 UTC 時間 |

使用者不提供刪除功能，只能停用，因此 `records.owner_id` 與 `system_logs.user_id` 不會懸空。

**使用者 id 採用 UUIDv7**：

- UUIDv7 的前 48 bits 是毫秒時間戳，id 依建立時間大致遞增，寫入 InnoDB 叢集主鍵時接近循序寫入，不像 UUIDv4 隨機插入造成頁分裂。對外也不暴露流水號，無法從 id 推測使用者數量或逐一枚舉。
- 由後端產生（模型欄位 `default=uuid7`），不依賴資料庫函式，ORM 與測試行為一致。使用 Python 3.14 標準庫的 `uuid.uuid7()`，不需額外套件。
- 型別：SQLAlchemy `Uuid(as_uuid=True)`，對應 MariaDB 10.7+ 的原生 `UUID` 型別。這需要 **SQLAlchemy 2.1**：2.1 起 MariaDB 方言（含 asyncmy driver）在連線後偵測到 MariaDB 10.7+ 才改用原生 `UUID`；2.0 搭配 asyncmy 一律建成 `CHAR(32)`。因為型別是連線後才決定，Alembic 的 offline（`--sql`）模式仍會輸出 `CHAR(32)`，遷移一律以 online 模式執行。Alembic autogenerate 後人工確認 `users.id`、`records.owner_id`、`system_logs.user_id` 皆為 `UUID`，而不是 `CHAR(32)`。
- API：Pydantic 欄位型別為 `uuid.UUID`，JSON 以標準 36 字元字串（`xxxxxxxx-xxxx-7xxx-...`）表示；路徑與查詢參數中的使用者 id 格式不合時回 422；JWT 的 `sub` 為同一字串。
- 只有 users 使用 UUID。records、metrics、system_logs 維持 BIGINT 自增主鍵：它們不代表使用者身分，且 metrics 寫入量大，8 bytes 的整數主鍵索引較省空間。

**records**（使用者手動建立的資料記錄）

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | BIGINT PK | |
| title | VARCHAR(200), NOT NULL | |
| value | DOUBLE, NOT NULL | |
| category | VARCHAR(50), NOT NULL | 自由輸入，不另建分類表 |
| description | TEXT, NULL | 最多 1000 字元（Pydantic 檢查） |
| recorded_at | DATETIME, NOT NULL | 資料本身的時間戳，篩選、分析都用它 |
| owner_id | UUID FK → users.id, NOT NULL | 建立者，修改刪除權限依據 |
| created_at / updated_at | DATETIME, NOT NULL | |

索引：`ix_records_category`、`ix_records_recorded_at`、`ix_records_owner_id`。

**metrics**（模擬器產生的即時監控資料）

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | BIGINT PK | |
| server | VARCHAR(50), NOT NULL | 例：server-1 |
| metric | ENUM('cpu','memory','temperature'), NOT NULL | 單位由程式對照（% / % / °C），不存資料庫 |
| value | DOUBLE, NOT NULL | 四捨五入到小數 1 位 |
| threshold | DOUBLE, NOT NULL | 產生當下的閾值；之後改閾值不影響歷史判斷 |
| is_anomaly | BOOLEAN, NOT NULL | value > threshold |
| recorded_at | DATETIME, NOT NULL | 產生時間（同一秒的 9 筆相同） |

索引：`ix_metrics_metric_recorded_at (metric, recorded_at)`（分析查詢）、`ix_metrics_server_metric_recorded_at (server, metric, recorded_at)`（歷史查詢）、`ix_metrics_recorded_at`。`is_anomaly` 不單獨建索引：選擇性低，配合時間範圍查詢即可。

**system_logs**

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | BIGINT PK | |
| level | ENUM('INFO','WARNING','ERROR'), NOT NULL | |
| action | VARCHAR(50), NOT NULL | 見下方事件清單 |
| message | VARCHAR(500), NOT NULL | 人看得懂的描述，例如「alice 將 bob 的角色由 user 改為 viewer」 |
| user_id | UUID FK → users.id, NULL | 觸發者；登入失敗時若帳號不存在則為空 |
| ip_address | VARCHAR(45), NULL | 支援 IPv6 長度 |
| created_at | DATETIME, NOT NULL | |

索引：`ix_system_logs_created_at`、`ix_system_logs_level`、`ix_system_logs_action`。

事件類型（`action`）：`login_success`、`login_failed`、`register`、`record_create`、`record_update`、`record_delete`、`record_import`、`role_change`、`user_status_change`、`server_error`、`metric_flush_failed`。

## Context

全新系統，一切從零開始。限制條件：

- async SQLAlchemy、WebSocket、Streamlit 是相對少用的技術，這三塊採用最貼近官方文件的寫法並加簡短註解，降低維護門檻。
- 技術選型已定：MariaDB 11.7、SQLAlchemy ORM（禁止原生 SQL）、asyncmy、Alembic、JWT、Pydantic、Swagger、多階段 Dockerfile、Docker Compose；Python 環境與套件以 pixi 管理。
- 每個 spec 要求都要能在介面或 API 上實際操作驗證。

動機見 proposal.md - Why；行為要求見 `specs/`。

## Goals / Non-Goals

**Goals:**

- 程式碼分層清楚，每個檔案的職責一句話講得完，新加入的開發者讀得懂、改得動。
- 本地開發與 Docker 映像使用同一份 `pixi.lock`，套件版本一致。
- `docker compose up -d --build` 一次成功，不需額外手動步驟。
- 關鍵路徑（認證、權限、CRUD、匯入、批次寫入、分析）有自動化測試。

**Non-Goals:**

- 水平擴展（多個後端 worker／多台機器）：即時資料的產生與廣播都在單一行程內。
- Refresh token、忘記密碼、Email 驗證、使用者刪除。
- metrics 資料保留／清理排程（每天約 77 萬筆，目前規模可接受）。
- 由介面調整閾值（閾值只透過環境變數設定）。
- 前端在瀏覽器重新整理後保持登入。
- HTTPS、反向代理、正式環境的密鑰管理。

## Decisions

### 1. 專案結構：前後端分開兩個資料夾，後端按職責分層

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # 建立 FastAPI app、lifespan（啟停背景任務）、掛 router、例外處理
│   │   ├── core/
│   │   │   ├── config.py      # pydantic-settings：所有環境變數
│   │   │   ├── security.py    # bcrypt 雜湊、JWT 簽發與解析
│   │   │   └── logging.py     # Python logging 設定 + 請求日誌 middleware
│   │   ├── db/
│   │   │   ├── base.py        # DeclarativeBase、時間欄位 mixin
│   │   │   └── session.py     # create_async_engine（連線池）、async_sessionmaker、get_db
│   │   ├── models/            # user.py, record.py, metric.py, system_log.py
│   │   ├── schemas/           # Pydantic：user, auth, record, metric, analytics, admin, common(分頁)
│   │   ├── routers/           # auth, users, records, analytics, metrics, admin, ws
│   │   ├── services/          # record_service, import_service, analytics_service, excel_service, audit_service, admin_service
│   │   ├── realtime/
│   │   │   ├── simulator.py   # 產生指標（隨機漫步 + 尖峰）
│   │   │   ├── manager.py     # ConnectionManager：管理 WebSocket 連線與廣播
│   │   │   └── buffer.py      # MetricBuffer + 批次寫入背景任務
│   │   ├── deps.py            # get_current_user、require_roles(...)
│   │   └── seed.py            # 建立測試帳號與範例資料（可重複執行）
│   ├── alembic/ + alembic.ini # async 範本（alembic init -t async）
│   ├── tests/
│   ├── entrypoint.sh          # alembic upgrade head → python -m app.seed → uvicorn
│   └── Dockerfile
├── frontend/
│   ├── app.py                 # st.navigation：依登入狀態與角色決定頁面；側邊欄使用者與登出
│   ├── views/                 # login.py, monitor.py, records.py, analytics.py, admin.py
│   ├── lib/
│   │   ├── api.py             # requests 包裝：自動帶 token、401 時清除登入狀態
│   │   ├── ws_listener.py     # 背景執行緒接 WebSocket，寫入 deque
│   │   └── charts.py          # Plotly 圖表函式
│   └── Dockerfile
├── sample_data/records.csv     # 約 50 筆，可直接用來測試匯入
├── pixi.toml / pixi.lock      # 前後端共用：features、environments（backend / backend-prod / frontend）、tasks
├── .dockerignore
├── docker-compose.yml
├── .env.example
└── README.md
```

router 只負責 HTTP（解析參數、呼叫 service、回傳），商業邏輯與 ORM 查詢放在 service。這是 FastAPI 社群最常見的分層，容易上手。替代方案「每個功能一個資料夾（feature-based）」在這個規模反而分散，不採用。

前端頁面放 `views/` 而非 Streamlit 慣用的 `pages/`：使用 `st.navigation` 時 `pages/` 會被忽略且容易混淆。

### 2. 資料庫存取：SQLAlchemy 2.1 async ORM + asyncmy

- 版本固定 `sqlalchemy >=2.1,<2.2`（原因見「使用者 id 採用 UUIDv7」的型別說明）。
- async engine 需要 `greenlet`。conda-forge 的 sqlalchemy 不會自動帶入 greenlet，pixi 的 conda 依賴也不支援 `sqlalchemy[asyncio]` 這種 extras 寫法，所以 `pixi.toml` 必須明確列出 `greenlet`。

- `create_async_engine("mysql+asyncmy://...", pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600)`：`pool_pre_ping` 避免 MariaDB 斷掉閒置連線後拿到壞連線。
- `async_sessionmaker(expire_on_commit=False)`；`get_db` 以 `async with` 產生 session 給每個請求。
- 模型使用 2.0 起的宣告式寫法：`Mapped[...]` + `mapped_column(...)`。
- 所有查詢使用 `select()`、`func.count/sum/avg/max/min`、`session.add/add_all/delete`。**不使用 `text()` 或字串 SQL**。
- 趨勢的時間分桶使用 `func.date_format(recorded_at, '%Y-%m-%d %H:00:00')`：這是透過 ORM 表達式呼叫 MariaDB 函式，不是原生 SQL 字串；替代方案「撈回全部資料在 Python 分桶」對 metrics 的資料量不可行。
- 資料庫狀態的連線池資訊取自 `engine.pool`（`size()`、`checkedout()`、`checkedin()`、`overflow()`），回應時間以計時一次 `select(func.now())` 取得，各表筆數以 `select(func.count()).select_from(Model)` 取得，皆不需原生 SQL。

### 3. Alembic：async 範本，遷移檔手動檢查後提交

以 `alembic init -t async` 建立，`env.py` 從 `app.core.config` 讀連線字串、`target_metadata = Base.metadata`。初始遷移由 `--autogenerate` 產生後人工檢查 ENUM 與索引。後端容器啟動時執行 `alembic upgrade head`，失敗則 `set -e` 讓容器退出。

### 4. 認證：PyJWT + bcrypt，OAuth2 password flow

- 登入端點接受 `OAuth2PasswordRequestForm`（form 格式），Swagger 的 Authorize 按鈕可直接用。
- JWT payload：`{"sub": "<user_id，UUID 字串>", "role": "<role>", "exp": ...}`，HS256，密鑰 `JWT_SECRET_KEY`。
- `get_current_user` 每次請求都到資料庫讀使用者，所以停用帳號或改角色**立即生效**（不信任 token 裡的 role，role 只是給前端參考）。
- 代價是資料庫掛掉時連身分驗證都做不了：全域攔截 SQLAlchemy 的連線錯誤（`OperationalError` / `DBAPIError` 中的斷線類），回 503 `{"detail": "Database unavailable"}`。因此 db-status 端點在資料庫無法連線時也是 503，而不是「200 + connected=false」；前端系統管理頁收到 503 時顯示「資料庫無法連線」。不為單一端點破例信任 token 裡的角色，讓安全規則保持一致。
- `require_roles(*roles)` 是一個回傳 dependency 的函式，例如 `Depends(require_roles(Role.admin, Role.user))`。擁有者檢查（建立者或 Admin）在 service 中進行，因為需要先讀出記錄。
- 直接用 `bcrypt` 套件而非 `passlib`：passlib 已停止維護，搭配新版 bcrypt 會出現警告。
- bcrypt 只處理前 72 bytes，5.x 遇到更長的密碼會拋 `ValueError`。因此註冊 schema 驗證密碼 UTF-8 編碼後不超過 72 bytes（超過回 422）；`verify_password` 遇到超過 72 bytes 的輸入直接回傳 False（登入回 401），任何情況都不會變成 500。

### 5. REST API 設計

所有 API 前綴 `/api/v1`，資源用複數名詞，用 HTTP 方法表達動作，部分更新用 PATCH。

| 方法 | 路徑 | 權限 | 說明 |
|---|---|---|---|
| GET | `/health` | 公開 | 健康檢查（compose healthcheck 用） |
| POST | `/api/v1/auth/register` | 公開 | 註冊，201 |
| POST | `/api/v1/auth/login` | 公開 | 登入（form），回傳 token |
| GET | `/api/v1/users/me` | 登入 | 目前使用者 |
| GET | `/api/v1/records` | 登入 | 列表：`page, page_size, category, min_value, max_value, start, end, q, sort`（如 `-recorded_at`） |
| POST | `/api/v1/records` | Admin/User | 建立，201 |
| GET | `/api/v1/records/categories` | 登入 | 不重複分類清單 |
| GET | `/api/v1/records/{id}` | 登入 | 單筆 |
| PATCH | `/api/v1/records/{id}` | 建立者/Admin | 部分更新 |
| DELETE | `/api/v1/records/{id}` | 建立者/Admin | 刪除，204 |
| POST | `/api/v1/records/import` | Admin/User | multipart 上傳 CSV/JSON，201 `{imported}` 或 422 `{detail: {errors:[{row, field, message}]}}`（外層沿用統一的 `detail` 格式；整個檔案的問題以 row 0 表示） |
| GET | `/api/v1/analytics/summary` | 登入 | `source, start, end, category \| metric, server` |
| GET | `/api/v1/analytics/groups` | 登入 | 同上，records 依分類、metrics 依伺服器 |
| GET | `/api/v1/analytics/trend` | 登入 | 同上 + `interval=minute\|hour\|day`（預設 hour）；`bucket` 為區間起點，以 UTC 回傳 |
| GET | `/api/v1/analytics/export` | 登入 | 同上，回傳 .xlsx |
| GET | `/api/v1/metrics` | Admin | 即時資料歷史：`server, metric, start, end, anomaly_only, page, page_size` |
| GET | `/api/v1/admin/users` | Admin | 使用者列表：`role, is_active, q, page, page_size` |
| PATCH | `/api/v1/admin/users/{user_id}` | Admin | `{role?, is_active?}`；`user_id` 為 UUID |
| GET | `/api/v1/admin/logs` | Admin | `level, action, user_id, start, end, page, page_size` |
| GET | `/api/v1/admin/db-status` | Admin | 資料庫狀態 |
| WS | `/ws/metrics?token=<JWT>` | 登入 | 每秒推送 |

- 分析 API 的 `sum`、`avg` 四捨五入到小數 4 位，去掉 DOUBLE 加總的浮點誤差。source=metrics 沒給 `start` 時，查詢 `end`（未給則為現在）之前 24 小時。
- 分頁回應統一：`{"items": [...], "total": 123, "page": 1, "page_size": 20}`。
- 即時資料歷史放在 `/api/v1/metrics`（資源名稱）而不是 `/admin/...`，權限由 dependency 控制；未來若要開放給其他角色只需改權限。
- 錯誤格式沿用 FastAPI 預設 `{"detail": ...}`；422 驗證錯誤用預設格式；全域攔截未處理例外 → 記 logger.exception 與 system_logs（`server_error`），回 500 `{"detail": "Internal server error"}`，不洩漏堆疊。

### 6. 即時資料：單一行程內的三個元件

- **simulator**：每台伺服器每個指標保存「目前值」，每秒加上小幅隨機變動（隨機漫步）並限制在範圍內；另有約 1% 機率產生尖峰（直接拉到閾值以上），讓使用者幾分鐘內就看得到告警。用 `asyncio.sleep(1)` 迴圈。
- **ConnectionManager**：保存已接受的 WebSocket 清單；`broadcast` 同時對所有連線 `send_json`（每個連線最多等 2 秒），失敗或逾時的連線移除，一個卡住的客戶端不會拖慢其他人。
- **MetricBuffer + 批次寫入任務**：`add()` 把資料放進 list，若筆數 ≥ `BATCH_SIZE` 就 `set()` 一個 `asyncio.Event`；寫入任務用 `asyncio.wait_for(event.wait(), timeout=BATCH_INTERVAL_SECONDS)` 等待，醒來（不論 event 或 timeout）先 `event.clear()`；暫存區為空就跳過（不寫入、不更新上次寫入資訊），否則取出全部、`add_all` 後 commit，並記下「上次寫入時間／筆數／原因（interval 或 size）」給資料庫狀態 API。寫入失敗把資料放回最前面（超過 10,000 筆丟最舊的），並在下一次嘗試前固定等滿一個 `BATCH_INTERVAL_SECONDS`，這段期間不因筆數條件提早喚醒，避免資料庫故障時每秒重試；失敗事件照常交給 `audit_service`（資料庫連不上時它只會記到 stdout）。
- 三者都在 FastAPI `lifespan` 中以 `asyncio.create_task` 啟動；關閉時先取消模擬器與寫入任務，再直接執行最後一次 flush，避免與寫入任務同時寫入。
- 預設值說明：每秒 9 筆，10 秒約 90 筆，所以預設下通常是「定期」觸發；把伺服器數調多或 `BATCH_SIZE` 調小就會看到「條件」觸發。兩條路徑都有單元測試（以小數值設定驗證）。

替代方案「模擬器獨立成一個容器，透過 Redis Pub/Sub 推送」可水平擴展，但多一個服務與概念，超出目前單機部署的需求；列為 README 的已知限制與改進方向。

### 7. WebSocket 認證用 query 參數帶 token

`/ws/metrics?token=...`，**先 `accept()` 再驗證**，失敗以 `close(code=1008)` 關閉。依 ASGI 規格，在 `accept()` 前關閉連線時伺服器會以 HTTP 403 拒絕握手，客戶端讀不到 close code；Starlette 的 TestClient 卻會模擬成 1008，測試會通過但實際行為不同。先 accept 才能讓前端確實收到 1008 並執行登出流程。瀏覽器原生 WebSocket 無法自訂 header，query 參數是 FastAPI 官方文件示範的做法，也方便用瀏覽器工具測試。驗證時若資料庫連不上，改以 1011 關閉，前端視為暫時錯誤並重連，不會登出。連線建立後 token 過期不會中斷連線（可接受，記於 Risks）。

Uvicorn 會把 WebSocket 握手連同完整網址（含 query string）寫進日誌，因此在 `uvicorn.error` logger 加上過濾器，把 `token=` 後面的值換成 `***`，token 不會出現在日誌中。

### 8. Streamlit 前端

- **導覽**：`st.navigation` + `st.Page`。未登入只註冊登入頁；登入後依角色組出頁面清單（Admin 多一個系統管理）。
- **Session**：`st.session_state` 存 `token`、`user`（me API 結果）、`ws_listener`。`lib/api.py` 統一加 Authorization header；遇到 401，或 `detail == "Inactive user"` 的 403，就清除 session 並 `st.rerun()` 回登入頁（後端以固定的 detail 字串區分「帳號停用」與「權限不足」）。ws_listener 收到 close code 1008 時停止重連並設一個旗標，即時監控頁看到旗標就執行同樣的登出流程。
- **即時接收**：`websocket-client` 的 `WebSocketApp.run_forever(reconnect=3)` 跑在 daemon 執行緒中，收到訊息就 append 到 `collections.deque(maxlen=60)`（最近 60 秒）與告警 `deque(maxlen=20)`。deque 的 append 是執行緒安全的，執行緒不碰 `st.session_state`（Streamlit 不允許其他執行緒存取 session）。listener 物件存在 session_state，所以切換頁面資料不會消失；登出時呼叫 `close()` 停止。
- **自動刷新**：即時監控頁的圖表區包在 `@st.fragment(run_every=1)` 中，只重繪這一區，不會整頁閃爍。
- **圖表**：Plotly（`st.plotly_chart`），因為內建 `st.line_chart` 無法把異常點標紅、畫閾值線。
- **HTTP**：前端用同步 `requests`（Streamlit 腳本本身是同步的），後端位址取自 `BACKEND_URL=http://backend:8000`；前端是在容器內呼叫後端，不經過瀏覽器，所以**不需要 CORS**。
- **Excel 下載**：前端呼叫匯出 API 取得 bytes，交給 `st.download_button`。

### 9. CSV/JSON 匯入

用標準庫 `csv.DictReader` / `json.loads` 解析，每列丟給 Pydantic `RecordCreate` 驗證，收集所有錯誤（列號以 CSV 資料列從 1 起算，與試算表看到的一致，標頭不算）。全部通過才 `add_all` 並在同一個交易 commit；任一失敗回 422 且不寫入。依副檔名或 content-type 判斷格式，其他格式回 415；超過 5 MB 或 10,000 筆回 413。不引入 pandas，後端相依套件保持精簡。

### 10. Excel 匯出

用 `openpyxl` 建立四個工作表（摘要、分組聚合、趨勢（依小時）、明細），寫入 `BytesIO` 後以 `Response` 回傳，`Content-Disposition` 檔名如 `analytics_records_20261027_1530.xlsx`。查詢重用 analytics service 的函式，確保與畫面數字一致。產生活頁簿是 CPU 工作，以 `asyncio.to_thread` 在執行緒中執行，避免卡住模擬器與 WebSocket 推送。Excel 不支援時區，工作表中的時間一律轉成 `APP_TIMEZONE` 的當地時間，並在摘要工作表註明時區。

### 11. 日誌：兩層

- **Python logging → stdout**：格式 `時間 等級 logger名稱 訊息`；middleware 記錄每個請求的方法、路徑、狀態碼與耗時。用 `docker compose logs backend` 查看。
- **system_logs 資料表**：只記稽核相關事件（見 DB Schema 的事件清單），透過 `audit_service.log(...)` 寫入。它使用**獨立的 session** 並包在 try/except 中，寫入失敗只記到 stdout，不影響原請求（例如登入失敗的請求也需要留下紀錄，不能因主交易 rollback 而消失）。

### 12. Docker

- **多階段 Dockerfile**（`backend/Dockerfile`、`frontend/Dockerfile`）：因為 `pixi.toml` 在根目錄，build context 是專案根目錄（compose 以 `context: .` 加 `dockerfile:` 指定），根目錄的 `.dockerignore` 排除 `.pixi/`、`.git/`、`.env`、`openspec/` 等。`build` 階段使用官方 pixi 映像（`ghcr.io/prefix-dev/pixi`，固定版本），先只複製 `pixi.toml`、`pixi.lock` 再執行 `pixi install --locked -e <環境>`（後端 `backend-prod`、前端 `frontend`），依賴沒變時可沿用快取層；`build` 階段另以 `pixi shell-hook -e <環境> -s bash` 產生環境啟用腳本。`runtime` 階段以 `debian:trixie-slim`（Debian 13）為基底，只把 `.pixi/envs/<環境>` 與各自的程式碼資料夾複製到**相同路徑**（conda 環境內含絕對路徑前綴，換路徑會失效），連同啟用腳本與程式碼一起複製，以非 root 使用者執行。`entrypoint.sh` 先 `source` 啟用腳本再執行指令（pixi 官方 container 做法，讓 `PATH`、`CONDA_PREFIX` 與套件的 activation 設定都生效）；另外把環境的 `bin` 加進映像的 `PATH`，供 compose healthcheck 這類不經 entrypoint 的指令使用。Python 直譯器本身也來自該環境，映像不含 pixi 與編譯器。
- 後端 Dockerfile 另有 `test` 階段：以 `build` 階段為基礎執行 `pixi install --locked -e backend`（含測試套件），供 `backend-test` 服務使用。
- **docker-compose.yml**：
  - `db`：`mariadb:11.7`，volume `db_data:/var/lib/mysql`，對主機開放 `3306` 供本地開發連線，healthcheck 用映像內建 `healthcheck.sh --connect --innodb_initialized`。
  - `backend`：`env_file: .env`，`depends_on: db (service_healthy)`，port 8000，healthcheck 以 `python -c` 呼叫 `/health`（slim 映像沒有 curl）。
  - `frontend`：`env_file: .env`，`depends_on: backend (service_healthy)`，port 8501，healthcheck 以 `python -c` 呼叫 Streamlit 內建的 `/_stcore/health`。
  - Compose 讀取根目錄 `.env` 只用於替換 compose 檔中的 `${...}`，不會自動傳進容器，所以 backend 與 frontend 要以 `env_file` 注入；`db` 以 `environment` 明確列出四個 `MARIADB_*` 變數。
  - `db-test` 與 `backend-test`：放在 `profiles: ["test"]`，平常不啟動；`backend-test` 以後端 Dockerfile 的 `test` target 建置，執行 `pixi run -e backend test`；`db-test` 是另一個 MariaDB 容器（無 volume），讓測試不碰正式資料，也不需要用 SQL 腳本建第二個資料庫。
  - 全部在 `app-net` 網路，服務間以服務名稱互連（`db:3306`、`backend:8000`）。
- **測試指令**：`docker compose --profile test run --rm backend-test`，測試以 `Base.metadata.create_all/drop_all` 建立與清除資料表，並將模擬器設為停用。

### 13. 環境變數（`.env.example`）

| 變數 | 預設 | 用途 |
|---|---|---|
| `MARIADB_ROOT_PASSWORD` | `rootpass` | MariaDB root 密碼 |
| `MARIADB_DATABASE` / `MARIADB_USER` / `MARIADB_PASSWORD` | `analytics` / `app` / `apppass` | 應用程式資料庫與帳號 |
| `DATABASE_URL` | `mysql+asyncmy://app:apppass@db:3306/analytics` | 後端連線字串 |
| `JWT_SECRET_KEY` | `change-me-in-production-at-least-32-bytes` | JWT 簽章密鑰（HS256 建議至少 32 bytes） |
| `JWT_EXPIRE_MINUTES` | `60` | Token 有效期 |
| `SEED_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` / `SEED_VIEWER_PASSWORD` | `Admin@1234` / `User@1234` / `Viewer@1234` | 測試帳號密碼 |
| `SIMULATOR_ENABLED` | `true` | 模擬器開關 |
| `SIMULATOR_SERVERS` | `server-1,server-2,server-3` | 模擬的伺服器 |
| `THRESHOLD_CPU` / `THRESHOLD_MEMORY` / `THRESHOLD_TEMPERATURE` | `90` / `90` / `80` | 異常閾值 |
| `BATCH_INTERVAL_SECONDS` / `BATCH_SIZE` | `10` / `100` | 批次寫入觸發條件 |
| `LOG_LEVEL` | `INFO` | 日誌等級 |
| `BACKEND_URL` / `BACKEND_WS_URL` | `http://backend:8000` / `ws://backend:8000` | 前端呼叫後端的位址 |
| `APP_TIMEZONE` | `Asia/Taipei` | 前端顯示時區；後端解讀無時區輸入與趨勢分桶的時區 |

### 14. 測試帳號與範例資料

`seed.py` 可重複執行：帳號不存在才建立（admin/admin@example.com、user/user@example.com、viewer/viewer@example.com）；`records` 為空才產生約 200 筆範例（分類 `sales`、`traffic`、`inventory`、`temperature`，時間分布於最近 30 天，以固定亂數種子產生，主要由 user 建立、少部分由 admin 建立，方便驗證「只能改自己的」）。`sample_data/records.csv` 是另外約 50 筆、用來測試匯入的檔案。

### 15. 測試策略

pytest + pytest-asyncio + httpx `AsyncClient(transport=ASGITransport(app))`，跑在 `backend-test` 容器對 `db-test`。涵蓋：註冊／登入／token 驗證、三種角色的權限矩陣、records CRUD 與擁有者檢查、分頁篩選排序、匯入成功與全有全無、分析統計數值、Excel 工作表數、Admin 自我保護、MetricBuffer 的兩種觸發與失敗重試（不需 WebSocket 的單元測試）、WebSocket 以無效 token 連線被拒。前端不寫自動化測試，以手動操作清單驗證。

- **Event loop**：pytest-asyncio 的 loop scope 設為 session；測試用 engine 使用 `poolclass=NullPool`，每次都開新連線，避免 asyncmy 連線被不同 event loop 共用（SQLAlchemy 文件「Using multiple asyncio event loops」的建議做法）。
- **WebSocket 測試**：httpx `AsyncClient` 不支援 WebSocket，改用 Starlette `TestClient`。它在另一條執行緒與 event loop 執行 app，這也是測試 engine 要用 NullPool 的原因。
- TestClient 收到的 close code 與真實客戶端可能不同（見決策 7），因此「無效 token 收到 1008」另以真實 uvicorn 加 websocket-client 手動確認一次。

### 16. 套件管理：pixi

- 前後端共用專案根目錄的一份 `pixi.toml` 與 `pixi.lock`，以 feature 與 environment 區分前後端。`pixi.lock` 進版控，`.pixi/` 不進版控。
- channel 只用 `conda-forge`，Python 固定 `3.14.*`。依賴優先寫在 `[dependencies]`（conda-forge）；conda-forge 沒有、或還沒有 Python 3.14 版本的套件，改放 `[pypi-dependencies]` 從 PyPI 安裝。
- 目前已知：asyncmy 在 conda-forge 沒有套件，放 `[pypi-dependencies]`（PyPI 有 cp314 的 Linux／macOS wheel，不需編譯）；sqlalchemy 2.1、greenlet、bcrypt、pydantic、streamlit 等在 conda-forge 都有 Python 3.14 版本。實際結果以第一次產生的 `pixi.lock` 為準。
- `platforms = ["linux-64", "linux-aarch64", "osx-arm64"]`：Docker 內執行 `pixi install --locked` 時，lock 檔必須含容器的平台（一般主機是 linux-64，Apple Silicon 上的 Docker 是 linux-aarch64），只在 macOS 上產生的 lock 會讓容器建置失敗。
- 共用的 `[dependencies]` 只有 `python = "3.14.*"`，其餘依賴分成三個 feature：
  - `backend`：fastapi、uvicorn、sqlalchemy、greenlet、asyncmy、alembic、pydantic-settings、pyjwt、bcrypt、openpyxl 等
  - `frontend`：streamlit、requests、websocket-client、plotly
  - `test`：pytest、pytest-asyncio、httpx
- environments：

  | environment | features | 用途 | solve-group |
  |---|---|---|---|
  | `backend` | backend + test | 本地開發、測試容器 | `backend` |
  | `backend-prod` | backend | 後端 Docker runtime | `backend` |
  | `frontend` | frontend | 本地開發、前端 Docker runtime | `frontend` |
  | `lint` | lint（只有 ruff，不含 Python 預設依賴） | 程式碼檢查與格式化 | — |

  `backend` 與 `backend-prod` 同一個 solve-group，共同套件的版本完全相同。前端使用獨立的 solve-group，前端套件的版本限制不會影響後端。預設環境只含 Python，不直接使用。
- 程式碼風格：ruff，設定在根目錄 `ruff.toml`（`line-length = 80`，lint 規則在預設之外加上 E501 與 import 排序），以 `pixi run lint`、`pixi run format` 執行。ruff 放在獨立的 `lint` 環境，不會進入任何執行用的映像。
- 常用指令定義為各 feature 的 pixi tasks，並設定 `cwd`（後端 task 在 `backend/` 執行，前端在 `frontend/`），一律以 `-e` 指定環境執行，例如 `pixi run -e backend dev`、`pixi run -e frontend dev`。README 與測試容器都使用這些 task。runtime 映像不含 pixi，所以 `entrypoint.sh` 直接執行與 task 相同的指令（`alembic upgrade head`、`python -m app.seed`、`uvicorn`）：
  - 後端（`backend` feature）：`dev`（`uvicorn app.main:app --reload`）、`migrate`（`alembic upgrade head`）、`seed`（`python -m app.seed`）；`test` feature：`test`（`pytest`）
  - 前端（`frontend` feature）：`dev`（`streamlit run app.py`，task 的 `env` 設定 `BACKEND_URL=http://localhost:8000`、`BACKEND_WS_URL=ws://localhost:8000`）
- 本地運行（皆在專案根目錄執行）：`docker compose up -d db` 只啟動資料庫 → `pixi run -e backend migrate`、`pixi run -e backend seed`、`pixi run -e backend dev` → 另開終端機執行 `pixi run -e frontend dev`。第一次執行時 pixi 會自動安裝對應環境。本地執行時 `DATABASE_URL` 要指向 `localhost:3306`，`BACKEND_URL`／`BACKEND_WS_URL` 要指向 `localhost:8000`。
- 本地的環境變數：後端以 pydantic-settings 讀取 `env_file=("../.env", ".env")`，後面的檔案優先。根目錄 `.env` 是 Docker Compose 與本地共用的設定；`backend/.env`（不進版控）只覆寫本地需要不同的值，例如 `DATABASE_URL=mysql+asyncmy://app:apppass@localhost:3306/analytics`。容器內不讀這兩個檔案，由 compose 的 `env_file` 注入。前端只需要後端位址，由 `dev` task 的 `env` 提供。
- 選 pixi 的原因：一份 lock 同時鎖定 Python 直譯器與所有套件，本地與容器一致；asyncmy、bcrypt 等含 C 擴充的套件直接取得預編譯版本（conda-forge 套件或 PyPI wheel），build 階段通常不需要安裝編譯工具。替代方案 pip + `requirements.txt` 沒有完整的鎖定檔，且需另外管理 Python 版本。
- 選單一份 `pixi.toml` 而非前後端各一份：只有一處設定 Python 版本、channel 與 platforms，一次 `pixi install` 就準備好所有環境，一份 lock 涵蓋整個專案。代價是 Docker build context 變成整個專案根目錄，且任一端修改依賴都會改動 `pixi.lock`，讓另一端的依賴快取層也失效重建；以本專案的規模可接受。

## Risks / Trade-offs

- [單一 worker：模擬器與廣播在行程內，無法水平擴展] → 刻意的取捨，README 註明；改進方向是獨立模擬器 + Redis Pub/Sub。
- [Streamlit 每個使用者 session 一條 WebSocket 執行緒，session 意外結束（關分頁）時執行緒可能殘留] → 使用 daemon 執行緒；目前規模可接受，README 註明。
- [Streamlit 重新整理瀏覽器就會登出] → spec 未要求，記為已知限制；比把 token 存在 cookie／query string 安全也簡單。
- [WebSocket 連線後 token 過期仍持續推送] → 推送內容為非敏感的模擬資料，可接受。
- [metrics 每天約 77 萬筆，長時間運作後查詢變慢] → 已建複合索引；分析預設最近 24 小時；Excel 明細上限 10,000 筆；資料清理排程列為非目標。
- [`func.date_format` 綁定 MariaDB/MySQL] → 資料庫已選定 MariaDB，可接受；測試也用 MariaDB 而非 SQLite，避免方言差異。
- [users 主鍵改為 16 bytes 的 UUID，主鍵與外鍵索引比 BIGINT 大] → 使用者數量少，影響可忽略；UUIDv7 時間有序，避免隨機寫入。
- [時間時區混淆] → 統一資料庫存 UTC、API 回 ISO 8601 帶 Z、只在前端轉換。
- [一次開發範圍大，整合問題可能較晚才發現] → tasks 依「可單獨驗證」的順序排列，先完成能跑的骨架與後端核心，前端最後；每組完成都能獨立驗證。
- [Python 3.14 較新，部分套件在 conda-forge 可能缺少、版本落後或尚無 3.14 版本] → 改從 PyPI 安裝（`[pypi-dependencies]`），兩者都記錄在同一份 `pixi.lock`；若某套件在 PyPI 也只有原始碼、需要編譯，只在 `build` 階段加入編譯工具，runtime 映像仍不含。

## Migration Plan

全新系統，無既有資料需遷移。部署步驟：

1. `cp .env.example .env`（可直接使用預設值）
2. `docker compose up -d --build`
3. 後端容器自動執行 `alembic upgrade head` → `python -m app.seed` → 啟動 uvicorn

回滾：`docker compose down`（保留資料）或 `docker compose down -v`（連資料一起清除）。結構變更一律新增 Alembic 遷移檔，不手動改資料庫。
