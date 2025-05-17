import numpy as np
from symbol_info import get_precision, round_qty
from logger import log
import asyncio

def calculate_atr(candles, period=14):
    """
    Calculate the Average True Range (ATR) from candles.
    
    Args:
        candles: List of candle dictionaries with 'high', 'low', 'close' keys
        period: ATR calculation period
        
    Returns:
        ATR value or None if not enough candles
    """
    if len(candles) < period + 1:
        return None

    highs = np.array([float(c['high']) for c in candles[-(period+1):]])
    lows = np.array([float(c['low']) for c in candles[-(period+1):]])
    closes = np.array([float(c['close']) for c in candles[-(period+1):]])

    tr_list = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)

    atr = np.mean(tr_list)
    return round(atr, 6)  # Round to 6 decimal places

def detect_price_momentum(candles, lookback=5):
    """
    Detect if price is showing strong momentum based on recent candles.
    
    Args:
        candles: List of candle dictionaries
        lookback: Number of recent candles to analyze
        
    Returns:
        Tuple of (has_momentum: bool, direction: str, strength: float)
    """
    if len(candles) < lookback + 5:
        return False, None, 0.0
    
    # Get recent candles for analysis
    recent = candles[-lookback:]
    
    # Calculate consecutive up/down candles
    consecutive_up = 0
    consecutive_down = 0
    
    for i in range(len(recent)):
        if float(recent[i]['close']) > float(recent[i]['open']):
            consecutive_up += 1
            consecutive_down = 0
        elif float(recent[i]['close']) < float(recent[i]['open']):
            consecutive_down += 1
            consecutive_up = 0
    
    # Calculate volume increase
    recent_vol = sum(float(c['volume']) for c in recent) / len(recent)
    prev_vol = sum(float(c['volume']) for c in candles[-(lookback+5):-lookback]) / lookback
    vol_ratio = recent_vol / prev_vol if prev_vol > 0 else 1.0
    
    # Calculate price momentum
    price_change = (float(recent[-1]['close']) - float(recent[0]['open'])) / float(recent[0]['open']) * 100
    
    # Determine momentum direction and strength
    direction = "up" if price_change > 0 else "down"
    
    # Strength is based on consecutive candles, volume increase, and price change
    strength = 0.0
    if consecutive_up >= 3 or consecutive_down >= 3:
        strength += 0.5
    if vol_ratio > 1.5:
        strength += 0.3
    if abs(price_change) > 1.0:
        strength += 0.2
    
    has_momentum = strength >= 0.7  # 70% of criteria met
    
    return has_momentum, direction, strength

