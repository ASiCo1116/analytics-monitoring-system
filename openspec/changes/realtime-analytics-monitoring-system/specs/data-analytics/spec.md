# Spec Delta

## Purpose

讓所有已登入使用者針對「資料記錄」或「即時監控資料」做統計、時間範圍查詢、分組聚合與趨勢分析，並可將結果下載為 Excel 檔。

## ADDED Requirements

### Requirement: 分析資料來源與共用篩選
分析功能 SHALL 以 `source` 參數選擇資料來源：`records`（資料記錄）或 `metrics`（即時監控資料）。共用篩選為時間範圍 start/end（依資料時間戳，含起不含訖）。source=records 時可選填 category；source=metrics 時 metric（cpu/memory/temperature）為必填、server 為選填，因為不同指標的單位不可混算。未給時間範圍時，records 不限時間，metrics 預設為最近 24 小時。start 晚於 end 時 MUST 回傳 422。

#### Scenario: metrics 未指定指標
- **WHEN** 使用者以 source=metrics 但未帶 metric 呼叫任一分析 API
- **THEN** 系統回傳 422

#### Scenario: 時間範圍顛倒
- **WHEN** 使用者帶入 start 晚於 end
- **THEN** 系統回傳 422

### Requirement: 統計摘要
系統 SHALL 依篩選條件回傳筆數、總計、平均、最大值、最小值。無符合資料時，筆數為 0，其餘欄位為 null。

#### Scenario: 資料記錄統計
- **WHEN** 符合篩選的資料記錄數值為 10、20、30
- **THEN** 回傳 count=3、sum=60、avg=20、max=30、min=10

#### Scenario: 無資料
- **WHEN** 篩選時間範圍內沒有任何資料
- **THEN** 回傳 count=0，sum/avg/max/min 為 null

### Requirement: 分組聚合
系統 SHALL 依篩選條件將資料分組並回傳每組的筆數、總計、平均、最大值、最小值：source=records 依分類分組，source=metrics 依伺服器分組。結果依組名排序。

#### Scenario: 依分類聚合
- **WHEN** 資料記錄中有 cpu 分類 2 筆、memory 分類 3 筆
- **THEN** 回傳兩組，cpu 組 count=2、memory 組 count=3，各含 sum/avg/max/min

#### Scenario: 依伺服器聚合
- **WHEN** 以 source=metrics、metric=cpu 查詢
- **THEN** 回傳每台伺服器一組的 cpu 統計

### Requirement: 趨勢序列
系統 SHALL 依篩選條件與時間粒度 interval（`minute`、`hour` 或 `day`）回傳依時間排序的序列，每個時間區間含筆數、平均、最大、最小值。區間依系統設定的顯示時區（預設 Asia/Taipei）切分，例如 interval=day 的一天是台灣時間 00:00 到 24:00。沒有資料的區間不出現在結果中。

#### Scenario: 依小時趨勢
- **WHEN** 使用者以 interval=hour 查詢某天的資料記錄
- **THEN** 回傳該天有資料的每個小時一筆，時間遞增

### Requirement: Excel 匯出
所有已登入角色 SHALL 能以與分析相同的篩選條件下載 .xlsx 檔，包含四個工作表：摘要、分組聚合、趨勢（依小時）、明細。明細最多包含最新 10,000 筆，超過時 MUST 在摘要工作表註明已截斷。檔名包含資料來源與下載時間。

#### Scenario: 下載 Excel
- **WHEN** Viewer 以 source=records 呼叫 Excel 匯出 API
- **THEN** 系統回傳 Content-Type 為 xlsx 的檔案，可用 Excel 開啟且有四個工作表

#### Scenario: 明細截斷
- **WHEN** 符合篩選的 metrics 有 50,000 筆
- **THEN** 明細工作表只有最新 10,000 筆，摘要工作表註明「明細已截斷，僅含最新 10,000 筆」，摘要統計仍以 50,000 筆計算
