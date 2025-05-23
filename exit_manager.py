from volume import get_average_volume
from symbol_info import get_precision, round_qty
from activity_logger import write_log
from logger import log
from atr import calculate_atr
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

def calculate_exit_tranches(symbol, qty, tranches=3):
    """
    Split position into multiple exit tranches - UPDATED for "let winners run"
    Returns a list of quantities for each exit level
    Now uses 20% / 30% / 50% distribution instead of 33% / 33% / 34%
    """
    if qty <= 0:
        return []
        
    min_qty = 0.001  # Use symbol info or fallback
    
    # UPDATED: New distribution to let winners run
    # 20% at TP1, 30% at TP2, 50% rides momentum
    tranche_percentages = [0.20, 0.30, 0.50]  # Changed from [0.33, 0.33, 0.34]
    
    # Calculate tranche sizes
    tranche_sizes = [qty * pct for pct in tranche_percentages]
    
    # Ensure all tranches meet minimum quantity requirements
    precision = get_precision(symbol)
    valid_tranches = [round(max(t, min_qty), precision) for t in tranche_sizes]
    
    # Adjust last tranche to ensure total equals original quantity
    sum_tranches = sum(valid_tranches[:-1])
    valid_tranches[-1] = round(max(qty - sum_tranches, min_qty), precision)
    
    log(f"🔢 EXIT TRANCHES (Let Winners Run): {symbol} - 20%: {valid_tranches[0]}, 30%: {valid_tranches[1]}, 50%: {valid_tranches[2]}")
    return valid_tranches

def detect_momentum_surge(candles, lookback=5):
    """
    Detect if we're in a strong momentum move that might continue
    Returns True if strong momentum is detected
    """
    if len(candles) < lookback + 5:
        return False
        
    # Get recent candles and slightly older candles for comparison
    recent = candles[-lookback:]
    prior = candles[-(lookback+5):-lookback]
    
    # Calculate average volume increase
    recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
    prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
    vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
    
    # Calculate price momentum
    recent_opens = [float(c['open']) for c in recent]
    recent_closes = [float(c['close']) for c in recent]
    
    # Count consecutive up/down candles
    if recent_closes[-1] > recent_opens[-1]:  # Current candle is up
        consecutive_up = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] > recent_opens[i]:
                consecutive_up += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive up candles with 2x+ volume
        if consecutive_up >= 3 and vol_increase >= 2.0:
            return True
    
    # For downward momentum (for shorts)
    if recent_closes[-1] < recent_opens[-1]:  # Current candle is down
        consecutive_down = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] < recent_opens[i]:
                consecutive_down += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive down candles with 2x+ volume
        if consecutive_down >= 3 and vol_increase >= 2.0:
            return True
    
    return False

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

def calculate_adaptive_trailing(symbol, candles, direction, current_price, base_trail_pct):
    """
    Adjust trailing percentage based on recent volatility and momentum.
    UPDATED: More conservative trailing to let winners run longer
    """
    try:
        # Use 7-period ATR for current volatility
        atr_short = calculate_atr(candles, period=7)
        # Use 21-period ATR for baseline volatility
        atr_long = calculate_atr(candles, period=21)
        
        volatility_factor = 1.0
        
        if atr_short and atr_long and atr_long > 0:
            # Calculate volatility ratio
            vol_ratio = atr_short / atr_long
            
            if vol_ratio > 1.5:
                # Higher volatility = wider trailing to avoid noise
                volatility_factor = 1.5  # Increased from 1.3 to let winners run
                log(f"📊 High volatility detected for {symbol}: {vol_ratio:.2f}x - widening trail")
            elif vol_ratio < 0.7:
                # Lower volatility = still use reasonable trailing
                volatility_factor = 0.9  # Increased from 0.8 to let winners run
                log(f"📊 Low volatility detected for {symbol}: {vol_ratio:.2f}x - using moderate trail")
        
        # Check for momentum surge - uses MUCH wider trailing to catch bigger moves
        if detect_momentum_surge(candles):
            momentum_factor = 2.0  # Increased from 1.5 to let winners run much longer
            log(f"🚀 Momentum surge detected for {symbol} - using MUCH wider trailing ({momentum_factor}x)")
            volatility_factor = max(volatility_factor, momentum_factor)
        
        adjusted_pct = base_trail_pct * volatility_factor
        log(f"🔄 Adjusted trailing % for {symbol}: {base_trail_pct:.2f}% → {adjusted_pct:.2f}%")
        return adjusted_pct
        
    except Exception as e:
        log(f"⚠️ Error in adaptive trailing calculation: {e}", level="WARN")
        return base_trail_pct  # Return original as fallback

