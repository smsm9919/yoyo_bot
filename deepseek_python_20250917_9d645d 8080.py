# ========== إعدادات الاستراتيجية الجديدة ==========
RSI_TREND_LONG = (45, 65)
RSI_TREND_SHORT = (35, 55)
ADX_MIN_TREND = 15
ADX_FLAT_EXIT = 12
BREAKOUT_LOOKBACK = 20
ATR_PCT_RANGE = (0.004, 0.05)
EXPLOSION_ATR_MOVE = 2.2
EXPLOSION_RANGE_MOVE = 2.5
EXPLOSION_ATR_PCT_BOOST = 1.5
ANTI_REENTRY_MIN_ATR = 0.25
SPIKE_BLOCK_ATR = 1.8
SL_MULT = 1.6
TP1_MULT = 1.0
TP2_MULT = 2.0
TRAIL_MULT = 1.0
COOLDOWN_WIN_BARS = 3
COOLDOWN_LOSS_BARS = 5
COOLDOWN_EXPLOSION_BARS = 10
MIN_ADX_NO_TRADE = 12

# متغيرات جديدة للاستراتيجية
last_loss_direction = None
loss_lock_count = 0
tp1_hit = False
tp2_hit = False
trailing_active = False
daily_trade_count = 0
last_trade_day = None
explosion_detected = False
explosion_cooldown = 0
explosion_direction = None

def calculate_bollinger_bands(df, period=20, std_dev=2):
    """حساب Bollinger Bands"""
    if len(df) < period:
        return pd.Series(), pd.Series(), pd.Series()
    
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    return upper_band, sma, lower_band

def check_explosion_condition(df, current_atr):
    """الكشف عن حالات الانفجار/الانهيار"""
    global explosion_detected, explosion_direction
    
    if len(df) < 2:
        return False, None
    
    # حساب ATR% للشمعة الحالية
    current_atr_pct = current_atr / df['close'].iloc[-1]
    
    # حساب متوسط ATR% لآخر 20 شمعة
    if len(df) >= 20:
        atr_values = []
        for i in range(-20, 0):
            if i + len(df) >= 0:
                atr_val = AverageTrueRange(
                    high=df['high'].iloc[i-14:i+1] if i-14 >= 0 else df['high'].iloc[:i+1],
                    low=df['low'].iloc[i-14:i+1] if i-14 >= 0 else df['low'].iloc[:i+1],
                    close=df['close'].iloc[i-14:i+1] if i-14 >= 0 else df['close'].iloc[:i+1],
                    window=14
                ).average_true_range().iloc[-1] if i+1 >= 14 else current_atr
                atr_pct = atr_val / df['close'].iloc[i]
                atr_values.append(atr_pct)
        
        avg_atr_pct = sum(atr_values) / len(atr_values) if atr_values else current_atr_pct
    else:
        avg_atr_pct = current_atr_pct
    
    # شروط الانفجار/الانهيار
    price_move = abs(df['close'].iloc[-1] - df['close'].iloc[-2])
    range_move = df['high'].iloc[-1] - df['low'].iloc[-1]
    
    explosion_condition = (
        price_move >= EXPLOSION_ATR_MOVE * current_atr or
        range_move >= EXPLOSION_RANGE_MOVE * current_atr or
        current_atr_pct >= EXPLOSION_ATR_PCT_BOOST * avg_atr_pct
    )
    
    if explosion_condition:
        explosion_detected = True
        explosion_direction = "UP" if df['close'].iloc[-1] > df['close'].iloc[-2] else "DOWN"
        return True, explosion_direction
    
    explosion_detected = False
    explosion_direction = None
    return False, None