def calculate_dynamic_sl_tp(candles_by_tf, entry_price, trade_type, direction, score, confidence, regime="trending"):
    """
    Calculate dynamic SL/TP using ATR, entry price, confidence, and market regime.
    Enhanced for better pump capture.
    
    Args:
        candles_by_tf: Dictionary of candles organized by timeframe
        entry_price: Entry price of the trade
        trade_type: "Scalp", "Intraday", or "Swing"
        direction: "long" or "short"
        score: Trade setup score (0-10)
        confidence: Confidence percentage (0-100)
        regime: Market regime ("trending", "ranging", "volatile")
        
    Returns:
        Tuple of (stop_loss, take_profit, sl_percentage, trailing_percentage, tp_percentage)
    """
    # Select appropriate timeframe based on trade type
    tf_mapping = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    selected_tf = tf_mapping.get(trade_type, '15')
    
    # Get candles for the selected timeframe
    candles = candles_by_tf.get(selected_tf, [])
    
    # Check for momentum which will affect our targets
    has_momentum, momentum_direction, momentum_strength = detect_price_momentum(
        candles_by_tf.get('1', []) if '1' in candles_by_tf else candles
    )
    
    momentum_aligned = (direction.lower() == "long" and momentum_direction == "up") or \
                       (direction.lower() == "short" and momentum_direction == "down")
    
    # Calculate ATR if enough candles are available
    atr = calculate_atr(candles) if len(candles) >= 15 else None
    
    # Default ATR factor - adjust based on confidence and score
    # Tighter for high confidence, wider for lower confidence
    atr_factor = 1.5 if confidence >= 80 or score >= 8.0 else 2.0
    
    # Determine SL percentage based on ATR or fallback values
    if atr and atr > 0:
        sl_pct = (atr * atr_factor / entry_price) * 100
        log(f"📊 SL calculation using ATR: {atr} × {atr_factor} = {sl_pct:.2f}%")
    else:
        # Fallback percentages based on trade type and confidence
        if trade_type == "Scalp":
            sl_pct = 1.0 if confidence > 80 else 1.5
        elif trade_type == "Intraday":
            sl_pct = 1.5 if confidence > 80 else 2.0
        else:  # Swing
            sl_pct = 2.0 if confidence > 80 else 3.0
            
        log(f"📊 SL calculation using fallback: {sl_pct:.2f}%")
    
    # Adjust SL based on market regime
    regime_multipliers = {"trending": 1.0, "ranging": 1.3, "volatile": 1.6}
    regime_mult = regime_multipliers.get(regime.lower(), 1.0)
    
    if regime_mult != 1.0:
        sl_pct *= regime_mult
        log(f"📊 SL adjusted for {regime} regime: {sl_pct:.2f}% (×{regime_mult})")
    
    # Determine TP percentage based on risk-reward ratios that vary with trade type
    # Enhanced for better pump capture - higher RR ratios
    rr_ratios = {
        "Scalp": 2.0,     # Increased from 1.5 to 2.0
        "Intraday": 2.5,  # Increased from 2.0 to 2.5
        "Swing": 3.0      # Increased from 2.5 to 3.0
    }
    tp_multiplier = rr_ratios.get(trade_type, 2.5)
    
    # For volatile markets, increase targets for pumps
    if regime.lower() == "volatile":
        tp_multiplier *= 1.2  # Increase targets in volatile markets
    
    # If we have aligned momentum, set even higher targets
    if has_momentum and momentum_aligned:
        tp_multiplier *= 1.2  # Additional 20% higher targets with momentum
        log(f"🚀 Momentum detected ({momentum_strength:.1f}) - increasing targets by 20%")
    
    tp_pct = sl_pct * tp_multiplier
    
    # Calculate trailing stop percentage - optimized for catching pumps
    # Use wider trailing stops to avoid getting shaken out
    trailing_mult_map = {
        "Scalp": 0.5,    # Was 0.4, now 0.5 (wider)
        "Intraday": 0.6, # Was 0.5, now 0.6 (wider)
        "Swing": 0.7     # Was 0.5, now 0.7 (wider)
    }
    trailing_mult = trailing_mult_map.get(trade_type, 0.6)
    trailing_pct = sl_pct * trailing_mult
    
    # Calculate actual price levels
    if direction.lower() == "long":
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)
    else:
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)
    
    # Round prices appropriately
    sl_price = round(sl_price, 6)
    tp_price = round(tp_price, 6)
    
    # Calculate TP2 for bigger moves (useful for partial exits)
    tp2_multiplier = tp_multiplier * 1.8  # TP2 is 1.8x further than TP1
    tp2_pct = sl_pct * tp2_multiplier
    
    if direction.lower() == "long":
        tp2_price = round(entry_price * (1 + tp2_pct / 100), 6)
    else:
        tp2_price = round(entry_price * (1 - tp2_pct / 100), 6)
    
    log(f"📊 TP calculations: TP1={tp_pct:.2f}% (×{tp_multiplier:.1f}), TP2={tp2_pct:.2f}% (×{tp2_multiplier:.1f}), Trailing={trailing_pct:.2f}%")
    
    return sl_price, tp_price, round(sl_pct, 2), round(trailing_pct, 2), round(tp_pct, 2), tp2_price, round(tp2_pct, 2)

async def validate_sl_placement(symbol, direction, sl_price, market_type="linear"):
    """
    Validate that a stop loss price is on the correct side of current market price.
    
    Args:
        symbol: Trading symbol
        direction: "long" or "short"
        sl_price: Proposed stop loss price
        market_type: Exchange market type
        
    Returns:
        Corrected SL price or original if already valid
    """
    from bybit_api import signed_request
    
    try:
        # Get current market price
        ticker_resp = await signed_request("GET", "/v5/market/tickers", 
                                           {"category": market_type, "symbol": symbol})
        
        # Extract mark price, last price, and bid/ask if available
        result_data = ticker_resp.get("result", {}).get("list", [{}])[0]
        mark_price = float(result_data.get("markPrice", 0))
        last_price = float(result_data.get("lastPrice", 0))
        
        # Use mark price if available, otherwise fall back to last price
        current_price = mark_price if mark_price > 0 else last_price
        
        if current_price <= 0:
            log(f"⚠️ Invalid market price for {symbol}", level="WARN")
            return sl_price  # Return original if we can't validate
        
        # Add safety buffer (0.5% for normal conditions)
        buffer_pct = 0.005  # 0.5%
        
        # For long positions, SL must be below current price
        if direction.lower() == "long":
            if sl_price >= current_price:
                new_sl = round(current_price * (1 - buffer_pct), 6)
                log(f"⚠️ Fixed long SL from {sl_price} to {new_sl} (below {current_price})", level="WARN")
                return new_sl
                
        # For short positions, SL must be above current price
        elif direction.lower() == "short":
            if sl_price <= current_price:
                new_sl = round(current_price * (1 + buffer_pct), 6)
                log(f"⚠️ Fixed short SL from {sl_price} to {new_sl} (above {current_price})", level="WARN")
                return new_sl
        
        # If already valid, return original SL price
        return sl_price
        
    except Exception as e:
        log(f"❌ Error validating SL placement: {e}", level="ERROR")
        return sl_price  # Return original if validation fails

