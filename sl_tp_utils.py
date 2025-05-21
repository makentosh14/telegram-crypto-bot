import asyncio
import traceback
from datetime import datetime
import numpy as np
from logger import log, write_log
from symbol_info import get_precision, round_qty
from error_handler import send_telegram_message, send_error_to_telegram

# Constants for SL/TP calculations
MIN_SL_PERCENTAGE = 0.5       # Minimum SL distance (0.5%)
MIN_SL_ATR_FACTOR = 1.0       # Minimum ATR factor for SL calculation
MAX_SL_PERCENTAGE = 10.0      # Maximum SL distance (10%)
MAX_SL_ATR_FACTOR = 3.0       # Maximum ATR factor for SL calculation

# Target risk-reward ratios by trade type
TARGET_RR_RATIOS = {
    "Scalp": 1.5,
    "Intraday": 2.0,
    "Swing": 2.5,
    "mean_reversion": 1.8,
    "breakout_sniper": 2.2,
}

# Trailing stop activation thresholds
TRAILING_ACTIVATION_THRESHOLD = 1.0  # Minimum move % to activate trailing
TRAILING_PERCENTAGE_MAP = {
    "Scalp": 0.4,              # 40% of initial stop distance
    "Intraday": 0.5,           # 50% of initial stop distance
    "Swing": 0.6,              # 60% of initial stop distance
    "mean_reversion": 0.3,     # 30% of initial stop distance
    "breakout_sniper": 0.4,    # 40% of initial stop distance
}

# Market regime adjustments
REGIME_ADJUSTMENTS = {
    "trending": {"sl": 1.0, "tp": 1.0, "trailing": 1.0},
    "ranging": {"sl": 1.2, "tp": 0.8, "trailing": 0.8},
    "volatile": {"sl": 1.5, "tp": 1.2, "trailing": 1.3},
}

# Exit tranches configuration
EXIT_TRANCHES = {
    "Scalp": [0.4, 0.3, 0.3],     # 40% at TP1, 30% at TP2, 30% at TP3
    "Intraday": [0.35, 0.35, 0.3], # 35% at TP1, 35% at TP2, 30% at TP3
    "Swing": [0.3, 0.3, 0.4],      # 30% at TP1, 30% at TP2, 40% at TP3
}

def calculate_atr(candles, period=14):
    """
    Calculate the Average True Range (ATR) from candles
    
    Args:
        candles: List of candle dictionaries with 'high', 'low', 'close' keys
        period: ATR calculation period
        
    Returns:
        float: ATR value or None if not enough candles
    """
    if len(candles) < period + 1:
        return None

    try:
        highs = np.array([float(c['high']) for c in candles[-(period+1):]])
        lows = np.array([float(c['low']) for c in candles[-(period+1):]])
        closes = np.array([float(c['close']) for c in candles[-(period+1):]])

        # Calculate True Range series
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)

        # Calculate ATR as simple average of true ranges
        atr = np.mean(tr_list)
        return round(atr, 6)
    except Exception as e:
        log(f"❌ Error calculating ATR: {e}", level="ERROR")
        return None