def check_strategy_conditions(df, current_price, rsi_value, adx_value, ema_50, ema_200, supertrend_trend):
    """فحص شروط الاستراتيجية الجديدة"""
    global last_loss_direction, loss_lock_count, explosion_detected, explosion_direction
    global explosion_cooldown, daily_trade_count, last_trade_day
    
    # تحديث عداد الصفقات اليومية
    current_day = time.strftime("%Y-%m-%d")
    if last_trade_day != current_day:
        daily_trade_count = 0
        last_trade_day = current_day
    
    # فحص Direction-Lock بعد الخسارة
    if last_loss_direction and loss_lock_count > 0:
        loss_lock_count -= 1
        if loss_lock_count == 0:
            last_loss_direction = None
    
    # فحص انتهاء cooldown الانفجار
    if explosion_cooldown > 0:
        explosion_cooldown -= 1
    
    # تحديد النظام (Regime)
    trending_up = ema_50 > ema_200 and adx_value >= ADX_MIN_TREND
    trending_down = ema_50 < ema_200 and adx_value >= ADX_MIN_TREND
    ranging = adx_value < ADX_MIN_TREND
    
    # حساب Bollinger Bands للنظام Ranging
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df)
    
    # فحص RSI الانعكاس
    rsi_prev = RSIIndicator(close=df["close"], window=14).rsi().iloc[-2] if len(df) >= 2 else rsi_value
    rsi_turning_up = rsi_value > rsi_prev and rsi_prev < 40
    rsi_turning_down = rsi_value < rsi_prev and rsi_prev > 60
    
    # فحص Breakout
    lookback_high = df['high'].rolling(window=BREAKOUT_LOOKBACK).max().iloc[-1]
    lookback_low = df['low'].rolling(window=BREAKOUT_LOOKBACK).min().iloc[-1]
    
    breakout_long = current_price >= lookback_high and rsi_value < 72
    breakout_short = current_price <= lookback_low and rsi_value > 28
    
    # فحص شروط الدخول
    long_signal, short_signal = False, False
    signal_reason = ""
    
    # Trending Long
    if trending_up and current_price > supertrend_trend and RSI_TREND_LONG[0] <= rsi_value <= RSI_TREND_LONG[1] and rsi_value > rsi_prev:
        if not last_loss_direction == "BUY" and not (explosion_detected and explosion_direction == "DOWN"):
            long_signal = True
            signal_reason = "Trending Long"
    
    # Trending Short
    elif trending_down and current_price < supertrend_trend and RSI_TREND_SHORT[0] <= rsi_value <= RSI_TREND_SHORT[1] and rsi_value < rsi_prev:
        if not last_loss_direction == "SELL" and not (explosion_detected and explosion_direction == "UP"):
            short_signal = True
            signal_reason = "Trending Short"
    
    # Ranging Long (Mean Reversion)
    elif ranging and bb_lower.iloc[-1] and current_price <= bb_lower.iloc[-1] and rsi_turning_up and rsi_value < 40:
        if not last_loss_direction == "BUY" and not explosion_detected:
            long_signal = True
            signal_reason = "Ranging Long"
    
    # Ranging Short (Mean Reversion)
    elif ranging and bb_upper.iloc[-1] and current_price >= bb_upper.iloc[-1] and rsi_turning_down and rsi_value > 60:
        if not last_loss_direction == "SELL" and not explosion_detected:
            short_signal = True
            signal_reason = "Ranging Short"
    
    # Breakout Long
    elif breakout_long and (not trending_down or adx_value < ADX_MIN_TREND):
        if not last_loss_direction == "BUY" and not (explosion_detected and explosion_direction == "DOWN"):
            long_signal = True
            signal_reason = "Breakout Long"
    
    # Breakout Short
    elif breakout_short and (not trending_up or adx_value < ADX_MIN_TREND):
        if not last_loss_direction == "SELL" and not (explosion_detected and explosion_direction == "UP"):
            short_signal = True
            signal_reason = "Breakout Short"
    
    # فلترة إضافية - تجنب الدخول أثناء الانفجار/الانهيار
    if explosion_detected and explosion_cooldown == 0:
        # السماح فقط بالدخول في اتجاه الانفجار بعد شمعة تأكيد
        if long_signal and explosion_direction == "DOWN":
            long_signal = False
            signal_reason = "Explosion Filter - Opposite Direction"
        elif short_signal and explosion_direction == "UP":
            short_signal = False
            signal_reason = "Explosion Filter - Opposite Direction"
        
        # اشترط شمعة تأكيد للدخول في اتجاه الانفجار
        if long_signal and explosion_direction == "UP" and df['close'].iloc[-1] < df['open'].iloc[-1]:
            long_signal = False
            signal_reason = "Explosion Filter - Need Confirmation Candle"
        elif short_signal and explosion_direction == "DOWN" and df['close'].iloc[-1] > df['open'].iloc[-1]:
            short_signal = False
            signal_reason = "Explosion Filter - Need Confirmation Candle"
    
    # منع إعادة الدخول على نفس الشمعة أو قريبة جداً
    if position_open and (long_signal or short_signal):
        if abs(current_price - entry_price) < ANTI_REENTRY_MIN_ATR * current_atr:
            long_signal, short_signal = False, False
            signal_reason = "Anti-Reentry Filter"
    
    # منع الدخول إذا كان التذبذب خارج النطاق المطلوب
    atr_pct = current_atr / current_price
    if atr_pct < ATR_PCT_RANGE[0] or atr_pct > ATR_PCT_RANGE[1]:
        long_signal, short_signal = False, False
        signal_reason = f"ATR% Filter: {atr_pct:.4f}"
    
    # منع الدخول إذا ADX ضعيف جداً (لا يوجد اتجاه ولا تذبذب)
    if adx_value < MIN_ADX_NO_TRADE:
        long_signal, short_signal = False, False
        signal_reason = f"ADX Too Weak: {adx_value:.2f}"
    
    return long_signal, short_signal, signal_reason