def calculate_exit_tranches(symbol, total_qty, tranche_count=3):
    """
    Calculate position size for each exit tranche to optimize for catching pumps.
    
    Args:
        symbol: Trading symbol for precision lookup
        total_qty: Total position size
        tranche_count: Number of exit tranches
        
    Returns:
        List of quantities for each tranche
    """
    if total_qty <= 0:
        return []
    
    # Get symbol precision for rounding
    precision = get_precision(symbol)
    min_qty = 0.001  # Fallback min quantity
    
    # For a 3-tranche exit strategy optimized for catching pumps:
    # - First tranche: 30% of position at TP1 (secure initial profit)
    # - Second tranche: 30% of position during pump continuation
    # - Third tranche: 40% of position for potential home run
    distributions = [0.30, 0.30, 0.40]  # Last tranche is larger to catch big pumps
    
    # Calculate raw tranches
    raw_tranches = [total_qty * dist for dist in distributions]
    
    # Round to valid quantities
    valid_tranches = [round(max(round_qty(symbol, qty), min_qty), precision) for qty in raw_tranches]
    
    # Adjust final tranche to ensure total equals original quantity
    sum_first_tranches = sum(valid_tranches[:-1])
    final_tranche = round(max(total_qty - sum_first_tranches, min_qty), precision)
    valid_tranches[-1] = final_tranche
    
    log(f"📊 Exit tranches for {symbol}: {valid_tranches} (from total {total_qty})")
    return valid_tranches

def calculate_tp_levels(entry_price, direction, risk_pct, rr_ratios=[2.0, 3.5, 6.0]):
    """
    Calculate multiple take profit levels based on risk-reward ratios.
    Enhanced for catching bigger pumps with more aggressive targets.
    
    Args:
        entry_price: Trade entry price
        direction: "long" or "short"
        risk_pct: Risk percentage from entry to SL
        rr_ratios: List of risk-reward ratios for TP levels
        
    Returns:
        List of TP prices
    """
    tp_prices = []
    
    for ratio in rr_ratios:
        reward_pct = risk_pct * ratio
        
        if direction.lower() == "long":
            tp_price = entry_price * (1 + reward_pct / 100)
        else:
            tp_price = entry_price * (1 - reward_pct / 100)
            
        tp_prices.append(round(tp_price, 6))
    
    return tp_prices

def calculate_position_size(account_balance, risk_usd, entry_price, sl_price, leverage=1):
    """
    Calculate position size based on fixed dollar risk.
    
    Args:
        account_balance: Account balance in USD
        risk_usd: Amount willing to risk in USD
        entry_price: Entry price
        sl_price: Stop loss price
        leverage: Leverage multiplier
        
    Returns:
        Position size in base currency units
    """
    # Ensure valid inputs
    if entry_price <= 0 or sl_price <= 0 or entry_price == sl_price:
        return 0
    
    # Calculate risk percentage
    risk_per_unit = abs(entry_price - sl_price) / entry_price
    
    # Calculate position size with leverage
    if risk_per_unit > 0:
        position_value = risk_usd / risk_per_unit
        position_size = position_value / entry_price * leverage
        return round(position_size, 6)
    
    return 0

def calculate_risk_reward_ratio(entry_price, sl_price, tp_price):
    """
    Calculate risk-reward ratio for a trade setup.
    
    Args:
        entry_price: Trade entry price
        sl_price: Stop loss price  
        tp_price: Take profit price
        
    Returns:
        Risk-reward ratio as a float
    """
    # Ensure valid inputs
    if not all([entry_price, sl_price, tp_price]) or entry_price == sl_price:
        return 0
    
    # Calculate risk and reward
    risk = abs(entry_price - sl_price)
    reward = abs(entry_price - tp_price)
    
    # Return RR ratio
    if risk > 0:
        return round(reward / risk, 2)
    return 0

def calculate_breakeven_after_move(entry_price, direction, move_pct=1.0):
    """
    Calculate breakeven price after a certain percentage move in favor.
    
    Args:
        entry_price: Trade entry price
        direction: "long" or "short"
        move_pct: Percentage move required before setting breakeven
        
    Returns:
        Breakeven price (usually entry, but can include buffer)
    """
    # Include a small buffer (0.1%) to account for fees
    buffer = entry_price * 0.001
    
    if direction.lower() == "long":
        return entry_price + buffer
    else:
        return entry_price - buffer

def should_exit_on_time(trade_timestamp, current_time, trade_type):
    """
    Determine if a trade should be exited based on time elapsed.
    
    Args:
        trade_timestamp: When the trade was entered
        current_time: Current timestamp
        trade_type: "Scalp", "Intraday", or "Swing"
        
    Returns:
        Boolean indicating if trade should be exited
    """
    from datetime import datetime, timedelta
    
    if not trade_timestamp:
        return False
    
    try:
        trade_time = datetime.strptime(trade_timestamp, "%Y-%m-%d %H:%M:%S")
        elapsed_hours = (current_time - trade_time).total_seconds() / 3600
        
        # Maximum hold times for each trade type
        max_hours = {
            "Scalp": 4,      # 4 hours max for scalps
            "Intraday": 24,  # 24 hours max for intraday
            "Swing": 72      # 72 hours (3 days) max for swings
        }
        
        return elapsed_hours > max_hours.get(trade_type, 24)
    except:
        return False