def detect_volatility_regime(candles, lookback=20):
    """
    Detect volatility regime based on ATR changes
    
    Args:
        candles: List of candle dictionaries
        lookback: Period for volatility comparison
        
    Returns:
        str: Volatility regime ('low', 'normal', 'high')
    """
    if len(candles) < lookback * 2:
        return "normal"  # Default if not enough data
    
    try:
        # Calculate recent ATR
        recent_atr = calculate_atr(candles[-lookback:], period=lookback//2)
        
        # Calculate prior ATR (earlier period)
        prior_atr = calculate_atr(candles[-(lookback*2):-lookback], period=lookback//2)
        
        if not recent_atr or not prior_atr or prior_atr == 0:
            return "normal"
        
        # Calculate volatility ratio
        volatility_ratio = recent_atr / prior_atr
        
        # Categorize volatility
        if volatility_ratio < 0.8:
            return "low"
        elif volatility_ratio > 1.3:
            return "high"
        else:
            return "normal"
    except Exception as e:
        log(f"❌ Error detecting volatility regime: {e}", level="ERROR")
        return "normal"

def detect_price_momentum(candles, lookback=5):
    """
    Detect if price is showing strong momentum based on recent candles
    
    Args:
        candles: List of candle dictionaries
        lookback: Number of recent candles to analyze
        
    Returns:
        Tuple of (has_momentum: bool, direction: str, strength: float)
    """
    if len(candles) < lookback + 5:
        return False, None, 0.0
    
    try:
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
        prev_vol = sum(float(c['volume']) for c in candles[-(lookback+5):-lookback]) / len(recent)
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
    
    except Exception as e:
        log(f"❌ Error detecting price momentum: {e}", level="ERROR")
        return False, None, 0.0

def calculate_dynamic_sl_tp(candles_by_tf, entry_price, trade_type, direction, score, confidence, regime="trending", strategy="core_strategy"):
    """
    Calculate optimal SL/TP using ATR, volatility regime, confidence, and momentum
    
    Args:
        candles_by_tf: Dictionary of candles organized by timeframe
        entry_price: Entry price of the trade
        trade_type: "Scalp", "Intraday", or "Swing"
        direction: "long" or "short"
        score: Trade setup score (0-10)
        confidence: Confidence percentage (0-100)
        regime: Market regime ("trending", "ranging", "volatile")
        strategy: Trading strategy name
        
    Returns:
        Tuple of (stop_loss, take_profit, sl_percentage, trailing_percentage, tp_percentage, tp2, tp2_percentage, tp3, tp3_percentage)
    """
    # Select appropriate timeframe for ATR calculation
    tf_mapping = {
        "Scalp": '3', 
        "Intraday": '15', 
        "Swing": '60',
        "mean_reversion": '15',
        "breakout_sniper": '5'
    }
    
    selected_tf = tf_mapping.get(trade_type, '15')
    
    # Get candles for the selected timeframe
    candles = candles_by_tf.get(selected_tf, [])
    if not candles or len(candles) < 30:
        # Fallback to a different timeframe if preferred one is not available
        for tf in sorted(candles_by_tf.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            if len(candles_by_tf[tf]) >= 30:
                candles = candles_by_tf[tf]
                log(f"⚠️ Using fallback timeframe {tf} for {trade_type} SL/TP calculation", level="WARN")
                break
        
        if not candles or len(candles) < 30:
            # If still no valid candles, use fixed percentages
            log(f"⚠️ No valid candles for SL/TP calculation - using fixed percentages", level="WARN")
            sl_pct = 2.0  # 2% default SL
            tp_pct = sl_pct * TARGET_RR_RATIOS.get(trade_type, 2.0)  # Default RR ratio
            
            # Apply regime adjustments
            regime_factor = REGIME_ADJUSTMENTS.get(regime, REGIME_ADJUSTMENTS["trending"])
            sl_pct *= regime_factor["sl"]
            tp_pct *= regime_factor["tp"]
            
            # Calculate prices
            if direction.lower() == "long":
                sl_price = entry_price * (1 - sl_pct/100)
                tp_price = entry_price * (1 + tp_pct/100)
                tp2_price = entry_price * (1 + tp_pct/100 * 1.5)
                tp3_price = entry_price * (1 + tp_pct/100 * 2.0)
            else:  # short
                sl_price = entry_price * (1 + sl_pct/100)
                tp_price = entry_price * (1 - tp_pct/100)
                tp2_price = entry_price * (1 - tp_pct/100 * 1.5)
                tp3_price = entry_price * (1 - tp_pct/100 * 2.0)
            
            return (
                round(sl_price, 6), 
                round(tp_price, 6), 
                round(sl_pct, 2), 
                round(sl_pct * TRAILING_PERCENTAGE_MAP.get(trade_type, 0.5), 2),
                round(tp_pct, 2),
                round(tp2_price, 6),
                round(tp_pct * 1.5, 2),
                round(tp3_price, 6), 
                round(tp_pct * 2.0, 2)
            )
    
    # Calculate ATR
    atr = calculate_atr(candles, period=14)
    if not atr:
        log(f"⚠️ Failed to calculate ATR - using fixed percentages", level="WARN")
        sl_pct = 2.0
    else:
        # Adjust ATR factor based on confidence and score
        confidence_factor = 0.8 + (confidence / 100 * 0.6)  # 0.8-1.4 based on confidence
        score_factor = 0.8 + (score / 10 * 0.4)  # 0.8-1.2 based on score
        
        # Tighter stops for high confidence/score setups
        atr_factor = MAX_SL_ATR_FACTOR - (confidence_factor * score_factor)
        atr_factor = max(MIN_SL_ATR_FACTOR, min(atr_factor, MAX_SL_ATR_FACTOR))
        
        # Calculate SL distance as ATR-based percentage
        sl_distance = atr * atr_factor
        sl_pct = (sl_distance / entry_price) * 100
    
    # Check for momentum which will affect our targets
    has_momentum, momentum_direction, momentum_strength = detect_price_momentum(
        candles_by_tf.get('1', []) if '1' in candles_by_tf else candles
    )
    
    momentum_aligned = (direction.lower() == "long" and momentum_direction == "up") or \
                       (direction.lower() == "short" and momentum_direction == "down")
    
    # Apply minimum and maximum bounds to SL percentage
    sl_pct = max(MIN_SL_PERCENTAGE, min(sl_pct, MAX_SL_PERCENTAGE))
    
    # Apply market regime adjustments
    regime_factors = REGIME_ADJUSTMENTS.get(regime, REGIME_ADJUSTMENTS["trending"])
    sl_pct *= regime_factors["sl"]
    
    # Get target risk-reward ratio
    base_rr = TARGET_RR_RATIOS.get(strategy, TARGET_RR_RATIOS.get(trade_type, 2.0))
    
    # Adjust RR ratio based on momentum and regime
    if has_momentum and momentum_aligned:
        momentum_bonus = momentum_strength * 0.5  # 0-0.5 bonus factor
        base_rr += momentum_bonus
        log(f"🚀 Momentum aligned with {direction} trade: RR ratio increased by {momentum_bonus:.1f} to {base_rr:.1f}")
    
    # Apply regime adjustment to TP
    tp_factor = regime_factors["tp"]
    tp_pct = sl_pct * base_rr * tp_factor
    
    # Calculate additional TP levels
    tp2_pct = tp_pct * 1.5  # TP2 is 1.5x TP1
    tp3_pct = tp_pct * 2.0  # TP3 is 2x TP1
    
    # Calculate trailing percentage (adjusted by regime)
    trailing_factor = regime_factors["trailing"]
    trailing_pct = sl_pct * TRAILING_PERCENTAGE_MAP.get(trade_type, 0.5) * trailing_factor
    
    # Calculate actual prices
    if direction.lower() == "long":
        sl_price = entry_price * (1 - sl_pct/100)
        tp1_price = entry_price * (1 + tp_pct/100)
        tp2_price = entry_price * (1 + tp2_pct/100)
        tp3_price = entry_price * (1 + tp3_pct/100)
    else:  # short
        sl_price = entry_price * (1 + sl_pct/100)
        tp1_price = entry_price * (1 - tp_pct/100)
        tp2_price = entry_price * (1 - tp2_pct/100)
        tp3_price = entry_price * (1 - tp3_pct/100)
    
    # Log detailed calculation
    log(f"📊 SL/TP calculation for {direction} {trade_type} in {regime} regime:")
    log(f"  Entry: {entry_price} | ATR: {atr if atr else 'N/A'} | ATR Factor: {atr_factor if atr else 'N/A'}")
    log(f"  SL%: {sl_pct:.2f}% | TP1%: {tp_pct:.2f}% | RR: {base_rr:.1f} | Trailing%: {trailing_pct:.2f}%")
    
    return (
        round(sl_price, 6),
        round(tp1_price, 6),
        round(sl_pct, 2),
        round(trailing_pct, 2),
        round(tp_pct, 2),
        round(tp2_price, 6),
        round(tp2_pct, 2),
        round(tp3_price, 6),
        round(tp3_pct, 2)
    )

def calculate_exit_tranches(symbol, total_qty, trade_type="Intraday", volatility="normal", momentum=False):
    """
    Calculate position size for each exit tranche
    
    Args:
        symbol: Trading symbol for precision lookup
        total_qty: Total position size
        trade_type: "Scalp", "Intraday", or "Swing"
        volatility: Volatility level ("low", "normal", "high")
        momentum: Flag for momentum presence
        
    Returns:
        List of quantities for each tranche
    """
    if total_qty <= 0:
        return []
    
    # Get symbol precision for rounding
    precision = get_precision(symbol)
    min_qty = 0.001  # Fallback min quantity
    
    # Get base distribution by trade type
    distribution = EXIT_TRANCHES.get(trade_type, [0.33, 0.33, 0.34])
    
    # Adjust for volatility
    if volatility == "high":
        # In high volatility, secure more profit early
        distribution = [d * 1.2 if i == 0 else d * 0.9 for i, d in enumerate(distribution)]
    elif volatility == "low":
        # In low volatility, aim for bigger targets
        distribution = [d * 0.9 if i == 0 else d * 1.05 for i, d in enumerate(distribution)]
    
    # Adjust for momentum
    if momentum:
        # In momentum, keep more for the final target
        distribution = [d * 0.8 if i < 2 else d * 1.4 for i, d in enumerate(distribution)]
    
    # Normalize distribution to sum to 1.0
    total = sum(distribution)
    if total > 0:
        distribution = [d / total for d in distribution]
    
    # Calculate raw tranches
    raw_tranches = [total_qty * dist for dist in distribution]
    
    # Round to valid quantities
    valid_tranches = []
    running_total = 0
    
    for i, qty in enumerate(raw_tranches):
        if i == len(raw_tranches) - 1:
            # Make sure final tranche captures any rounding errors
            final_qty = round_qty(symbol, total_qty - running_total)
            if final_qty >= min_qty:
                valid_tranches.append(final_qty)
        else:
            rounded_qty = round_qty(symbol, qty)
            if rounded_qty >= min_qty:
                valid_tranches.append(rounded_qty)
                running_total += rounded_qty
    
    # Ensure we have at least one valid tranche
    if not valid_tranches:
        valid_tranches = [total_qty]
    
    log(f"📊 Exit tranches for {symbol} ({trade_type}, {volatility}, momentum={momentum}): {valid_tranches}")
    return valid_tranches

async def validate_sl_placement(symbol, direction, sl_price, market_type="linear"):
    """
    Validate that a stop loss price is on the correct side of current market price
    
    Args:
        symbol: Trading symbol
        direction: "long" or "short"
        sl_price: Proposed stop loss price
        market_type: Exchange market type
        
    Returns:
        float: Corrected SL price or original if already valid
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
        
        # Add safety buffer (increased to 1.0% from 0.5% for more reliable stop placement)
        buffer_pct = 0.01  # 1.0%
        
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
        log(traceback.format_exc(), level="ERROR")
        return sl_price  # Return original if validation fails

def calculate_smart_trailing_stop(symbol, entry_price, current_price, direction, candles, base_trail_pct=0.5):
    """
    Calculate an adaptive trailing stop based on volatility and momentum
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price
        current_price: Current market price
        direction: 'long' or 'short'
        candles: Recent candles for analysis
        base_trail_pct: Base trailing percentage
        
    Returns:
        float: Calculated stop loss price
    """
    try:
        # Basic move calculation
        price_move = 0
        if direction.lower() == "long":
            price_move = current_price - entry_price
            if price_move <= 0:
                return None  # No trailing until in profit
        else:  # short
            price_move = entry_price - current_price
            if price_move <= 0:
                return None  # No trailing until in profit
        
        # Determine relative profit percentage
        profit_pct = (price_move / entry_price) * 100
        
        # Volatility-based adjustment
        volatility_factor = 1.0
        
        # Detect volatility regime
        volatility = detect_volatility_regime(candles if candles else [])
        if volatility == "high":
            volatility_factor = 1.5  # Wider trailing in high volatility
        elif volatility == "low":
            volatility_factor = 0.8  # Tighter trailing in low volatility
        
        # Check for momentum
        has_momentum, momentum_direction, momentum_strength = detect_price_momentum(candles if candles else [])
        momentum_aligned = (direction.lower() == "long" and momentum_direction == "up") or \
                           (direction.lower() == "short" and momentum_direction == "down")
        
        if has_momentum and momentum_aligned:
            # Momentum-based adjustment - looser trailing to let profits run
            momentum_factor = 1.0 + (momentum_strength * 0.5)  # 1.0-1.5
            volatility_factor *= momentum_factor
            log(f"🚀 Momentum detected for {symbol} - using wider trail: {momentum_factor:.2f}x")
        
        # Profit-based adjustment (trailing width increases with profit)
        profit_factor = 1.0
        if profit_pct > 5.0:
            profit_factor = 1.2  # Wider trail for bigger winners
        elif profit_pct > 10.0:
            profit_factor = 1.5  # Even wider trail for huge winners
        
        # Combine all factors
        adjustment_factor = min(max(volatility_factor * profit_factor, 0.8), 2.0)
        adjusted_trail_pct = base_trail_pct * adjustment_factor
        
        # Calculate actual SL price
        if direction.lower() == "long":
            sl_price = current_price * (1 - (adjusted_trail_pct / 100))
        else:  # short
            sl_price = current_price * (1 + (adjusted_trail_pct / 100))
        
        return round(sl_price, 6)
        
    except Exception as e:
        log(f"❌ Error calculating smart trailing stop: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        
        # Fallback to simple trailing calculation
        try:
            if direction.lower() == "long":
                return round(current_price * (1 - (base_trail_pct / 100)), 6)
            else:
                return round(current_price * (1 + (base_trail_pct / 100)), 6)
        except:
            return None

def should_trail_stop(symbol, entry_price, current_price, direction, candles=None, trailing_pct=0.5):
    """
    Determine if trailing stop should be activated and calculate new stop price
    
    Args:
        symbol: Trading symbol
        entry_price: Trade entry price
        current_price: Current market price
        direction: 'long' or 'short'
        candles: Recent candles for analysis
        trailing_pct: Base trailing percentage
        
    Returns:
        float or None: New stop loss price if trailing should activate, None otherwise
    """
    try:
        # Check if we've reached the activation threshold
        if direction.lower() == "long":
            activation_threshold = entry_price * (1 + TRAILING_ACTIVATION_THRESHOLD/100)
            if current_price < activation_threshold:
                return None  # Not enough move to activate trailing
        else:  # short
            activation_threshold = entry_price * (1 - TRAILING_ACTIVATION_THRESHOLD/100)
            if current_price > activation_threshold:
                return None  # Not enough move to activate trailing
        
        # Calculate the new trailing stop price
        return calculate_smart_trailing_stop(
            symbol=symbol,
            entry_price=entry_price,
            current_price=current_price,
            direction=direction,
            candles=candles,
            base_trail_pct=trailing_pct
        )
    
    except Exception as e:
        log(f"❌ Error in trailing stop logic: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

def calculate_breakeven_after_move(entry_price, direction, move_pct=1.0):
    """
    Calculate breakeven price after a certain percentage move in favor
    
    Args:
        entry_price: Trade entry price
        direction: "long" or "short"
        move_pct: Percentage move required before setting breakeven
        
    Returns:
        float: Breakeven price (usually entry, but can include buffer)
    """
    try:
        # Calculate the trigger price
        if direction.lower() == "long":
            trigger_price = entry_price * (1 + move_pct/100)
        else:
            trigger_price = entry_price * (1 - move_pct/100)
        
        # Include a small buffer (0.1%) to account for fees and spread
        buffer = entry_price * 0.001
        
        # Calculate breakeven with buffer
        if direction.lower() == "long":
            return entry_price + buffer
        else:
            return entry_price - buffer
            
    except Exception as e:
        log(f"❌ Error calculating breakeven: {e}", level="ERROR")
        return entry_price  # Return exact entry price if calculation fails

def adjust_profit_protection(symbol, entry_price, current_price, direction, trade_type="Intraday"):
    """
    Adjust stop loss based on profit milestones reached
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price
        current_price: Current price
        direction: 'long' or 'short'
        trade_type: Trade type for milestone selection
        
    Returns:
        float or None: New stop loss price or None if no adjustment needed
    """
    try:
        precision = get_precision(symbol)
        
        if not entry_price or entry_price <= 0:
            return None
            
        # Calculate current profit percentage
        if direction.lower() == "long":
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:  # short
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Define profit protection milestones based on trade type
        milestones = {
            "Scalp": [
                {"pct": 2.0, "sl_at": 0.3},  # At 2% profit, move SL to 0.3% profit
                {"pct": 3.0, "sl_at": 1.0},  # At 3% profit, move SL to 1.0% profit
                {"pct": 5.0, "sl_at": 2.0}   # At 5% profit, move SL to 2.0% profit
            ],
            "Intraday": [
                {"pct": 3.0, "sl_at": 0.5},  # At 3% profit, move SL to 0.5% profit
                {"pct": 5.0, "sl_at": 1.5},  # At 5% profit, move SL to 1.5% profit
                {"pct": 8.0, "sl_at": 3.0}   # At 8% profit, move SL to 3.0% profit
            ],
            "Swing": [
                {"pct": 5.0, "sl_at": 1.0},   # At 5% profit, move SL to 1.0% profit
                {"pct": 8.0, "sl_at": 2.5},   # At 8% profit, move SL to 2.5% profit
                {"pct": 12.0, "sl_at": 5.0}   # At 12% profit, move SL to 5.0% profit
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
                
            return round(new_sl, precision)
            
        return None
        
    except Exception as e:
        log(f"❌ Error in profit protection: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

def should_exit_by_time(trade, current_time=None, candles=None):
    """
    Check if trade should be exited based on time elapsed
    
    Args:
        trade: Trade data dictionary
        current_time: Current datetime (uses now if None)
        candles: Recent candles for momentum detection
        
    Returns:
        bool: True if trade should be exited
    """
    from datetime import datetime
    
    if not current_time:
        current_time = datetime.utcnow()
    
    try:
        # Get trade entry time
        entry_time_str = trade.get("timestamp")
        if not entry_time_str:
            return False
            
        entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
        trade_age_hours = (current_time - entry_time).total_seconds() / 3600
        
        trade_type = trade.get("trade_type", "Intraday")
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
        log(traceback.format_exc(), level="ERROR")
    
    return False

def evaluate_score_exit(symbol, scores, min_exit_cycles=3, trade_type="Intraday"):
    """
    Evaluate whether to exit based on score deterioration pattern
    
    Args:
        symbol: Trading symbol
        scores: List of historical scores
        min_exit_cycles: Minimum cycles before considering exit
        trade_type: Trade type for threshold adjustment
        
    Returns:
        bool: True if exit is recommended based on score trend
    """
    try:
        # Guard clauses
        if len(scores) < min_exit_cycles:
            return False
            
        # Thresholds by trade type
        thresholds = {
            "Scalp": 5.0,      # Exit if sustained below 5.0
            "Intraday": 4.5,   # Exit if sustained below 4.5
            "Swing": 4.0       # Exit if sustained below 4.0
        }
        
        threshold = thresholds.get(trade_type, 4.5)
        
        # Get recent scores
        recent_scores = scores[-min_exit_cycles:]
        
        # Calculate peak score and current score
        max_score = max(scores)
        current_score = scores[-1]
        absolute_drop = max_score - current_score
        relative_drop = (absolute_drop / max_score) * 100 if max_score > 0 else 0
        
        # Check if scores are consistently declining
        is_deteriorating = all(recent_scores[i] >= recent_scores[i+1] for i in range(len(recent_scores)-1))
        
        # Exit criteria:
        # 1. All recent scores below threshold
        # 2. Current score significantly lower than peak (30%+ drop)
        # 3. Consistent deterioration in recent cycles
        below_threshold = all(s < threshold for s in recent_scores)
        significant_drop = relative_drop >= 30 and absolute_drop >= 2.0
        
        should_exit = below_threshold and significant_drop and is_deteriorating
        
        if should_exit:
            log(f"📉 Score deterioration exit for {symbol}: Current: {current_score:.2f}, Peak: {max_score:.2f}, " 
                f"Drop: {absolute_drop:.2f} ({relative_drop:.1f}%), Threshold: {threshold}")
        
        return should_exit
        
    except Exception as e:
        log(f"❌ Error evaluating score exit: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False
