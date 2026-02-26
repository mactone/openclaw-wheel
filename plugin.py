"""
OpenClaw Wheel Strategy Plugin
連接 Interactive Brokers 獲取期權數據
"""

import asyncio
import json
import logging
import math
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd
from ib_async import IB, Stock, Option, Contract, util

logger = logging.getLogger('openclaw.wheel')

# Config path
CONFIG_PATH = Path(__file__).parent / 'config.json'


class IBWheel:
    """Interactive Brokers Wheel Strategy 助手"""
    
    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        self.config = self._load_config()
        self.ib = IB()
        self._connected = False
        
    def _load_config(self) -> dict:
        """載入配置"""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return {
            'host': '127.0.0.1',
            'port': 7497,
            'client_id': 1,
            'readonly': True
        }
    
    def _ensure_connection(self) -> bool:
        """確保連接"""
        if self._connected and self.ib.isConnected():
            return True
        
        try:
            # 抑制 ib_async logs
            logging.getLogger('ib_async').setLevel(logging.ERROR)
            
            client_id = self.config.get('client_id', 1) + int(time.time() % 1000)
            self.ib.connect(
                self.config['host'],
                self.config['port'],
                clientId=client_id,
                readonly=self.config.get('readonly', True)
            )
            self._connected = self.ib.isConnected()
            return self._connected
        except Exception as e:
            logger.error(f"連接失敗: {e}")
            return False
    
    def disconnect(self):
        """斷開連接"""
        if self._connected:
            self.ib.disconnect()
            self._connected = False
    
    def get_stock_price(self, symbol: str) -> Optional[float]:
        """取得股價 - 先嘗試 IB，失敗則用 yfinance"""
        
        # 嘗試 IB
        if self._ensure_connection():
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
                # 嘗試即時數據
                self.ib.reqMarketDataType(1)
                ticker = self.ib.reqMktData(contract)
                
                for _ in range(10):
                    self.ib.sleep(0.1)
                    if ticker.marketPrice() and not math.isnan(ticker.marketPrice()):
                        price = ticker.marketPrice()
                        self.ib.cancelMktData(contract)
                        return float(price)
                
                # 嘗試 frozen 數據
                self.ib.reqMarketDataType(2)
                ticker = self.ib.reqMktData(contract)
                for _ in range(10):
                    self.ib.sleep(0.1)
                    if ticker.close and not math.isnan(ticker.close):
                        price = ticker.close
                        self.ib.cancelMktData(contract)
                        return float(price)
                
                self.ib.cancelMktData(contract)
            except Exception as e:
                logger.warning(f"IB 取得股價失敗: {e}")
        
        # Fallback: yfinance
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            if price:
                return float(price)
        except Exception as e:
            logger.error(f"yfinance 取得股價失敗: {e}")
        
        return None
    
    def _get_option_chain_yf(self, symbol: str, otm_pct: float = 10, 
                            option_type: str = 'PUT') -> dict:
        """用 yfinance 取得期權鏈"""
        try:
            ticker = yf.Ticker(symbol)
            stock_price = ticker.info.get('currentPrice') or ticker.info.get('regularMarketPrice')
            
            if not stock_price:
                return {'error': '無法取得股價'}
            
            # 計算目標 strike
            if option_type.upper() == 'PUT':
                target_strike = stock_price * (1 - otm_pct / 100)
            else:
                target_strike = stock_price * (1 + otm_pct / 100)
            
            # 四捨五入到最近的整數
            target_strike = round(target_strike)
            
            # 取得期權鏈
            opt_chain = ticker.option_chain()
            
            if option_type.upper() == 'PUT':
                options = opt_chain.puts
            else:
                options = opt_chain.calls
            
            if options is None or options.empty:
                return {'error': '無期權數據'}
            
            # 轉換為 list 並找最近的 strike
            options['strike'] = options['strike'].astype(float)
            options = options.sort_values('strike')
            
            # 找最近的
            closest = options.iloc[(options['strike'] - target_strike).abs().argsort()[:1]]
            
            if closest.empty:
                return {'error': '找不到合適的 strike'}
            
            row = closest.iloc[0]
            
            # 取得價格
            bid = float(row['bid']) if pd.notna(row.get('bid')) and row['bid'] > 0 else 0
            ask = float(row['ask']) if pd.notna(row.get('ask')) and row['ask'] > 0 else 0
            last = float(row['lastPrice']) if pd.notna(row.get('lastPrice')) else 0
            
            # 如果 bid/ask 為 0，用 last
            if bid == 0 and ask == 0 and last > 0:
                mid = last
            elif bid > 0 and ask > 0:
                mid = (bid + ask) / 2
            elif bid > 0:
                mid = bid
            elif ask > 0:
                mid = ask
            else:
                mid = 0
            
            # 取得到期日
            exp = row.get('contractSymbol', '')
            if exp and len(exp) >= 8:
                expiration = exp[-8:]  # 最後 8 個字元是日期
            else:
                expiration = ''
            
            return {
                'symbol': symbol,
                'stock_price': stock_price,
                'expiration': expiration,
                'strike': float(row['strike']),
                'bid': bid,
                'ask': ask,
                'last': last,
                'iv': float(row['impliedVolatility']) if pd.notna(row.get('impliedVolatility')) else 0,
                'delta': float(row['delta']) if pd.notna(row.get('delta')) else 0,
                'theta': float(row['theta']) if pd.notna(row.get('theta')) else 0,
                'gamma': float(row['gamma']) if pd.notna(row.get('gamma')) else 0,
                'vega': float(row['vega']) if pd.notna(row.get('vega')) else 0,
                'premium': mid * 100,  # 每合約 100 股
            }
            
        except Exception as e:
            logger.error(f"yfinance 期權失敗: {e}")
            return {'error': str(e)}

    def get_option_chain(self, symbol: str, otm_pct: float = 10, 
                         option_type: str = 'PUT', expiration: str = None) -> dict:
        """取得期權鏈 - 用 yfinance"""
        
        # 直接用 yfinance（IB 期權權限有問題）
        result = self._get_option_chain_yf(symbol, otm_pct, option_type)
        
        if 'error' not in result:
            return result
        
        # Fallback 失敗，回傳錯誤
        return result
    
    def _get_next_expiration(self, symbol: str) -> Optional[str]:
        """取得下一個到期日"""
        try:
            stock = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(stock)
            chains = self.ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
            
            if not chains:
                return None
            
            chain = chains[0]
            today = datetime.now().strftime('%Y%m%d')
            valid_exps = [e for e in chain.expirations if e >= today]
            
            if valid_exps:
                return sorted(valid_exps)[0]
            return None
        except:
            return None
    
    def _get_option_data(self, symbol: str, expiration: str, right: str, 
                         target_strike: float) -> dict:
        """取得單一期權數據"""
        try:
            stock = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(stock)
            
            # 取得 chain - 嘗試多個 exchange
            chains = self.ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
            if not chains:
                return {}
            
            # 找有最多 strikes 的 chain
            chain = max(chains, key=lambda c: len(c.strikes) if c.strikes else 0)
            
            # 如果沒有 strikes，根據股價產生
            strikes = list(chain.strikes) if chain.strikes else []
            
            if not strikes:
                # 根據股價產生範圍
                price = self.get_stock_price(symbol) or target_strike
                strikes = [price * 0.7, price * 0.8, price * 0.9, price * 0.95, 
                          price, price * 1.05, price * 1.1, price * 1.2, price * 1.3]
            
            # 找最近的 strike
            closest_strike = min(strikes, key=lambda s: abs(s - target_strike))
            
            # 取得正確的 exchange
            exchange = chain.exchange if hasattr(chain, 'exchange') else 'NASDAQOM'
            
            contract = Option(symbol, expiration, closest_strike, right, exchange, 'USD', 100)
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                logger.warning(f"無法 qualify 合約: {contract}")
                return {}
            
            contract = qualified[0]
            ticker = self.ib.reqMktData(contract, '106', False, False)
            
            for _ in range(30):
                self.ib.sleep(0.1)
                if ticker.modelGreeks:
                    break
            
            bid = ticker.bid or 0
            ask = ticker.ask or 0
            last = ticker.last or 0
            
            greeks = ticker.modelGreeks or type('obj', (object,), {
                'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0
            })()
            
            self.ib.cancelMktData(contract)
            
            return {
                'symbol': symbol, 
                'expiration': expiration, 
                'options': [{
                    'strike': contract.strike,
                    'expiration': contract.lastTradeDateOrContractMonth,
                    'option_type': 'CALL' if right == 'C' else 'PUT',
                    'bid': bid,
                    'ask': ask,
                    'last': last,
                    'implied_volatility': ticker.impliedVolatility or 0,
                    'delta': greeks.delta,
                    'gamma': greeks.gamma,
                    'theta': greeks.theta,
                    'vega': greeks.vega
                }]
            }
            
        except Exception as e:
            logger.error(f"取得期權數據失敗: {e}")
            return {}
    
    def get_portfolio(self) -> dict:
        """取得持倉"""
        if not self._ensure_connection():
            return {'error': '無法連接 IB'}
        
        try:
            account_id = self.ib.managedAccounts()[0]
            values = self.ib.accountSummary(account_id)
            
            account = {}
            for v in values:
                if v.tag == 'NetLiquidation':
                    account['net_liquidation'] = float(v.value)
                elif v.tag == 'TotalCashValue':
                    account['cash'] = float(v.value)
                elif v.tag == 'ExcessLiquidity':
                    account['excess_liquidity'] = float(v.value)
                elif v.tag == 'FullInitMarginReq':
                    account['margin'] = float(v.value)
            
            positions = []
            for pos in self.ib.portfolio():
                if isinstance(pos.contract, Stock):
                    positions.append({
                        'symbol': pos.contract.symbol,
                        'shares': pos.position,
                        'avg_cost': pos.averageCost,
                        'market_value': pos.marketValue,
                        'unrealized_pnl': pos.unrealizedPNL
                    })
            
            return {
                'account': account,
                'positions': positions
            }
            
        except Exception as e:
            logger.error(f"取得持倉失敗: {e}")
            return {'error': str(e)}
    
    def wheel_recommendation(self, symbol: str, cash_available: float = None) -> dict:
        """Wheel Strategy 推薦"""
        # 取得股價
        stock_price = self.get_stock_price(symbol)
        if not stock_price:
            return {'error': f'無法取得 {symbol} 股價'}
        
        # 取得持倉
        portfolio = self.get_portfolio()
        has_stock = False
        if 'positions' in portfolio:
            for pos in portfolio['positions']:
                if pos.get('symbol') == symbol and pos.get('shares', 0) > 0:
                    has_stock = True
                    break
        
        # 沒有持股 → 推薦 CSP
        if not has_stock:
            # 計算可以賣幾個 contract
            if cash_available:
                max_contracts = int(cash_available / (stock_price * 100))
            else:
                max_contracts = 1
            
            # 取得 PUT 數據 (10% OTM)
            put_data = self.get_option_chain(symbol, otm_pct=10, option_type='PUT')
            
            if 'error' in put_data:
                return put_data
            
            premium = put_data.get('premium', 0)
            strike = put_data.get('strike', 0)
            
            # 計算回報
            collateral = strike * 100
            return_pct = (premium / collateral * 100) if collateral > 0 else 0
            
            return {
                'action': 'SELL_PUT',
                'symbol': symbol,
                'stock_price': stock_price,
                'strike': strike,
                'premium': round(premium, 2),
                'return_pct': round(return_pct, 2),
                'max_contracts': max_contracts,
                'max_premium': round(premium * max_contracts, 2),
                'description': f'現價 ${stock_price:.2f}，賣出 {strike} Put，收 ${premium:.2f}/合約 ({return_pct:.2f}% 回報)'
            }
        
        # 有持股 → 推薦 CC
        else:
            # 取得 CALL 數據 (10% OTM)
            call_data = self.get_option_chain(symbol, otm_pct=10, option_type='CALL')
            
            if 'error' in call_data:
                return call_data
            
            premium = call_data.get('premium', 0)
            strike = call_data.get('strike', 0)
            
            return_pct = (premium / stock_price * 100) if stock_price > 0 else 0
            
            return {
                'action': 'SELL_CALL',
                'symbol': symbol,
                'stock_price': stock_price,
                'strike': strike,
                'premium': round(premium, 2),
                'return_pct': round(return_pct, 2),
                'description': f'現價 ${stock_price:.2f}，賣出 {strike} Call，收 ${premium:.2f}/合約 ({return_pct:.2f}% 月回報)'
            }