def should_trail_stop(symbol, entry_price, current_price, direction="long", candles=None, trigger_pct=0.018, trail_pct=0.009, current_trailing_sl=None):
    """
    Checks if trailing stop should activate - UPDATED for letting winners run
    """
    # UPDATED: Require higher volume confirmation for trailing activation
    if candles:
        avg_volume = get_average_volume(candles)
        current_volume = float(candles[-1]['volume'])
        
        # Check for mega pump pattern - in strong momentum be even more permissive
        in_momentum_surge = detect_momentum_surge(candles)
        
        # UPDATED: Only trail if volume is significantly higher OR in momentum surge
        if current_volume < avg_volume * 1.5 and not in_momentum_surge:  # Increased from 1.2x to 1.5x
            write_log(f"🔕 Volume too low for trailing: {current_volume:.2f} < 1.5x avg {avg_volume:.2f}")
            return None
            
        # Use adaptive trailing with more conservative settings
        adjusted_trail_pct = calculate_adaptive_trailing(symbol, candles, direction, current_price, trail_pct)
    else:
        adjusted_trail_pct = trail_pct

    # Calculate potential new SL value
    new_sl = calculate_trailing_stop(symbol, entry_price, current_price, direction, trigger_pct, adjusted_trail_pct)
    if not new_sl:
        return None

    # Only update SL if it's significantly better (tighter) than current
    # UPDATED: Require bigger improvement to update trailing SL
    if current_trailing_sl:
        min_improvement_pct = 0.5  # Require at least 0.5% improvement
        if direction.lower() == "long":
            improvement = (new_sl - current_trailing_sl) / current_trailing_sl * 100
            if improvement < min_improvement_pct:
                return None
        else:  # short
            improvement = (current_trailing_sl - new_sl) / current_trailing_sl * 100
            if improvement < min_improvement_pct:
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

    # Calculate TP based on risk-reward ratio that varies with trade type AND regime
    # Using higher TP targets to catch larger pumps
    base_tp_ratios = {
        "Scalp": 2.0,      # 2.0:1 reward-to-risk for scalps (increased from 1.5)
        "Intraday": 2.5,   # 2.5:1 for intraday (increased from 1.8)
        "Swing": 3.0       # 3.0:1 for swing trades (increased from 2.2)
    }
    
    tp1_ratio = base_tp_ratios.get(trade_type, 2.5)
    
    # Adjust TP ratio based on market regime
    if regime == "volatile":
        tp1_ratio *= 1.4   # Higher targets in volatile markets to catch pumps
    elif regime == "ranging":
        tp1_ratio *= 0.85  # Tighter targets in ranging markets
    
    tp1_pct = sl_pct * tp1_ratio
    
    # Calculate trailing percentage (typically 1/3 to 1/2 of SL percentage)
    # Using wider trailing % to avoid getting stopped out of big pumps
    trailing_pct = sl_pct * 0.4 if trade_type == "Scalp" else sl_pct * 0.5
    
    # Calculate actual price levels
    if direction.lower() == "long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:  # Short
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    log(f"📊 SL/TP calculated for {direction} {trade_type} in {regime} regime | SL: {sl_pct:.2f}% | TP: {tp1_pct:.2f}% | Ratio: {tp1_ratio:.2f}")
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

