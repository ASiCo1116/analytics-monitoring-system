# Spec Delta

## Purpose

模擬多台伺服器的 CPU、記憶體與溫度指標，每秒產生一批數值、標記超過閾值的異常，並即時推送給已登入的使用者，同時批次寫入資料庫供後續分析與歷史查詢。

## ADDED Requirements

### Requirement: 每秒產生模擬指標
系統啟用模擬器時 SHALL 每秒為每台設定的伺服器（預設 server-1、server-2、server-3）產生 cpu（%）、memory（%）、temperature（°C）三種指標各一筆，每筆包含伺服器名稱、指標名稱、數值、單位、閾值、是否異常與時間戳。數值 MUST 落在合理範圍（百分比 0–100、溫度 20–110），並以隨機漫步加偶發尖峰的方式變化，使一般情況大多正常但數分鐘內會出現異常。

#### Scenario: 每秒一批
- **WHEN** 系統以預設設定運作 1 秒
- **THEN** 產生 9 筆指標（3 台伺服器 × 3 種指標），時間戳相同

#### Scenario: 模擬器關閉
- **WHEN** 環境變數將模擬器設為停用
- **THEN** 系統不產生任何指標，其他功能照常運作

### Requirement: 閾值異常標記
系統 SHALL 在產生每筆指標時，以該指標的閾值判斷是否異常：數值嚴格大於閾值即標記為異常。閾值由環境變數設定，預設 cpu 90、memory 90、temperature 80。

#### Scenario: 超過閾值
- **WHEN** 產生 cpu 數值 95.2，cpu 閾值為 90
- **THEN** 該筆 is_anomaly=true、threshold=90

#### Scenario: 等於閾值
- **WHEN** 產生 temperature 數值剛好 80.0，閾值為 80
- **THEN** 該筆 is_anomaly=false

### Requirement: WebSocket 即時推送
系統 SHALL 提供 WebSocket 端點，連線時以 query 參數帶入 JWT。驗證通過的連線（任何角色）每秒收到一則 JSON 訊息：`{"type": "metrics", "timestamp": ..., "data": [ ...該秒全部指標... ]}`。Token 無效、過期或使用者已停用時，系統 MUST 先完成 WebSocket 握手，再以 close code 1008 關閉連線，讓客戶端能讀到關閉原因（不以 HTTP 403 拒絕握手）。單一連線斷線 MUST NOT 影響其他連線與資料產生。

#### Scenario: 已登入使用者收到推送
- **WHEN** Viewer 以有效 token 連上 WebSocket 並等待 3 秒
- **THEN** 收到約 3 則訊息，每則 data 含 9 筆指標

#### Scenario: 無效 Token
- **WHEN** 以錯誤 token 連線
- **THEN** 握手成功後連線被以 code 1008 關閉，客戶端收到的關閉代碼為 1008

#### Scenario: 某個客戶端斷線
- **WHEN** 兩個客戶端連線中，其中一個突然斷線
- **THEN** 另一個客戶端仍持續每秒收到資料

### Requirement: 批次寫入資料庫
系統 SHALL 將產生的指標先放入記憶體暫存區，於下列任一條件成立時一次批次寫入資料庫：距上次寫入已達設定秒數（預設 10 秒），或暫存筆數達設定上限（預設 100 筆）。寫入失敗時 MUST 保留暫存資料並記錄錯誤日誌，且至少間隔一個寫入週期（預設 10 秒）才重試；暫存區為空時 MUST NOT 執行寫入；暫存區超過 10,000 筆時 MUST 丟棄最舊的資料並記錄警告。系統正常關閉時 MUST 寫入剩餘暫存資料。

#### Scenario: 定期觸發
- **WHEN** 暫存區有 30 筆，距上次寫入已滿 10 秒
- **THEN** 30 筆被寫入資料庫，暫存區清空

#### Scenario: 條件觸發
- **WHEN** 暫存筆數達 100 筆，距上次寫入未滿 10 秒
- **THEN** 立即寫入 100 筆，不等到 10 秒

#### Scenario: 資料庫暫時無法連線
- **WHEN** 批次寫入時資料庫連線失敗
- **THEN** 暫存資料保留，記錄 ERROR 日誌，10 秒後才重試，期間即使暫存筆數達上限也不提早重試

#### Scenario: 正常關閉
- **WHEN** 後端收到關閉訊號時暫存區還有 25 筆
- **THEN** 25 筆在關閉前寫入資料庫
