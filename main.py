import time
import requests
import hmac
import hashlib
import json
import os
import pandas as pd
import numpy as np
from flask import Flask, render_template_string
from threading import Thread
from collections import deque
from urllib.parse import urlencode
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

# Terminal coloring
try:
    from termcolor import colored
except:
    os.system("pip install termcolor")
    from termcolor import colored

app = Flask(__name__)

# ===== Trade tracking variables =====
total_trades = 0
successful_trades = 0
failed_trades = 0
trade_log = deque(maxlen=20)
compound_profit = 0.0
last_direction = None
# ===================================

# Cooldown period to avoid duplicate signals (10 minutes)
COOLDOWN_PERIOD = 600
last_trade_time = 0

def log_status(title, value, color="white"):
    print(colored(f"{title:<25}: {value}", color))

@app.route('/')
def dashboard():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>DOGE Trading Bot</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {
                --bg-color: #121826;
                --card-bg: #1e293b;
                --text-color: #f8fafc;
                --positive: #10b981;
                --negative: #ef4444;
                --warning: #f59e0b;
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                margin: 0;
                padding: 20px;
                line-height: 1.6;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            .header {
                text-align: center;
                padding: 20px 0;
                border-bottom: 1px solid #334155;
                margin-bottom: 30px;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .card {
                background: var(--card-bg);
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .card-title {
                font-size: 1.2rem;
                font-weight: 600;
                margin-bottom: 15px;
                color: #94a3b8;
                display: flex;
                align-items: center;
            }
            .card-title i {
                margin-right: 10px;
                font-size: 1.4rem;
            }
            .stat-value {
                font-size: 2rem;
                font-weight: 700;
                margin: 10px 0;
            }
            .positive { color: var(--positive); }
            .negative { color: var(--negative); }
            .trade-log {
                max-height: 500px;
                overflow-y: auto;
            }
            .trade-item {
                padding: 12px;
                margin: 8px 0;
                border-radius: 8px;
                background: #2d3748;
                display: grid;
                grid-template-columns: 20px 1fr;
                gap: 12px;
                align-items: center;
            }
            .trade-icon {
                font-size: 1.2rem;
                text-align: center;
            }
            .trade-details {
                display: grid;
                grid-template-columns: 1fr auto;
            }
            .trade-main {
                font-weight: 500;
            }
            .trade-meta {
                font-size: 0.9rem;
                color: #94a3b8;
            }
            .tp { border-left: 4px solid var(--positive); }
            .sl { border-left: 4px solid var(--negative); }
            .status-indicators {
                display: flex;
                justify-content: space-around;
                text-align: center;
                padding: 15px 0;
            }
            .indicator {
                padding: 10px;
            }
            .indicator-value {
                font-size: 1.8rem;
                font-weight: 700;
            }
            .indicator-label {
                font-size: 0.9rem;
                color: #94a3b8;
            }
            @media (max-width: 768px) {
                .grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🪙 DOGE/USDT Trading Bot</h1>
                <p>Automated Trading with Dynamic Risk Management</p>
            </div>
            
            <div class="status-indicators">
                <div class="indicator">
                    <div class="indicator-value">{{ total_trades }}</div>
                    <div class="indicator-label">Total Trades</div>
                </div>
                <div class="indicator">
                    <div class="indicator-value positive">{{ successful_trades }}</div>
                    <div class="indicator-label">Winning Trades</div>
                </div>
                <div class="indicator">
                    <div class="indicator-value negative">{{ failed_trades }}</div>
                    <div class="indicator-label">Losing Trades</div>
                </div>
                <div class="indicator">
                    <div class="indicator-value {% if compound_profit >= 0 %}positive{% else %}negative{% endif %}">
                        {{ compound_profit|round(4) }}
                    </div>
                    <div class="indicator-label">Total Profit (USDT)</div>
                </div>
            </div>
            
            <div class="grid">
                <div class="card">
                    <div class="card-title">📊 Performance Summary</div>
                    <div class="card-content">
                        <p>Current Strategy: Moving Average Crossover</p>
                        <p>Leverage: {{ leverage }}x</p>
                        <p>Risk per Trade: {{ risk_per_trade|round(2) }}%</p>
                        <p>TP: 1.2x ATR | SL: 0.8x ATR</p>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">📈 Market Conditions</div>
                    <div class="card-content">
                        {% if current_price and ema_200 %}
                            <p>Current Price: {{ current_price|round(5) }} USDT</p>
                            <p>EMA 200: {{ ema_200|round(5) }}</p>
                            <p>Position: {{ "Above EMA200" if current_price > ema_200 else "Below EMA200" }}</p>
                            <p>RSI: {{ rsi|round(2) }} - {{ "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral" }}</p>
                            <p>ADX: {{ adx|round(2) }} - {{ "Strong Trend" if adx > 25 else "Weak Trend" }}</p>
                        {% else %}
                            <p>Loading market data...</p>
                        {% endif %}
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">⚙️ Bot Status</div>
                    <div class="card-content">
                        {% if position_open %}
                            <p>🟢 ACTIVE TRADE</p>
                            <p>Position: {{ position_side }} @ {{ position_entry|round(5) }}</p>
                            <p>TP Target: {{ position_tp|round(5) }}</p>
                            <p>SL Target: {{ position_sl|round(5) }}</p>
                            <p>Current PnL: {{ position_pnl|round(4) }} USDT</p>
                        {% else %}
                            <p>🔴 NO ACTIVE POSITION</p>
                            <p>Waiting for trading signals...</p>
                        {% endif %}
                        <p>Last Update: {{ update_time }}</p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">📜 Recent Trades</div>
                <div class="card-content trade-log">
                    {% if trade_log %}
                        {% for trade in trade_log %}
                            <div class="trade-item {{ 'tp' if trade.result == 'TP' else 'sl' }}">
                                <div class="trade-icon">
                                    {{ '🟢' if trade.side == 'BUY' else '🔴' }}
                                </div>
                                <div class="trade-details">
                                    <div class="trade-main">
                                        {{ trade.side }} @ {{ trade.entry_price|round(5) }}
                                        → {{ trade.exit_price|round(5) }}
                                    </div>
                                    <div class="trade-meta {% if trade.profit >= 0 %}positive{% else %}negative{% endif %}">
                                        {{ trade.profit|round(4) }} USDT
                                    </div>
                                    <div class="trade-meta">
                                        {{ trade.result }} | {{ trade.time }}
                                    </div>
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <p>No trades recorded yet</p>
                    {% endif %}
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', 
    symbol=SYMBOL.replace('-', '/'),
    total_trades=total_trades,
    successful_trades=successful_trades,
    failed_trades=failed_trades,
    compound_profit=compound_profit,
    leverage=LEVERAGE,
    risk_per_trade=TRADE_PORTION*100,
    trade_log=trade_log,
    position_open=position_open,
    position_side=position_side,
    position_entry=entry_price,
    position_tp=tp_price,
    position_sl=sl_price,
    position_pnl=current_pnl,
    current_price=current_price,
    ema_200=ema_200_value,
    rsi=rsi_value,
    adx=adx_value,
    update_time=update_time)

def run_flask_app():
    app.run(host="0.0.0.0", port=8080)

def start_dashboard():
    Thread(target=run_flask_app).start()

# ========== Trading Configuration ==========
API_KEY = os.getenv("BINGX_API_KEY")
API_SECRET = os.getenv("BINGX_API_SECRET")
BASE_URL = "https://open-api.bingx.com"

SYMBOL = "DOGE-USDT"
INTERVAL = "15m"
LEVERAGE = 10
TRADE_PORTION = 0.60
ATR_PERIOD = 14
TOLERANCE = 0.0005

# Risk management parameters
MIN_ATR = 0.001
MIN_TP_PERCENT = 0.75
# ===========================================

# Trading state variables
position_open = False
position_side = None
entry_price = 0.0
tp_price = 0.0
sl_price = 0.0
current_quantity = 0.0
current_atr = 0.0
current_pnl = 0.0
current_price = 0.0
ema_200_value = 0.0
rsi_value = 0.0
adx_value = 0.0
update_time = ""

# Compound profit variables
initial_balance = 0.0

def get_signature(params):
    query_string = "&".join([f"{key}={value}" for key, value in params.items()])
    return hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def safe_api_request(method, endpoint, params=None, data=None):
    try:
        url = f"{BASE_URL}{endpoint}"
        headers = {"X-BX-APIKEY": API_KEY}
        timestamp = str(int(time.time() * 1000))
        
        if params is None:
            params = {}
        params["timestamp"] = timestamp
        
        params["signature"] = get_signature(params)
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, params=params, json=data)
        else:
            return None
        
        if response.status_code != 200:
            print(f"❌ API request failed with status {response.status_code}: {response.text}")
            return None
        
        try:
            return response.json()
        except json.JSONDecodeError:
            print(f"❌ Failed to parse JSON response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ API request failed: {e}")
        return None

def get_balance():
    try:
        timestamp = str(int(time.time() * 1000))
        params = {"timestamp": timestamp}
        signature = get_signature(params)
        
        url = f"{BASE_URL}/openApi/swap/v2/user/balance?timestamp={timestamp}&signature={signature}"
        headers = {"X-BX-APIKEY": API_KEY}
        
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if isinstance(result, dict) and "code" in result and result["code"] == 0:
            balance_data = result.get("data", {})
            
            if isinstance(balance_data.get("balance"), list):
                for asset in balance_data["balance"]:
                    if asset.get("asset") == "USDT":
                        return float(asset.get("availableBalance", 0.0))
            
            elif isinstance(balance_data.get("balance"), dict):
                asset = balance_data["balance"]
                if asset.get("asset") == "USDT":
                    return float(asset.get("availableMargin", 0.0))
            
            print("❌ USDT balance not found in response")
        else:
            print(f"❌ Balance request failed: {result.get('msg', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Error fetching balance: {str(e)}")
    return 0.0

def get_open_position():
    try:
        params = {"symbol": SYMBOL}
        response = safe_api_request("GET", "/openApi/swap/v2/user/positions", params)
        
        if response and isinstance(response, dict) and "data" in response:
            for position in response["data"]:
                if (isinstance(position, dict) and 
                    "entryPrice" in position and 
                    "positionAmt" in position and
                    float(position.get("positionAmt", 0)) != 0):
                    
                    return {
                        "side": "BUY" if float(position["positionAmt"]) > 0 else "SELL",
                        "entryPrice": float(position["entryPrice"]),
                        "positionAmt": abs(float(position["positionAmt"])),
                        "unrealizedProfit": float(position.get("unrealizedProfit", 0))
                    }
        return None
    except Exception as e:
        print(f"❌ Error in get_open_position: {e}")
        return None

def get_klines():
    try:
        response = requests.get(
            f"{BASE_URL}/openApi/swap/v2/quote/klines",
            params={"symbol": SYMBOL, "interval": INTERVAL, "limit": 200}
        )
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data:
                df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume"])
                df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
                return df
        return pd.DataFrame()
    except Exception as e:
        print(f"❌ Error fetching klines: {e}")
        return pd.DataFrame()

def calculate_adx(df, period=14):
    try:
        if len(df) < period * 2:
            return pd.Series()
            
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr1 = pd.DataFrame(high - low)
        tr2 = pd.DataFrame(abs(high - close.shift(1)))
        tr3 = pd.DataFrame(abs(low - close.shift(1)))
        frames = [tr1, tr2, tr3]
        tr = pd.concat(frames, axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.ewm(alpha=1/period).mean()
        
        return adx
    except Exception as e:
        print(f"❌ Error calculating ADX: {e}")
        return pd.Series()

def calculate_sma(series, period):
    if len(series) < period:
        return pd.Series()
    return series.rolling(period).mean()

def calculate_ema(series, period):
    if len(series) < period:
        return pd.Series()
    return series.ewm(span=period, adjust=False).mean()

def price_range_percent(df, lookback=20):
    if len(df) < lookback:
        return 0.0
    recent = df["close"].iloc[-lookback:]
    highest = recent.max()
    lowest = recent.min()
    return ((highest - lowest) / lowest) * 100

def calculate_supertrend(df, period=10, multiplier=3):
    try:
        if len(df) < period * 2:
            return pd.Series(), pd.Series()
            
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        hl2 = (high + low) / 2
        atr_indicator = AverageTrueRange(high=high, low=low, close=close, window=period)
        atr = atr_indicator.average_true_range()
        
        if atr.empty:
            return pd.Series(), pd.Series()
            
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        supertrend = pd.Series(np.zeros(len(close)), index=close.index)
        direction = pd.Series(np.ones(len(close)), index=close.index)
        
        for i in range(1, len(close)):
            if close.iloc[i] > upper_band.iloc[i-1]:
                direction.iloc[i] = 1
            elif close.iloc[i] < lower_band.iloc[i-1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i-1]
                
                if direction.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i-1]
                if direction.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i-1]
        
        supertrend = np.where(direction == 1, lower_band, upper_band)
        return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)
    except Exception as e:
        print(f"❌ Error calculating Supertrend: {e}")
        return pd.Series(), pd.Series()

