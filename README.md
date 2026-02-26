# OpenClaw Wheel Strategy Plugin

連接 Interactive Brokers 獲取期權數據，幫助執行 Wheel Strategy。

## 功能

- **股價查詢** - 查詢個股現價（IB 即時 或 yfinance 備援）
- **期權鏈** - 查詢任一股票的期權鏈（支援 Calls/Puts）
- **Wheel 建議** - 根據 Wheel Strategy 邏輯推薦 CSP/CC
- **持倉查詢** - 查看目前 IB 持倉（含股票與期權）
- **帳戶資訊** - 現金、槓桿、保證金
- **轉倉分析** - 計算轉倉成本與收益
- **下單功能** - 支援市價單與限價單（需關閉 readonly）

## 安裝

```bash
# Clone
git clone https://github.com/mactone/openclaw-wheel.git
cd openclaw-wheel

# 建立虛擬環境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安裝依賴
pip install ib_async pandas pytz yfinance flask
```

## 設定

### config.json

```json
{
  "host": "192.168.0.41",
  "port": 7496,
  "client_id": 1,
  "readonly": false,
  "comment": "TWS IP 和 Port"
}
```

- `host`: TWS 的 IP（用遠端時填內網 IP）
- `port`: API Port（TWS 預設 7496，IB Gateway 預設 4001）
- `client_id`: 固定 client ID（避免重複連線）
- `readonly`: `true` = 唯讀，`false` = 可下單

### TWS 設定

1. 開啟 TWS → Settings → API
2. 勾選 **Enable ActiveX and Socket Clients**
3. 設定 **Socket Port**（預設 7496）
4. 確認帳戶有 API 權限

## 使用範例

### Python Code

```python
from plugin import (
    IBWheel,
    get_price,
    get_options,
    wheel_recommend,
    portfolio_status
)

# 初始化
wheel = IBWheel()

# 查股價
price = wheel.get_stock_price('NVDA')
print(f'NVDA: ${price}')

# Wheel 建議
recommendation = wheel.wheel_recommend('NVDA')
print(recommendation)

# 持倉狀態
status = wheel.portfolio_status()
print(status)

# 查特定標的持倉
portfolio = wheel.get_portfolio()
print(portfolio)

# 下單（市價單）
wheel.place_order(contract, 'BUY', 1, 'MKT')

# 斷開連線
wheel.disconnect()
```

### CLI 使用

```bash
source venv/bin/activate

# 查股價
python -c "from plugin import get_price; print(get_price('NVDA'))"

# Wheel 建議
python -c "from plugin import wheel_recommend; print(wheel_recommend('TSLA'))"

# 持倉
python -c "from plugin import portfolio_status; print(portfolio_status())"
```

### Discord Commands

```
# 查股價
查一下 NVDA 股價

# 看期權鏈
看 AAPL 的期權鏈 PUT 10%

# Wheel 建議
給我 TSLA 的 wheel 建議

# 持倉
查看持倉

# 帳戶
帳戶狀態
```

## 資料來源

| 資料類型 | 主要來源 | 備援來源 |
|---------|---------|---------|
| 股價 | IB (需訂閱) | yfinance |
| 期權報價 | IB (需訂閱) | yfinance |
| 持倉/帳戶 | IB | 無 |

**注意**：IB 即時報價需要 Market Data 訂閱。沒有訂閱時會自動使用 yfinance（延遲 15-20 分鐘）。

## 常見問題

### Q: 訂單狀態一直是 PendingSubmit？
A: 
1. 檢查 TWS API 設定是否有勾選 Enable API
2. 確認市場是否開盤（盤後訂單會排隊）
3. 檢查帳戶是否開通 API 權限

### Q: 一直開新的 client？
A: 確認 `config.json` 裡 `client_id` 是固定值，plugin 會重複使用連線。

### Q: yfinance 資料是舊的？
A: yfinance 資料會延遲 15-20 分鐘，這是正常的。要即時資料需要 IB Market Data 訂閱。

## 檔案結構

```
openclaw-wheel/
├── plugin.py           # 主程式碼
├── README.md           # 本文件
├── config.json         # 設定檔（需自己建立）
├── config.json.example # 設定範例
└── .gitignore
```

## License

MIT