def adjust_profit_protection(symbol, entry_price, current_price, direction, trade_type="Intraday"):
    """
    Adjust stop loss based on profit milestones reached
    Returns a new stop loss price if a milestone is hit, otherwise None
    """
    precision = get_precision(symbol)
    
    if not entry_price or entry_price <= 0:
        return None
        
    # Calculate current profit percentage
    if direction.lower() == "long":
        profit_pct = ((current_price - entry_price) / entry_price) * 100
    else:  # short
        profit_pct = ((entry_price - current_price) / entry_price) * 100
    
    # Define profit milestones based on trade type
    # Modified to be more tolerant of big moves
    milestones = {
        "Scalp": [
            {"pct": 2.0, "sl_at": 0.5},  # At 2% profit, move SL to 0.5% profit
            {"pct": 4.0, "sl_at": 1.5},  # At 4% profit, move SL to 1.5% profit
            {"pct": 7.0, "sl_at": 3.0}   # At 7% profit, move SL to 3% profit
        ],
        "Intraday": [
            {"pct": 3.0, "sl_at": 0.5},  # At 3% profit, move SL to 0.5% profit
            {"pct": 6.0, "sl_at": 2.0},  # At 6% profit, move SL to 2.0% profit
            {"pct": 10.0, "sl_at": 4.0}  # At 10% profit, move SL to 4% profit
        ],
        "Swing": [
            {"pct": 5.0, "sl_at": 1.0},   # At 5% profit, move SL to 1% profit
            {"pct": 10.0, "sl_at": 3.0},  # At 10% profit, move SL to 3% profit
            {"pct": 15.0, "sl_at": 6.0}   # At 15% profit, move SL to 6% profit
        ]
    }
    
    # Get appropriate milestones based on trade type
    trade_milestones = milestones.get(trade_type, milestones["Intraday"])
    
    # Find the highest milestone reached
    best_milestone = None
    for milestone in trade_milestones:
        if profit_pct >= milestone["pct"]:
            best_milestone = milestone
        else:
            break
            
    # If milestone reached, calculate new SL price
    if best_milestone:
        sl_pct = best_milestone["sl_at"]
        
        if direction.lower() == "long":
            new_sl = entry_price * (1 + sl_pct/100)
        else:  # short
            new_sl = entry_price * (1 - sl_pct/100)
            
        new_sl = round(new_sl, precision)
        log(f"💰 Profit protection triggered for {symbol} at {profit_pct:.2f}% profit. New SL: {new_sl} ({sl_pct:.2f}% profit)")
        return new_sl
        
    return None

def detect_price_momentum(candles, lookback=5):
    """
    Detect if price is showing strong momentum based on recent candles
    Returns tuple of (has_momentum, direction, strength)
    """
    if len(candles) < lookback + 5:
        return False, None, 0.0
        
    try:
        recent = candles[-lookback:]
        prior = candles[-(lookback+5):-lookback]
        
        # Calculate recent volume vs prior
        recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
        prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
        vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
        
        # Calculate consecutive up/down candles
        consecutive_up = 0
        consecutive_down = 0
        
        for i in range(len(recent)):
            candle_close = float(recent[i]['close'])
            candle_open = float(recent[i]['open'])
            
            if candle_close > candle_open:  # Bullish candle
                consecutive_up += 1
                consecutive_down = 0
            elif candle_close < candle_open:  # Bearish candle
                consecutive_down += 1
                consecutive_up = 0
        
        # Calculate price movement percentage
        first_candle_open = float(recent[0]['open'])
        last_candle_close = float(recent[-1]['close'])  
        price_change_pct = ((last_candle_close - first_candle_open) / first_candle_open) * 100
        
        # Determine momentum direction
        direction = "up" if price_change_pct > 0 else "down"
        
        # Calculate momentum strength (0-1 scale)
        strength = 0
        if consecutive_up >= 3 or consecutive_down >= 3:
            strength += 0.4
        if vol_increase >= 1.5:
            strength += 0.3
        if abs(price_change_pct) >= 1.0:
            strength += 0.3
        
        has_momentum = strength >= 0.6  # 60% of criteria met
        
        return has_momentum, direction, strength
        
    except Exception as e:
        log(f"❌ Error detecting price momentum: {e}", level="ERROR")
        return False, None, 0.0