def calculate_tp_sl(entry_price, atr_value, direction):
    if direction == "BUY":
        tp = entry_price + atr_value * 1.2
        sl = entry_price - atr_value * 0.8
    else:
        tp = entry_price - atr_value * 1.2
        sl = entry_price + atr_value * 0.8
    return round(tp, 5), round(sl, 5)

def create_tp_sl_orders():
    global position_open
    
    if not position_open or current_quantity <= 0 or entry_price <= 0:
        print("⚠️ Skipping TP/SL creation — Missing data!")
        return False
    
    # Wait 1 second to ensure order confirmation
    time.sleep(1)
    
    if position_side == "BUY":
        tp_side = "SELL"
        sl_side = "SELL"
    else:
        tp_side = "BUY"
        sl_side = "BUY"
    
    tp_params = {
        "symbol": SYMBOL,
        "side": tp_side,
        "positionSide": "BOTH",
        "type": "TAKE_PROFIT_MARKET",
        "quantity": current_quantity,
        "stopPrice": f"{tp_price:.5f}",
        "workingType": "MARK_PRICE"
    }
    
    sl_params = {
        "symbol": SYMBOL,
        "side": sl_side,
        "positionSide": "BOTH",
        "type": "STOP_MARKET",
        "quantity": current_quantity,
        "stopPrice": f"{sl_price:.5f}",
        "workingType": "MARK_PRICE"
    }
    
    try:
        # Place TP order
        tp_response = safe_api_request("POST", "/openApi/swap/v2/trade/order", params=tp_params)
        if tp_response and tp_response.get("code") == 0:
            print(f"✅ TP order placed @ {tp_price:.5f}")
        else:
            print(f"❌ Failed to place TP order: {tp_response.get('msg') if tp_response else 'Unknown error'}")
            close_position("NO_TP", current_price)
            return False
        
        # Place SL order
        sl_response = safe_api_request("POST", "/openApi/swap/v2/trade/order", params=sl_params)
        if sl_response and sl_response.get("code") == 0:
            print(f"✅ SL order placed @ {sl_price:.5f}")
            return True
        else:
            print(f"❌ Failed to place SL order: {sl_response.get('msg') if sl_response else 'Unknown error'}")
            close_position("NO_SL", current_price)
            return False
    except Exception as e:
        print(f"❌ Error creating TP/SL orders: {e}")
        close_position("ERROR", current_price)
        return False

