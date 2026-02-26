# Wheel Strategy Plugin for OpenClaw

連接 Interactive Brokers 獲取期權數據，幫助執行 Wheel Strategy。

## 功能

- **股價查詢** - 查詢個股現價
- **期權鏈** - 查詢任一股票的期權鏈（支援 Calls/Puts）
- **Wheel 建議** - 根據 Wheel Strategy 邏輯推薦 CSP/CC
- **持倉查詢** - 查看目前 IB 持倉
- **帳戶資訊** - 現金、槓桿、保證金

## 前置要求

1. **IB Gateway 或 TWS** 必須運行在 本機 (127.0.0.1)
   - Paper Trading: Port 7497
   - Live Trading: Port 7496

2. **安裝依賴**:
```bash
pip install ib_async pandas pytz
```

3. **設定 config.json**:
```json
{
  "host": "127.0.0.1",
  "port": 7497,
  "client_id": 1,
  "readonly": true
}
```

## 使用方式

```
# 查股價
查一下 NVDA 股價

# 期權鏈
看 AAPL 的期權鏈 (PUT 10% OTM)

# Wheel 建議
給我 TSLA 的 wheel 建議

# 持倉
查看持倉

# 帳戶
帳戶狀態
```

## 邏輯說明

### Wheel Strategy 推薦邏輯

**Cash-Secure Put (CSP)**:
- 選擇 10-16% OTM 的 Put
- 目標：收取權利金，願意被assign

**Covered Call (CC)**:
- 需先持有正股
- 選擇 10-30% OTM 的 Call
- 目標：收取權利金，願意賣出

### 數據優先順序

1. 市場開盤 → 即時數據
2. 市場關盤 → Frozen 數據