# === OpenClaw Tool Functions ===

def get_price(symbol: str) -> str:
    """查詢股價"""
    wheel = IBWheel()
    price = wheel.get_stock_price(symbol.upper())
    wheel.disconnect()
    
    if price:
        return f"**{symbol.upper()}** 現在價格: **${price:.2f}**"
    return f"無法取得 {symbol} 股價"


def get_options(symbol: str, otm_pct: float = 10, option_type: str = 'PUT') -> str:
    """查詢期權鏈"""
    wheel = IBWheel()
    data = wheel.get_option_chain(symbol.upper(), otm_pct, option_type)
    wheel.disconnect()
    
    if 'error' in data:
        return f"錯誤: {data['error']}"
    
    return (f"**{symbol.upper()}** 期權數據 (OTM {otm_pct}% {option_type}):\n"
            f"• 股價: ${data['stock_price']:.2f}\n"
            f"• Strike: ${data['strike']:.2f}\n"
            f"• Bid: ${data['bid']:.2f} | Ask: ${data['ask']:.2f}\n"
            f"• IV: {data['iv']*100:.1f}%\n"
            f"• Delta: {data['delta']:.3f} | Theta: {data['theta']:.3f}\n"
            f"• 權利金: ${data['premium']:.2f}/合約")


def wheel_recommend(symbol: str) -> str:
    """Wheel Strategy 推薦"""
    wheel = IBWheel()
    data = wheel.wheel_recommendation(symbol.upper())
    wheel.disconnect()
    
    if 'error' in data:
        return f"錯誤: {data['error']}"
    
    return (f"**{symbol.upper()}** Wheel 建議:\n"
            f"• 動作: **{data['action']}**\n"
            f"• {data['description']}")


