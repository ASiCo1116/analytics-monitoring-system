# Analytics Monitoring System

即時資料分析與監控系統：FastAPI 後端、Streamlit 前端、MariaDB 資料庫，以 Docker Compose 一鍵啟動。

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 | FastAPI、Pydantic v2、SQLAlchemy 2.1 async ORM（asyncmy driver）、Alembic、PyJWT + bcrypt、Uvicorn |
| 前端 | Streamlit、Plotly、requests、websocket-client |
| 資料庫 | MariaDB 11.7 |
| 套件與環境 | [pixi](https://pixi.sh)（conda-forge 優先，缺少的從 PyPI），Python 3.14 |
| 部署 | Docker 多階段建置、Docker Compose |
| 測試 | pytest、pytest-asyncio、httpx |

專案根目錄只有一份 `pixi.toml` / `pixi.lock`，以 environment 區分用途：

| environment | 內容 | 用途 |
|---|---|---|
| `backend` | 後端 + 測試套件 | 本地開發、測試容器 |
| `backend-prod` | 後端 | 後端 Docker 映像 |
| `frontend` | 前端 | 本地開發、前端 Docker 映像 |

## Docker 部署

需求：Docker 與 Docker Compose v2。

```bash
cp .env.example .env          # 預設值可直接使用
docker compose up -d --build
```

| 服務 | 位址 |
|---|---|
| 前端 | http://localhost:8501 |
| 後端 API | http://localhost:8000 |
| Swagger 文件 | http://localhost:8000/docs |

常用指令：

```bash
docker compose ps              # 查看服務狀態（三個服務都應為 healthy）
docker compose logs -f backend # 查看後端日誌
docker compose down            # 停止，保留資料
docker compose down -v         # 停止並清除資料庫資料
```

## 執行測試

後端測試在 Docker 中執行，使用獨立的 `db-test` 資料庫（資料只存在記憶體），不會影響正式資料：

```bash
cp .env.example .env    # 若尚未建立
docker compose --profile test run --rm --build backend-test
```

- `--build` 會把最新的程式碼建進測試映像；`db-test` 會自動啟動，測試結束後可用 `docker compose stop db-test` 只關閉測試資料庫，不影響主系統。
- 測試資料庫名稱必須以 `_test` 結尾，否則測試會拒絕執行，避免誤刪開發或正式資料。

## 本地運行

需求：[pixi](https://pixi.sh/latest/#installation) 與 Docker（只用來跑資料庫）。以下指令都在專案根目錄執行，第一次執行時 pixi 會自動安裝對應的環境。

1. 準備環境變數。本地執行時後端要連 `localhost` 的資料庫，用 `backend/.env` 覆寫連線字串（`backend/.env` 不進版控）：

   ```bash
   cp .env.example .env
   echo 'DATABASE_URL=mysql+asyncmy://app:apppass@localhost:3306/analytics' > backend/.env
   ```

2. 只啟動資料庫容器：

   ```bash
   docker compose up -d db
   ```

3. 建立資料表並啟動後端（http://localhost:8000/docs）：

   ```bash
   pixi run -e backend migrate
   pixi run -e backend dev
   ```

4. 另開一個終端機啟動前端（http://localhost:8501）。前端的 `dev` task 已把後端位址設為 `localhost:8000`：

   ```bash
   pixi run -e frontend dev
   ```