def update_tp_sl():
    """تحديث مستويات TP وSL مع التريلينغ"""
    global tp_price, sl_price, tp1_hit, tp2_hit, trailing_active
    
    if not position_open:
        return
    
    if position_side == "BUY":
        # TP1: Move SL to Break-Even
        if not tp1_hit and current_price >= entry_price + TP1_MULT * current_atr:
            tp1_hit = True
            sl_price = entry_price  # Break-even
            print(f"✅ TP1 Hit - SL moved to break-even: {sl_price:.5f}")
        
        # TP2: Activate Trailing Stop
        if not tp2_hit and current_price >= entry_price + TP2_MULT * current_atr:
            tp2_hit = True
            trailing_active = True
            print(f"✅ TP2 Hit - Trailing stop activated")
        
        # Update Trailing Stop
        if trailing_active:
            new_sl = current_price - TRAIL_MULT * current_atr
            if new_sl > sl_price:
                sl_price = new_sl
                print(f"🔺 Trailing SL updated: {sl_price:.5f}")
    
    else:  # SELL position
        # TP1: Move SL to Break-Even
        if not tp1_hit and current_price <= entry_price - TP1_MULT * current_atr:
            tp1_hit = True
            sl_price = entry_price  # Break-even
            print(f"✅ TP1 Hit - SL moved to break-even: {sl_price:.5f}")
        
        # TP2: Activate Trailing Stop
        if not tp2_hit and current_price <= entry_price - TP2_MULT * current_atr:
            tp2_hit = True
            trailing_active = True
            print(f"✅ TP2 Hit - Trailing stop activated")
        
        # Update Trailing Stop
        if trailing_active:
            new_sl = current_price + TRAIL_MULT * current_atr
            if new_sl < sl_price:
                sl_price = new_sl
                print(f"🔻 Trailing SL updated: {sl_price:.5f}")

def check_early_exit():
    """الخروج المبكر عند تشبع RSI مع ضعف الاتجاه"""
    global current_quantity
    
    if not position_open or current_quantity <= 0:
        return False
    
    # Long exit conditions
    if position_side == "BUY" and rsi_value > 78 and adx_value < ADX_FLAT_EXIT:
        # Close 50% of position
        close_qty = round(current_quantity * 0.5, 2)
        if close_qty > 0:
            print(f"⚠️ Early Exit - Closing 50% due to RSI overbought: {rsi_value:.2f}")
            # نستخدم دالة close_position مع كمية جزئية
            partial_close(close_qty, "RSI_OVERBOUGHT")
            return True
    
    # Short exit conditions
    elif position_side == "SELL" and rsi_value < 22 and adx_value < ADX_FLAT_EXIT:
        # Close 50% of position
        close_qty = round(current_quantity * 0.5, 2)
        if close_qty > 0:
            print(f"⚠️ Early Exit - Closing 50% due to RSI oversold: {rsi_value:.2f}")
            partial_close(close_qty, "RSI_OVERSOLD")
            return True
    
    return False