def portfolio_status() -> str:
    """查看持倉"""
    wheel = IBWheel()
    data = wheel.get_portfolio()
    wheel.disconnect()
    
    if 'error' in data:
        return f"錯誤: {data['error']}"
    
    account = data.get('account', {})
    positions = data.get('positions', [])
    
    lines = [f"**帳戶資訊:**"]
    lines.append(f"• 淨資產: ${account.get('net_liquidation', 0):,.2f}")
    lines.append(f"• 現金: ${account.get('cash', 0):,.2f}")
    lines.append(f"• 保證金: ${account.get('margin', 0):,.2f}")
    
    if positions:
        lines.append(f"\n**持倉 ({len(positions)}檔):**")
        for p in positions:
            lines.append(f"• {p['symbol']}: {p['shares']}股 @ ${p['avg_cost']:.2f} "
                       f"(市值 ${p['market_value']:.2f}, PnL ${p['unrealized_pnl']:.2f})")
    else:
        lines.append(f"\n目前無股票持倉")
    
    return '\n'.join(lines)


# === Main handler for OpenClaw ===
def handle_wheel_command(command: str, args: list) -> str:
    """處理 Wheel 命令"""
    if not args:
        return "請提供股票代碼，例如: wheel NVDA"
    
    symbol = args[0].upper()
    
    if 'price' in command or '股價' in command:
        return get_price(symbol)
    elif 'option' in command or '期權' in command:
        otm = 10
        opt_type = 'PUT'
        
        # 解析參數
        for a in args[1:]:
            if a.isdigit():
                otm = int(a)
            elif a.upper() in ['CALL', 'PUT', 'C', 'P']:
                opt_type = a.upper() if a.upper() in ['CALL', 'PUT'] else ('CALL' if a.upper() == 'C' else 'PUT')
        
        return get_options(symbol, otm, opt_type)
    elif 'wheel' in command:
        return wheel_recommend(symbol)
    elif 'portfolio' in command or '持倉' in command or '帳戶' in command:
        return portfolio_status()
    else:
        return f"未知命令: {command}。可用: price, options, wheel, portfolio"


if __name__ == '__main__':
    # Test
    wheel = IBWheel()
    print("Testing connection...")
    price = wheel.get_stock_price('AAPL')
    print(f"AAPL: ${price}")
    wheel.disconnect()