def should_exit_by_time(trade, current_time=None, candles=None, current_price=None):
    """
    Check if trade should be exited based on time elapsed
    FIXED: Proper datetime handling to avoid comparison errors
    """
    from datetime import datetime
    
    if not current_time:
        current_time = datetime.utcnow()
    
    # Ensure current_time is a datetime object
    if not isinstance(current_time, datetime):
        try:
            current_time = datetime.utcnow()
        except:
            return False
    
    try:
        # Get trade entry time
        entry_time_str = trade.get("timestamp")
        if not entry_time_str:
            return False
            
        # Parse entry time - handle different possible formats
        try:
            if isinstance(entry_time_str, str):
                entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
            elif isinstance(entry_time_str, datetime):
                entry_time = entry_time_str
            else:
                log(f"⚠️ Invalid timestamp format: {entry_time_str}", level="WARN")
                return False
        except ValueError:
            # Try alternative format
            try:
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
            except:
                log(f"⚠️ Could not parse timestamp: {entry_time_str}", level="WARN")
                return False
        
        # Calculate trade age in hours
        trade_age_hours = (current_time - entry_time).total_seconds() / 3600
        
        trade_type = trade.get("trade_type")
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        
        # Don't exit if we're in profit and in momentum
        if candles:
            has_momentum, momentum_direction, _ = detect_price_momentum(candles)
            momentum_aligned = (direction == "long" and momentum_direction == "up") or \
                              (direction == "short" and momentum_direction == "down")
            
            # Check if in significant profit
            is_in_profit = False
            if entry_price and current_price:
                if direction == "long":
                    is_in_profit = current_price > entry_price * 1.02  # 2% profit
                else:
                    is_in_profit = current_price < entry_price * 0.98  # 2% profit
                    
            if has_momentum and momentum_aligned and is_in_profit:
                # Don't exit on time if in profitable momentum
                return False
        
        # Define max age based on trade type
        max_age = {
            "Scalp": 12,      # 12 hours for scalps
            "Intraday": 36,   # 36 hours for intraday
            "Swing": 120      # 120 hours (5 days) for swing trades
        }.get(trade_type, 36)
        
        # For scalps - check for progress
        if trade_type == "Scalp" and trade_age_hours > 4 and not trade.get("tp1_hit") and entry_price:
            # Check if price is making any progress
            if direction == "long":
                # For longs, exit if price is below entry after 4 hours
                if current_price < entry_price:
                    log(f"⏱ Time-based exit for {trade.get('symbol')}: Scalp not making progress after {trade_age_hours:.1f} hours")
                    return True
            else:  # short
                # For shorts, exit if price is above entry after 4 hours
                if current_price > entry_price:
                    log(f"⏱ Time-based exit for {trade.get('symbol')}: Scalp not making progress after {trade_age_hours:.1f} hours")
                    return True
        
        # If trade has hit TP1, give it more time
        if trade.get("tp1_hit"):
            max_age *= 1.5  # 50% more time after TP1 is hit
        
        # Exit any trade if max age exceeded
        if trade_age_hours > max_age:
            log(f"⏱ Time-based exit for {trade.get('symbol')}: Max age of {max_age} hours exceeded ({trade_age_hours:.1f} hours)")
            return True
            
    except Exception as e:
        log(f"❌ Error in time-based exit check: {e}", level="ERROR")
        log(f"Debug info - trade timestamp: {trade.get('timestamp')}, current_time type: {type(current_time)}")
        import traceback
        log(f"Stack trace: {traceback.format_exc()}", level="ERROR")
    
    return False

def evaluate_score_exit(symbol, trade, score_history, min_exit_cycles=3):
    """
    Evaluate whether to exit based on score deterioration pattern
    Returns True if exit is recommended based on score trend
    """
    # Disabled to prevent premature exits - using SL for protection instead
    return False
    
    trade_type = trade.get("trade_type", "Intraday")
    recent_scores = score_history[-min_exit_cycles:]
    
    # Don't exit during momentum
    candles = trade.get("candles_1m")
    if candles and detect_momentum_surge(candles):
        log(f"🚀 Momentum surge detected for {symbol} - bypassing score-based exit")
        return False
    
    # Calculate peak score and current score
    max_score = max(score_history)
    current_score = score_history[-1]
    absolute_drop = max_score - current_score
    pct_drop = (absolute_drop / max_score * 100) if max_score > 0 else 0
    
    # Check if scores are consistently declining
    is_deteriorating = all(recent_scores[i] >= recent_scores[i+1] for i in range(len(recent_scores)-1))
    
    # Different thresholds based on trade type
    thresholds = {
        "Scalp": 4.0,     # More tolerant for scalps
        "Intraday": 3.5,  # More tolerant for intraday
        "Swing": 3.0      # More tolerant for swings
    }
    
    threshold = thresholds.get(trade_type, 4.0)
    
    # Exit criteria - must meet ALL conditions:
    # 1. Consistent score drop over recent cycles
    # 2. Current score below threshold
    # 3. Significant absolute drop from peak (at least 2 points)
    # 4. Significant percentage drop from peak (at least 30%)
    should_exit = (
        is_deteriorating and
        current_score < threshold and
        absolute_drop >= 2.0 and
        pct_drop >= 30
    )
    
    if should_exit:
        log(f"📉 Score deterioration exit for {symbol}: Current: {current_score}, Peak: {max_score}, " 
            f"Drop: {absolute_drop:.2f} ({pct_drop:.1f}%), Threshold: {threshold}")
    
    return should_exit

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