def place_order(side, quantity):
    global position_open, position_side, entry_price, current_quantity, tp_price, sl_price, last_trade_time
    
    current_time = time.time()
    if current_time - last_trade_time < COOLDOWN_PERIOD:
        remaining = COOLDOWN_PERIOD - (current_time - last_trade_time)
        print(f"⏳ Skipping duplicate signal (cooldown: {int(remaining)}s)")
        return False
    
    if position_open:
        print("🚫 Position already open - skipping new order")
        return False
    
    try:
        atr = max(current_atr, MIN_ATR)
        estimated_entry = current_price
        
        estimated_tp, estimated_sl = calculate_tp_sl(estimated_entry, atr, side)
        
        tp_distance = abs(estimated_tp - estimated_entry)
        if estimated_entry <= 0:
            print("❌ Invalid price for risk calculation")
            return False
            
        tp_percent = (tp_distance / estimated_entry) * 100
        
        if tp_percent < MIN_TP_PERCENT:
            print(f"🚫 TP too small: {tp_percent:.3f}% — skipping trade")
            return False
        
        if adx_value < 20:
            print("🚫 ADX too weak — skipping trade")
            return False
        
        params = {
            "symbol": SYMBOL,
            "side": side,
            "positionSide": "BOTH",
            "type": "MARKET",
            "quantity": quantity
        }
        
        response = safe_api_request("POST", "/openApi/swap/v2/trade/order", params=params)
        
        if response and response.get("code") == 0:
            order_data = response["data"]
            
            if 'avgPrice' in order_data and order_data['avgPrice'] is not None:
                entry_price = float(order_data['avgPrice'])
            else:
                print("⚠️ avgPrice not available. Using current market price")
                entry_price = current_price
                
            position_side = side
            current_quantity = quantity
            position_open = True
            
            tp_price, sl_price = calculate_tp_sl(entry_price, atr, position_side)
            
            last_trade_time = current_time
            
            print(f"\n{'🟢 BUY' if side == 'BUY' else '🔴 SELL'} @ {entry_price:.5f}")
            print(f"🎯 Take Profit: {tp_price:.5f}")
            print(f"🛑 Stop Loss: {sl_price:.5f}")
            print(f"⚙️ Leverage: {LEVERAGE}x | 📏 ATR: {atr:.5f}")
            
            # STRICT PROTECTION: Immediately create TP/SL and close if failed
            if not create_tp_sl_orders():
                print("🛑 Trade aborted - protection orders failed")
                position_open = False  # Reset position status
                return False
            
            return True
        else:
            print(f"❌ Failed to place {side} order: {response.get('msg') if response else 'Unknown error'}")
            return False
    except Exception as e:
        print(f"❌ Error placing order: {e}")
        return False

