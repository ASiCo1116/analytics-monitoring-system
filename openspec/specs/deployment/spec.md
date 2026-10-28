# deployment Specification

## Purpose
讓使用者只需複製環境變數範本並執行一個 Docker Compose 指令，就能啟動完整可用的系統（含資料庫結構、測試帳號與範例資料），且資料在容器重啟後仍保留。

## Requirements

### Requirement: 一鍵啟動
在已安裝 Docker 與 Docker Compose v2 的機器上，複製 `.env.example` 為 `.env` 後執行 `docker compose up -d --build`，系統 SHALL 啟動資料庫、後端、前端三個服務，並在資料庫就緒後才啟動後端、後端健康後才啟動前端。啟動完成後前端可於 `http://localhost:8501`、Swagger 文件可於 `http://localhost:8000/docs` 存取。

#### Scenario: 全新環境啟動
- **WHEN** 在沒有任何既有 volume 的機器上執行啟動指令
- **THEN** 三個服務皆為 running/healthy，前端登入頁與 Swagger 頁皆可開啟

### Requirement: 自動資料庫遷移
後端啟動時 SHALL 先將資料庫遷移至最新版本再開始服務請求。遷移失敗時後端 MUST 結束並輸出錯誤，不以不完整的結構運作。

#### Scenario: 首次啟動建立資料表
- **WHEN** 後端首次啟動
- **THEN** 資料庫中存在 users、records、metrics、system_logs 與遷移版本表

### Requirement: 測試帳號與範例資料
後端啟動時 SHALL 確保三個測試帳號存在（admin、user、viewer，角色分別對應，密碼取自環境變數並記載於 README）；若資料記錄表為空，MUST 建立約 200 筆時間分布於最近 30 天的範例資料記錄。重複啟動 MUST NOT 產生重複帳號或重複範例資料。

#### Scenario: 重複啟動
- **WHEN** 系統第二次啟動
- **THEN** 仍只有一組測試帳號，範例資料不會再增加

### Requirement: 資料持久化
資料庫資料 SHALL 存放於具名 Docker volume。執行 `docker compose down` 再 `up` 後，先前資料 MUST 仍存在；只有 `docker compose down -v` 才會清除。

#### Scenario: 重啟後資料保留
- **WHEN** 使用者新增一筆記錄後執行 down 與 up
- **THEN** 該筆記錄仍可查到

### Requirement: 環境變數設定
所有可調整的設定（資料庫帳密、JWT 密鑰與有效期、測試帳號密碼、模擬器開關與伺服器清單、各指標閾值、批次寫入秒數與筆數、日誌等級、顯示時區）SHALL 透過環境變數提供，並在 `.env.example` 中列出且附說明與可直接使用的預設值。程式碼與映像中 MUST NOT 寫死密碼或密鑰。

#### Scenario: 調整閾值
- **WHEN** 使用者將 `.env` 中的 CPU 閾值改為 50 並重啟後端
- **THEN** cpu 數值超過 50 即被標記為異常

### Requirement: 專案文件與範例
專案 SHALL 提供 README，至少包含：專案介紹、技術棧、本地運行步驟、Docker 部署指令、API 文件連結、測試帳號資訊，以及以 Mermaid 繪製的系統架構圖。專案 SHALL 提供 `.env.example`，以及至少一個可直接透過匯入功能使用的 CSV 範例檔（`sample_data/records.csv`）。

#### Scenario: 依 README 從零啟動
- **WHEN** 新的開發者在乾淨環境只依照 README 操作
- **THEN** 能以 Docker 啟動系統，並用 README 列出的測試帳號登入

#### Scenario: 匯入範例 CSV
- **WHEN** User 透過匯入功能上傳 `sample_data/records.csv`
- **THEN** 系統回傳 201，所有列皆成功匯入

#### Scenario: 架構圖可閱讀
- **WHEN** 在 GitHub 上檢視 README
- **THEN** 系統架構圖正確顯示

### Requirement: 可重現的開發環境
專案 SHALL 以根目錄的單一 `pixi.toml` 宣告前後端依賴，以 pixi environment 區分前端、後端與測試環境，並將 `pixi.lock` 納入版控。開發者在本地安裝的環境 MUST 與 Docker 映像使用相同版本的 Python 與套件；啟動服務、遷移、建立測試資料、執行測試等常用操作 SHALL 以 pixi tasks 提供。

#### Scenario: 本地啟動後端
- **WHEN** 開發者在已啟動資料庫容器的機器上，於專案根目錄依序執行 `pixi run -e backend migrate`、`pixi run -e backend dev`
- **THEN** 後端在 `http://localhost:8000` 啟動，Swagger 文件可開啟

#### Scenario: 版本一致
- **WHEN** 比較本地 `backend` 環境與後端映像（`backend-prod` 環境）中的 fastapi、sqlalchemy 版本
- **THEN** 兩者版本相同，皆來自同一份 `pixi.lock`

### Requirement: 自動化測試可在容器中執行
專案 SHALL 提供在 Docker 中執行後端測試的指令，測試使用獨立的測試資料庫，MUST NOT 影響正式資料。

#### Scenario: 執行測試
- **WHEN** 使用者執行 README 中的測試指令
- **THEN** 測試在獨立資料庫上執行並輸出結果，正式資料庫內容不變
