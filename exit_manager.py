from volume import get_average_volume
from symbol_info import get_precision, round_qty
from activity_logger import write_log
from logger import log
import asyncio

def calculate_quantity(symbol, raw_qty, min_qty=0.001):
    """
    Calculates and rounds the order quantity according to symbol precision rules.
    """
    if raw_qty <= 0:
        return 0
    precision = get_precision(symbol)
    rounded_qty = round(raw_qty, precision)
    if rounded_qty < min_qty:
        return 0
    return rounded_qty

def calculate_trailing_stop(symbol, entry_price, current_price, direction="long", trigger_pct=0.01, trail_pct=0.005):
    """
    Calculates new SL price using trailing logic once trigger threshold is passed.
    Applies correct rounding precision per symbol.
    """
    precision = get_precision(symbol)

    # For long positions
    if direction.lower() == "long":
        # Check if price has moved up enough to trigger trailing
        if current_price > entry_price * (1 + trigger_pct):
            # Calculate trailing stop below current price
            new_sl = round(current_price * (1 - trail_pct), precision)
            write_log(f"🔐 Trailing SL calc for {symbol} (long): new SL = {new_sl}")
            return new_sl
    # For short positions
    elif direction.lower() == "short":
        # Check if price has moved down enough to trigger trailing
        if current_price < entry_price * (1 - trigger_pct):
            # Calculate trailing stop above current price
            new_sl = round(current_price * (1 + trail_pct), precision)
            write_log(f"🔐 Trailing SL calc for {symbol} (short): new SL = {new_sl}")
            return new_sl

    # Return None if trailing should not be activated yet
    return None

def should_trail_stop(symbol, entry_price, current_price, direction="long", candles=None, trigger_pct=0.018, trail_pct=0.009, current_trailing_sl=None):
    """
    Checks if trailing stop should activate:
      - price exceeds trigger threshold
      - volume is at least 1.2x average (optional)
      - SL must improve (never downgrade)
    """
    # Check if we have enough volume to justify trailing
    if candles:
        avg_volume = get_average_volume(candles)
        current_volume = float(candles[-1]['volume'])
        if current_volume < avg_volume * 1.2:
            write_log(f"🔕 Volume too low for trailing: {current_volume:.2f} < 1.2x avg {avg_volume:.2f}")
            return None

    # Calculate potential new SL value
    new_sl = calculate_trailing_stop(symbol, entry_price, current_price, direction, trigger_pct, trail_pct)
    if not new_sl:
        return None

    # Only update SL if it's better (tighter) than current
    if current_trailing_sl:
        if direction.lower() == "long" and new_sl <= current_trailing_sl:
            return None
        if direction.lower() == "short" and new_sl >= current_trailing_sl:
            return None

    return new_sl

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending"):
    """
    Calculates optimal SL/TP levels based on multiple factors:
    - Trade type (Scalp/Intraday/Swing)
    - Market regime (trending/volatile/ranging)
    - Confidence score
    - ATR (Average True Range)
    
    Returns SL price, TP1 price, SL percentage, trailing percentage, and TP1 percentage
    """
    # Select appropriate timeframe for ATR calculation based on trade type
    atr_tf_map = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    
    # Calculate ATR if we have candles
    if candles and len(candles) >= 30:
        from atr import calculate_atr
        atr = calculate_atr(candles)
    else:
        atr = None

    # Base ATR multiplier - adjust based on confidence
    atr_factor = 1.5 if confidence >= 80 else (1.2 if confidence >= 65 else 1.8)
    
    # If we have ATR, use it to calculate SL distance
    if atr:
        sl_distance = atr * atr_factor
        sl_pct = (sl_distance / price) * 100
    else:
        # Fallback percentages if ATR not available
        if confidence >= 85 and score >= 7.5:
            sl_pct = 1.5  # Tighter stop for high confidence setups
        elif confidence < 60 or score < 6:
            sl_pct = 2.5  # Wider stop for lower confidence
        else:
            sl_pct = 2.0  # Default stop percentage

    # Adjust based on market regime
    if regime == "volatile":
        sl_pct *= 1.5  # Wider stops in volatile markets
    elif regime == "ranging":
        sl_pct *= 1.3  # Slightly wider stops in ranging markets

    # Calculate TP based on risk-reward ratio that varies with trade type
    if trade_type == "Scalp":
        tp1_ratio = 1.5  # 1.5:1 reward-to-risk for scalps
    elif trade_type == "Intraday":
        tp1_ratio = 1.8  # 1.8:1 for intraday
    else:  # Swing
        tp1_ratio = 2.2  # 2.2:1 for swing trades
    
    tp1_pct = sl_pct * tp1_ratio
    
    # Calculate trailing percentage (typically 1/3 to 1/2 of SL percentage)
    trailing_pct = sl_pct * 0.4 if trade_type == "Scalp" else sl_pct * 0.5
    
    # Calculate actual price levels
    if direction.lower() == "long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:  # Short
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    return sl, tp1, sl_pct, trailing_pct, tp1_pct