def partial_close(quantity, reason):
    """إغلاق جزئي لل中心位置"""
    global current_quantity, compound_profit
    
    if not position_open or quantity <= 0 or quantity > current_quantity:
        return False
    
    close_side = "SELL" if position_side == "BUY" else "BUY"
    
    params = {
        "symbol": SYMBOL,
        "side": close_side,
        "positionSide": "BOTH",
        "type": "MARKET",
        "quantity": quantity
    }
    
    try:
        response = safe_api_request("POST", "/openApi/swap/v2/trade/order", params=params)
        
        if response and response.get("code") == 0:
            order_data = response["data"]
            exit_price = float(order_data['avgPrice']) if 'avgPrice' in order_data and order_data['avgPrice'] is not None else current_price
            
            # حساب الربح الجزئي
            if position_side == "BUY":
                profit = (exit_price - entry_price) * quantity
            else:
                profit = (entry_price - exit_price) * quantity
            
            compound_profit += profit
            current_quantity -= quantity
            
            print(f"✅ Partial Close: {quantity} {SYMBOL.split('-')[0]} @ {exit_price:.5f}")
            print(f"📈 Partial Profit: {profit:.4f} USDT | Total Profit: {compound_profit:.4f} USDT")
            
            # تسجيل في السجل
            trade_record = {
                'side': position_side,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'result': reason,
                'profit': profit,
                'time': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            trade_log.appendleft(trade_record)
            
            return True
        else:
            print(f"❌ Failed to partial close: {response.get('msg') if response else 'Unknown error'}")
            return False
    except Exception as e:
        print(f"❌ Error in partial close: {e}")
        return False

# في دالة main_bot_loop، نستبدل منطق الدخول القديم بالجديد:
# نضيف هذا الكود بعد حساب المؤشرات وقبل فحص إشارات الدخول

# الكشف عن الانفجار/الانهيار
is_explosion, explosion_dir = check_explosion_condition(df, current_atr)
if is_explosion:
    print(f"⚠️ Explosion/Collapse detected: {explosion_dir}")

# فحص شروط الاستراتيجية الجديدة
long_signal, short_signal, signal_reason = check_strategy_conditions(
    df, current_price, rsi_value, adx_value, 
    ema_50.iloc[-1] if not ema_50.empty else 0,
    ema_200.iloc[-1] if not ema_200.empty else 0,
    supertrend_trend.iloc[-1] if not supertrend_trend.empty else 0
)

# تحديث TP/SL مع التريلينغ
update_tp_sl()

# فحص الخروج المبكر
check_early_exit()

# فحص إشارات الدخول مع المرشحات الجديدة
if not position_open:
    current_time = time.time()
    
    # تحقق من cooldown
    bars_since_last_trade = int((current_time - last_trade_time) / (15 * 60))  # افتراض أن الشمعة 15 دقيقة
    
    if current_time - last_trade_time < current_cooldown_seconds:
        remaining = int(current_cooldown_seconds - (current_time - last_trade_time))
        print(f"⏳ Cooldown active. Waiting {remaining} seconds before next trade.")
    
    # فلترة سبايك الشمعة
    elif abs(current_close - previous_close) > SPIKE_BLOCK_ATR * current_atr:
        print(f"⛔ Spike candle detected ({abs(current_close - previous_close):.5f} > {SPIKE_BLOCK_ATR * current_atr:.5f}) — skipping trade")
    
    # فحص إشارة Long
    elif long_signal and price_range > 1.5:
        print(f"🚀 {signal_reason} SIGNAL - RSI: {rsi_value:.2f}, ADX: {adx_value:.2f}")
        place_order("BUY", quantity)
    
    # فحص إشارة Short
    elif short_signal and price_range > 1.5:
        print(f"🚀 {signal_reason} SIGNAL - RSI: {rsi_value:.2f}, ADX: {adx_value:.2f}")
        place_order("SELL", quantity)
    
    elif (long_signal or short_signal) and price_range <= 1.5:
        print(f"🚫 Price range too low ({price_range:.2f}% < 1.5%) — skipping trade")
    
    elif long_signal or short_signal:
        print(f"🚫 Signal filtered: {signal_reason}")

# في دالة close_position، نضيف تحديثًا لـ last_loss_direction و loss_lock_count
# نضيف هذا الكود بعد إغلاق المركز:

if reason != "TP":  # إذا كانت خسارة
    last_loss_direction = position_side
    loss_lock_count = 8  # قفل لمدة 8 شموع
    
if explosion_detected:
    explosion_cooldown = COOLDOWN_EXPLOSION_BARS

# إعادة تعيين حالة التريلينغ عند فتح صفقة جديدة
# في دالة place_order، نضيف هذا الكود بعد فتح الصفقة:
tp1_hit = False
tp2_hit = False
trailing_active = False

# زيادة عداد الصفقات اليومية
daily_trade_count += 1