def close_position(reason, exit_price):
    global position_open, position_side, entry_price, current_quantity, tp_price, sl_price
    global total_trades, successful_trades, failed_trades, compound_profit, last_trade_time
    global last_direction
    
    if not position_open or position_side is None:
        print("⚠️ No open position to close")
        return False
    
    if position_side == "BUY":
        close_side = "SELL"
    else:
        close_side = "BUY"
    
    params = {
        "symbol": SYMBOL,
        "side": close_side,
        "positionSide": "BOTH",
        "type": "MARKET",
        "quantity": current_quantity
    }
    
    try:
        response = safe_api_request("POST", "/openApi/swap/v2/trade/order", params=params)
        
        if response and response.get("code") == 0:
            order_data = response["data"]
            
            if 'avgPrice' in order_data and order_data['avgPrice'] is not None:
                exit_price = float(order_data['avgPrice'])
            else:
                print("⚠️ avgPrice not available. Using current market price")
                exit_price = current_price
            
            if position_side == "BUY":
                profit = (exit_price - entry_price) * current_quantity
                profit_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                profit = (entry_price - exit_price) * current_quantity
                profit_pct = ((entry_price - exit_price) / entry_price) * 100
            
            compound_profit += profit
            total_trades += 1
            
            if reason == "TP":
                successful_trades += 1
            else:
                failed_trades += 1
            
            trade_record = {
                'side': position_side,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'result': reason,
                'profit': profit,
                'time': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            trade_log.appendleft(trade_record)
            
            last_direction = position_side
            
            last_trade_time = time.time()
            
            print(f"\n💼 Closed {position_side} @ {exit_price:.5f} | Entry: {entry_price:.5f}")
            print(f"📈 Profit: {profit:.4f} USDT | 📊 Change: {profit_pct:.2f}%")
            print(f"💰 Total Profit: {compound_profit:.4f} USDT")
            print(f"🔁 Total Trades: {total_trades} | ✅ Wins: {successful_trades} | ❌ Losses: {failed_trades}")
            print(f"🛑 Reason: {reason}")
            print(f"⏳ Cooldown period started (10 minutes)")
            
            position_open = False
            position_side = None
            entry_price = 0.0
            current_quantity = 0.0
            tp_price = 0.0
            sl_price = 0.0
            
            # === FIX: Allow API to update balance ===
            print("🔄 Waiting 10 seconds for balance update...")
            time.sleep(10)
            # ========================================
            
            return True
        else:
            print(f"❌ Failed to close position: {response.get('msg') if response else 'Unknown error'}")
            return False
    except Exception as e:
        print(f"❌ Error closing position: {e}")
        return False

def check_position_status():
    global current_price, current_pnl
    
    if not position_open or position_side is None:
        return
    
    if position_side == "BUY":
        current_pnl = (current_price - entry_price) * current_quantity
    else:
        current_pnl = (entry_price - current_price) * current_quantity
    
    if position_side == "BUY":
        if current_price >= tp_price - TOLERANCE:
            print(f"✅ TP condition met! Price reached {current_price:.5f}")
            close_position("TP", current_price)
        elif current_price <= sl_price + TOLERANCE:
            print(f"🛑 SL condition met! Price dropped to {current_price:.5f}")
            close_position("SL", current_price)
    else:
        if current_price <= tp_price + TOLERANCE:
            print(f"✅ TP condition met! Price dropped to {current_price:.5f}")
            close_position("TP", current_price)
        elif current_price >= sl_price - TOLERANCE:
            print(f"🛑 SL condition met! Price rose to {current_price:.5f}")
            close_position("SL", current_price)

def resume_open_position():
    global position_open, position_side, entry_price, current_quantity, current_atr
    
    try:
        position = get_open_position()
        if position:
            position_side = position["side"]
            entry_price = position["entryPrice"]
            current_quantity = position["positionAmt"]
            position_open = True
            
            atr = max(current_atr, MIN_ATR)
            
            tp_price, sl_price = calculate_tp_sl(entry_price, atr, position_side)
            
            print(f"\n▶️ RESUMING OPEN POSITION ◀️")
            print(f"🔹 Side: {position_side}")
            print(f"🔹 Entry Price: {entry_price:.5f}")
            print(f"🔹 Quantity: {current_quantity}")
            print(f"🎯 Take Profit: {tp_price:.5f}")
            print(f"🛑 Stop Loss: {sl_price:.5f}")
            print(f"📏 Current ATR: {atr:.5f}")
            
            # Apply strict protection for resumed positions
            if not create_tp_sl_orders():
                print("🛑 Failed to set protection for resumed position")
            
            return True
        return False
    except Exception as e:
        print(f"❌ Error resuming position: {e}")
        return False

def main_bot_loop():
    global current_atr, current_price, ema_200_value, rsi_value, adx_value, update_time
    
    print(colored("🚀 Starting DOGE Trading Bot...", "green", attrs=["bold"]))
    print(f"⚙️ Configuration:")
    print(f"  - Symbol: {SYMBOL}")
    print(f"  - Leverage: {LEVERAGE}x")
    print(f"  - Risk per Trade: {TRADE_PORTION*100}%")
    print(f"  - Tolerance: {TOLERANCE}")
    print(f"  - MIN_ATR: {MIN_ATR}")
    print(f"  - MIN_TP_PERCENT: {MIN_TP_PERCENT}%")
    print(f"  - Cooldown Period: {COOLDOWN_PERIOD} seconds")

    initial_balance = get_balance()
    if initial_balance <= 0:
        print("❌ Error: Initial balance is not positive")
        exit(1)

    df = get_klines()
    if not df.empty:
        atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=ATR_PERIOD)
        atr_series = atr_indicator.average_true_range()
        if not atr_series.empty:
            current_atr = atr_series.iloc[-1]
        else:
            current_atr = MIN_ATR

    resume_open_position()

    while True:
        try:
            update_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            sleep_time = 15 if position_open else 60
            
            df = get_klines()
            if df.empty:
                print(colored("❌ Failed to get market data, retrying...", "red"))
                time.sleep(sleep_time)
                continue
                
            if len(df) < 50:
                print(f"⚠️ Insufficient data ({len(df)} candles), waiting...")
                time.sleep(sleep_time)
                continue
                
            close_prices = df["close"]
            current_price = close_prices.iloc[-1]
            
            atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=ATR_PERIOD)
            atr_series = atr_indicator.average_true_range()
            current_atr = atr_series.iloc[-1] if not atr_series.empty else MIN_ATR
            
            rsi_series = RSIIndicator(close=df["close"], window=14).rsi()
            ema_20 = calculate_ema(close_prices, 20)
            ema_50 = calculate_ema(close_prices, 50)
            ema_200 = calculate_ema(close_prices, 200)
            adx_series = calculate_adx(df)
            supertrend_line, supertrend_trend = calculate_supertrend(df)
            price_range = price_range_percent(df)
            
            sma_3 = calculate_sma(close_prices, 3).iloc[-1] if len(close_prices) >= 3 else 0
            sma_5 = calculate_sma(close_prices, 5).iloc[-1] if len(close_prices) >= 5 else 0
            sma_7 = calculate_sma(close_prices, 7).iloc[-1] if len(close_prices) >= 7 else 0
            sma_10 = calculate_sma(close_prices, 10).iloc[-1] if len(close_prices) >= 10 else 0
            sma_14 = calculate_sma(close_prices, 14).iloc[-1] if len(close_prices) >= 14 else 0
            
            rsi_value = rsi_series.iloc[-2] if not rsi_series.empty and len(rsi_series) >= 2 else 0
            ema_200_value = ema_200.iloc[-1] if not ema_200.empty else 0
            adx_value = adx_series.iloc[-1] if not adx_series.empty else 0
            current_supertrend = supertrend_trend.iloc[-1] if not supertrend_trend.empty else 0
            
            # ===== (PRO) استراتيجية مطوّرة — قرار موحّد للشراء/البيع =====
            from strategy_upgrade import StrategyUpgrade, Params as _P, Guard as _G
            strategyX = StrategyUpgrade(_P(), _G())
            state = {
                "price": current_price,
                "atr": current_atr,
                "ema200": ema_200_value,
                "rsi": rsi_value,
                "adx": adx_value,
                "range": price_range,
                "supertrend": 1 if current_supertrend > 0 else -1,
                "sma3": sma_3, "sma5": sma_5, "sma7": sma_7,
                "last_direction": last_direction,
                "mins_since_last_trade": int((time.time() - last_trade_time) / 60),
                "spike": abs(close_prices.iloc[-1] - close_prices.iloc[-2]) > 1.8 * current_atr
            }
            dec = strategyX.decide(state)
            ok_pre, reasons_pre = strategyX.pre_trade({
                **state,
                "prev": close_prices.iloc[-2],
                "pct3": ((close_prices.iloc[-1] - close_prices.iloc[-4]) / close_prices.iloc[-4] * 100) if len(close_prices) >= 4 else 0.0
            }, dec["side"])

            # بدل إشارات التقاطع الأصلية إلى إشارات محسّنة
            ma_cross_up   = dec["enter"] and dec["side"] == "BUY"
            ma_cross_down = dec["enter"] and dec["side"] == "SELL"

            if not ok_pre:
                print(f"[PROTECT][PRE] blocked: {reasons_pre}")
                ma_cross_up = ma_cross_down = False

            # منع الدخول بعد الشموع المفاجئة
            current_close = close_prices.iloc[-1]
            previous_close = close_prices.iloc[-2]
            spike = abs(current_close - previous_close) > current_atr * 1.8
            
            # ===== الحسابات المالية =====
            current_balance = get_balance()
            
            total_balance = initial_balance + compound_profit
            trade_usdt = min(total_balance * TRADE_PORTION, current_balance)
            effective_usdt = trade_usdt * LEVERAGE
            quantity = round(effective_usdt / current_price, 2)
            
            print(f"📊 Effective USD (after leverage): {effective_usdt:.2f} USD")
            print(f"📦 Quantity: {quantity} {SYMBOL.split('-')[0]}")
            
            print("\n" + "="*50)
            print(colored(f"📊 Market Data @ {update_time}", "cyan", attrs=["bold"]))
            
            log_status("💰 Price", f"{current_price:.5f}", "yellow")
            log_status("💵 Balance", f"{current_balance:.2f} USDT", "green")
            log_status("💰 Compound Profit", f"{compound_profit:.4f} USDT", "green")
            log_status("🧮 Trade Size", f"{trade_usdt:.2f} USDT (Leverage {LEVERAGE}x -> {effective_usdt:.2f} USD)", "white")
            log_status("📦 Quantity", f"{quantity} {SYMBOL.split('-')[0]}", "white")
            log_status("📈 RSI", f"{rsi_value:.2f}", "blue")
            log_status("📉 EMA 200", f"{ema_200_value:.5f}", "cyan")
            log_status("📏 ATR", f"{current_atr:.5f}", "magenta")
            log_status("📊 ADX", f"{adx_value:.2f}", "red")
            log_status("📐 Price Range", f"{price_range:.2f}%", "yellow")
            log_status("MA Cross", "UP" if ma_cross_up else "DOWN" if ma_cross_down else "NEUTRAL", "white")
            log_status("🔀 Supertrend", "BULLISH" if current_supertrend > 0 else "BEARISH", 
                     "green" if current_supertrend > 0 else "red")
            log_status("💥 Spike Candle", f"{abs(current_close - previous_close):.5f} > {current_atr*1.8:.5f}" if spike else "No", "red" if spike else "green")
            
            check_position_status()
            
            if not position_open:
                current_time = time.time()
                if current_time - last_trade_time < COOLDOWN_PERIOD:
                    remaining = int(COOLDOWN_PERIOD - (current_time - last_trade_time))
                    print(f"🕒 Cooldown active. Waiting {remaining} seconds before next trade.")
                elif spike:
                    print(f"⛔ Spike candle detected ({abs(current_close - previous_close):.5f} > {current_atr*1.8:.5f}) — skipping trade")
                else:
                    if ma_cross_up and price_range > 1.5:
                        atr_val = max(current_atr, MIN_ATR)
                        estimated_tp, estimated_sl = calculate_tp_sl(current_price, atr_val, "BUY")
                        tp_percent = ((estimated_tp - current_price) / current_price) * 100
                        
                        if tp_percent >= MIN_TP_PERCENT and dec["est_tp_percent"] >= dec["min_tp_percent"]:
                            if last_direction == "BUY":
                                print("🚫 Last trade was also BUY — skipping repeated direction")
                            else:
                                print(colored("\n🚀 PRO SIGNAL BUY", "green", attrs=["bold"]))
                                place_order("BUY", quantity)
                        else:
                            print(f"🚫 TP too small: {tp_percent:.3f}% — skipping trade")
                    
                    elif ma_cross_down and price_range > 1.5:
                        atr_val = max(current_atr, MIN_ATR)
                        estimated_tp, estimated_sl = calculate_tp_sl(current_price, atr_val, "SELL")
                        tp_percent = ((current_price - estimated_tp) / current_price) * 100
                        
                        if tp_percent >= MIN_TP_PERCENT and dec["est_tp_percent"] >= dec["min_tp_percent"]:
                            if last_direction == "SELL":
                                print("🚫 Last trade was also SELL — skipping repeated direction")
                            else:
                                print(colored("\n🚀 PRO SIGNAL SELL", "red", attrs=["bold"]))
                                place_order("SELL", quantity)
                        else:
                            print(f"🚫 TP too small: {tp_percent:.3f}% — skipping trade")
                    
                    elif (ma_cross_up or ma_cross_down) and price_range <= 1.5:
                        print(f"🚫 Price range too low ({price_range:.2f}% < 1.5%) — skipping trade")
            
            time.sleep(sleep_time)
            
        except Exception as e:
            print(colored(f"❌ Unexpected error: {e}", "red"))
            time.sleep(60)

def keep_alive():
    def ping():
        while True:
            try:
                requests.get("https://YOUR-REPLIT-URL.replit.app")
                print("🟢 Keep-alive ping sent")
            except:
                print("🔴 Keep-alive failed")
            time.sleep(300)
    
    t = Thread(target=ping)
    t.daemon = True
    t.start()

keep_alive()

if __name__ == '__main__':
    bot_thread = Thread(target=main_bot_loop)
    bot_thread.daemon = True
    bot_thread.start()
    # Bind PORT for Render
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