def calculate_optimal_sl(symbol, direction, entry_price, current_price, trade_type="Intraday", candles=None):
    """
    Calculate optimal SL based on multiple factors:
    - Current price
    - Trade type
    - ATR
    - Market volatility
    """
    # Base percentage for SL based on trade type
    base_pct = {
        "Scalp": 0.8,
        "Intraday": 1.2,
        "Swing": 2.0
    }.get(trade_type, 1.2)
    
    # Calculate ATR-based SL if candles available
    atr = None
    if candles and len(candles) >= 30:
        from atr import calculate_atr
        atr = calculate_atr(candles)
    
    # Calculate ATR-based SL if available
    if atr:
        atr_factor = 1.5
        atr_sl_pct = (atr / current_price) * 100 * atr_factor
        # Use ATR-based SL if greater than base
        base_pct = max(base_pct, atr_sl_pct)
    
    # Adjust for market volatility
    volatility_factor = 1.0
    # Check recent price action for volatility
    if candles and len(candles) >= 10:
        recent_high = max(float(c['high']) for c in candles[-10:])
        recent_low = min(float(c['low']) for c in candles[-10:])
        price_range = (recent_high - recent_low) / recent_low
        if price_range > 0.03:  # 3% range considered volatile
            volatility_factor = 1.3
    
    final_sl_pct = base_pct * volatility_factor
    
    # Calculate actual SL price
    if direction.lower() == "long":
        sl_price = current_price * (1 - final_sl_pct/100)
    else:
        sl_price = current_price * (1 + final_sl_pct/100)
    
    # Get precision and round properly
    precision = get_precision(symbol)
    sl_price = round(sl_price, precision)
    
    log(f"🎯 Calculated optimal SL for {symbol} ({direction}): {sl_price} | Base: {base_pct:.2f}% | Volatility: {volatility_factor} | Final: {final_sl_pct:.2f}%")
    return sl_price

def calculate_early_trailing_stop(symbol, direction, entry_price, current_price, trailing_pct=0.5):
    """
    Calculate trailing stop that follows price from entry point.
    Activates immediately when price moves favorably.
    """
    precision = get_precision(symbol)
    
    # For long positions
    if direction.lower() == "long":
        # If price moved up from entry
        if current_price > entry_price:
            # Calculate how much we've moved up
            move_up = current_price - entry_price
            # Trail by trailing_pct of this movement
            new_sl = entry_price + (move_up * (1 - trailing_pct/100))
            return round(new_sl, precision)
        return None
    
    # For short positions
    elif direction.lower() == "short":
        # If price moved down from entry
        if current_price < entry_price:
            # Calculate how much we've moved down
            move_down = entry_price - current_price
            # Trail by trailing_pct of this movement
            new_sl = entry_price - (move_down * (1 - trailing_pct/100))
            return round(new_sl, precision)
        return None

async def validate_sl_price(symbol, direction, sl_price, market_type="linear"):
    """
    Validates that an SL price is on the correct side of the current market price.
    Returns adjusted price if needed.
    """
    try:
        from bybit_api import signed_request
        
        # Get current mark price
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": market_type, "symbol": symbol})
        mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
        
        if mark_price <= 0:
            log(f"⚠️ Invalid mark price ({mark_price}) for {symbol}", level="WARN")
            return sl_price
        
        # Ensure SL is on the correct side of mark price
        if direction.lower() == "long" and sl_price >= mark_price:
            # For long positions, SL must be below mark price
            new_sl = round(mark_price * 0.995, 6)  # 0.5% below
            log(f"⚠️ Adjusted long SL from {sl_price} to {new_sl} (below mark price {mark_price})", level="WARN")
            return new_sl
        elif direction.lower() == "short" and sl_price <= mark_price:
            # For short positions, SL must be above mark price
            new_sl = round(mark_price * 1.005, 6)  # 0.5% above
            log(f"⚠️ Adjusted short SL from {sl_price} to {new_sl} (above mark price {mark_price})", level="WARN")
            return new_sl
        
        # If SL is already on the correct side, return original
        return sl_price
    except Exception as e:
        log(f"❌ Error validating SL price: {e}", level="ERROR")
        return sl_price  # Return original price if validation fails
