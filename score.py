from rsi import calculate_rsi
from macd import detect_macd_cross
from supertrend import calculate_supertrend_signal
from ema import detect_ema_crossover
from bollinger import calculate_bollinger_bands
from pattern_detector import detect_pattern
from volume import is_volume_spike, get_average_volume
from stealth_detector import detect_volume_divergence, detect_slow_breakout
from whale_detector import detect_whale_activity
from error_handler import send_error_to_telegram
from config import ALWAYS_ALLOW_SWING
from logger import log

# Enhanced weights to better identify potential pumps
WEIGHTS = {
    "macd": 1.5,
    "ema": 1.0,
    "volume_spike": 1.2,  # Increased weight for volume spikes
    "supertrend": 1.0,
    "rsi": 1.0,
    "bollinger": 0.5,
    "pattern": 0.7,   # Increased pattern weight
    "divergence": 0.5,
    "slow_breakout": 0.8,  # Increased for early detection of breakouts
    "whale": 1.3,     # Increased whale activity weight
    "momentum": 1.5,  # New weight for momentum detection
}

# Timeframe mapping for trade types
TRADE_TYPE_TF = {
    "Scalp": ["1", "3"],
    "Intraday": ["5", "15"],
    "Swing": ["30", "60", "240"],
}

MIN_TF_REQUIRED = {
    "Scalp": 1,
    "Intraday": 1,
    "Swing": 1,
}

def detect_momentum_strength(candles, lookback=5):
    """
    Detect price momentum strength and direction from recent candles
    Returns tuple of (has_momentum, direction, strength)
    """
    if len(candles) < lookback + 5:
        return False, None, 0
        
    recent = candles[-lookback:]
    prior = candles[-(lookback+5):-lookback]
    
    # Calculate recent volume vs prior
    recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
    prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
    vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
    
    # Calculate price direction and consecutive candles
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
    direction = "bullish" if price_change_pct > 0 else "bearish"
    
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

def score_symbol(symbol, candles_by_timeframe):
    if symbol == "FOOUSDT":
        tf_scores = {"1": -3.0, "3": -3.0, "5": -2.0}
        indicator_scores = {"1m_macd": -1.5, "1m_ema": -1.0, "1m_volume": 1.0}
        used_indicators = ["macd", "ema", "volume"]
        return 9.5, tf_scores, "Scalp", indicator_scores, used_indicators

    tf_scores = {}
    type_scores = {"Scalp": 0, "Intraday": 0, "Swing": 0}
    tf_count = {"Scalp": 0, "Intraday": 0, "Swing": 0}
    indicator_scores = {}
    used_indicators = set()
    
    # Check for momentum across timeframes
    momentum_data = {
        "1m": detect_momentum_strength(candles_by_timeframe.get("1", [])),
        "5m": detect_momentum_strength(candles_by_timeframe.get("5", [])),
        "15m": detect_momentum_strength(candles_by_timeframe.get("15", []))
    }
    
    # Aggregate momentum data across timeframes
    has_momentum = any(data[0] for tf, data in momentum_data.items() if data[0])
    momentum_direction = next((data[1] for tf, data in momentum_data.items() if data[0]), None)
    
    if has_momentum:
        log(f"🚀 Momentum detected for {symbol}: {momentum_direction} direction")

    for tf, candles in candles_by_timeframe.items():
        score = 0
        tf_label = f"{tf}m"

        try:
            # Check volume first as a basic filter
            if not is_volume_spike(candles, 2.5):
                avg_vol = get_average_volume(candles)
                if avg_vol and avg_vol < 1000:
                    tf_scores[tf] = -99.0
                    continue
            
            # Add momentum score if present
            tf_momentum = detect_momentum_strength(candles)
            if tf_momentum[0]:  # If momentum exists
                momentum_score = WEIGHTS["momentum"] * tf_momentum[2]  # Weight * strength
                score += momentum_score
                indicator_scores[f"{tf_label}_momentum"] = momentum_score
                used_indicators.add("momentum")

            if tf in TRADE_TYPE_TF["Scalp"]:
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                pattern = detect_pattern(candles)
                if is_volume_spike(candles, 2.5):
                    score += WEIGHTS["volume_spike"]
                    indicator_scores[f"{tf_label}_volume"] = WEIGHTS["volume_spike"]
                if macd == "bullish":
                    score += WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = WEIGHTS["macd"]
                elif macd == "bearish":
                    score -= WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = -WEIGHTS["macd"]
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                if pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                if detect_volume_divergence(candles):
                    score += WEIGHTS["divergence"]
                    indicator_scores[f"{tf_label}_divergence"] = WEIGHTS["divergence"]
                if detect_slow_breakout(candles):
                    score += WEIGHTS["slow_breakout"]
                    indicator_scores[f"{tf_label}_slow_breakout"] = WEIGHTS["slow_breakout"]
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                type_scores["Scalp"] += score
                tf_count["Scalp"] += 1
                used_indicators.update(["macd", "ema", "volume", "pattern", "divergence", "slow_breakout", "whale"])

            elif tf in TRADE_TYPE_TF["Intraday"]:
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                trend = calculate_supertrend_signal(candles)
                pattern = detect_pattern(candles)
                if is_volume_spike(candles, 2.5):
                    score += WEIGHTS["volume_spike"]
                    indicator_scores[f"{tf_label}_volume"] = WEIGHTS["volume_spike"]
                if macd == "bullish":
                    score += WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = WEIGHTS["macd"]
                elif macd == "bearish":
                    score -= WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = -WEIGHTS["macd"]
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                if trend == "bullish":
                    score += WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = WEIGHTS["supertrend"]
                elif trend == "bearish":
                    score -= WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = -WEIGHTS["supertrend"]
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                if pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                if detect_volume_divergence(candles):
                    score += WEIGHTS["divergence"]
                    indicator_scores[f"{tf_label}_divergence"] = WEIGHTS["divergence"]
                if detect_slow_breakout(candles):
                    score += WEIGHTS["slow_breakout"]
                    indicator_scores[f"{tf_label}_slow_breakout"] = WEIGHTS["slow_breakout"]
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                type_scores["Intraday"] += score
                tf_count["Intraday"] += 1
                used_indicators.update(["macd", "ema", "supertrend", "volume", "pattern", "divergence", "slow_breakout", "whale"])

            elif tf in TRADE_TYPE_TF["Swing"]:
                rsi_vals = calculate_rsi(candles)
                if rsi_vals:
                    rsi = rsi_vals[-1]
                    if rsi < 30:
                        score += WEIGHTS["rsi"]
                        indicator_scores[f"{tf_label}_rsi"] = WEIGHTS["rsi"]
                    elif rsi > 70:
                        score -= WEIGHTS["rsi"]
                        indicator_scores[f"{tf_label}_rsi"] = -WEIGHTS["rsi"]
                trend = calculate_supertrend_signal(candles)
                ema = detect_ema_crossover(candles)
                bb = calculate_bollinger_bands(candles)
                pattern = detect_pattern(candles)
                if trend == "bullish":
                    score += WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = WEIGHTS["supertrend"]
                elif trend == "bearish":
                    score -= WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = -WEIGHTS["supertrend"]
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                if bb and bb[-1]:
                    close = float(candles[-1]["close"])
                    if close < bb[-1]["lower"]:
                        score += WEIGHTS["bollinger"]
                        indicator_scores[f"{tf_label}_bollinger"] = WEIGHTS["bollinger"]
                    elif close > bb[-1]["upper"]:
                        score -= WEIGHTS["bollinger"]
                        indicator_scores[f"{tf_label}_bollinger"] = -WEIGHTS["bollinger"]
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                if pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                type_scores["Swing"] += score
                tf_count["Swing"] += 1
                used_indicators.update(["rsi", "ema", "supertrend", "bollinger", "pattern", "whale"])

        except Exception as e:
            from logger import log
            log(f"❌ Scoring error for {symbol} [{tf}m]: {str(e)}", level="ERROR")

        tf_scores[tf] = round(score, 2)
    
    # Add momentum information to timeframe scores
    if has_momentum:
        tf_scores["momentum"] = 1.5
        if "momentum" not in used_indicators:
            used_indicators.add("momentum")

    valid_types = [t for t in type_scores if tf_count[t] >= MIN_TF_REQUIRED[t]]
    best_type = max(valid_types, key=lambda t: type_scores[t], default="Scalp")
    best_score = type_scores[best_type]
    
    # Bonus for aligned momentum with strong scores
    if has_momentum and best_score > 6.0:
        expected_direction = "bullish" if determine_direction(tf_scores) == "Long" else "bearish"
        if momentum_direction == expected_direction:
            bonus = 0.8  # Bonus for aligned momentum and trade direction
            best_score += bonus
            log(f"🚀 Momentum bonus applied to {symbol}: +{bonus} (aligned {momentum_direction})")

    return round(best_score, 2), tf_scores, best_type, indicator_scores, list(used_indicators)

def determine_direction(tf_scores):
    values = list(tf_scores.values())
    # Remove momentum from direction calculation
    if "momentum" in tf_scores:
        values.remove(tf_scores["momentum"])
        
    negative_count = sum(1 for v in values if v < 0)
    total = sum(values)
    return "Short" if negative_count >= len(values) // 2 and total < 0 else "Long"

def calculate_confidence(score, tf_scores, trend_context, trade_type):
    """
    Calculate confidence percentage with enhanced momentum support
    """
    max_score = 10 if trade_type == "Scalp" else (15 if trade_type == "Intraday" else 20)
    
    # Apply trend boost based on BTC trend
    trend_boost = 2 if trend_context.get("btc_trend") == "strong" or trend_context.get("altseason") else 0
    
    # Count aligned timeframes
    tf_alignment = sum(1 for s in tf_scores.values() if s > 0)
    
    # Add momentum bonus to confidence if present
    momentum_bonus = 3 if "momentum" in tf_scores else 0
    
    # Calculate base confidence
    base_confidence = (score + trend_boost + tf_alignment + momentum_bonus) / (max_score + 3 + 3) * 100

    # Adjust for market regime
    regime = trend_context.get("regime", "trending")
    if regime == "ranging":
        base_confidence *= 0.9
    elif regime == "trending" and trend_context.get("altseason"):
        base_confidence *= 1.05
    elif regime == "volatile":
        # Higher confidence in volatile markets if score is high (potential pumps)
        if score > 7:
            base_confidence *= 1.1
        else:
            base_confidence *= 0.95
            
    # Cap confidence at 100%
    return round(min(base_confidence, 100), 1)

def has_pump_potential(candles_by_tf, direction):
    """
    Analyze if a setup has potential for a large pump
    Returns true if setup shows signs of imminent large move
    """
    # Check for momentum across multiple timeframes
    momentum_1m = detect_momentum_strength(candles_by_tf.get("1", []))
    momentum_5m = detect_momentum_strength(candles_by_tf.get("5", []))
    
    # Check for whale activity
    whale_activity = detect_whale_activity(candles_by_tf.get("5", []))
    
    # Check for volume anomalies
    volume_spike = is_volume_spike(candles_by_tf.get("1", []), 3.0)  # 3x normal volume
    
    # Check patterns
    pattern_1m = detect_pattern(candles_by_tf.get("1", []))
    pattern_5m = detect_pattern(candles_by_tf.get("5", []))
    
    # Strong pattern combination
    breakout_patterns = ["hammer", "bullish_engulfing", "morning_star"] if direction == "Long" else ["inverted_hammer", "bearish_engulfing", "evening_star"]
    has_breakout_pattern = pattern_1m in breakout_patterns or pattern_5m in breakout_patterns
    
    # Count positive signals
    signals = [
        momentum_1m[0],  # Has momentum on 1m
        momentum_5m[0],  # Has momentum on 5m
        whale_activity,  # Whale activity detected
        volume_spike,    # Volume spike detected
        has_breakout_pattern  # Has breakout pattern
    ]
    
    signal_count = sum(1 for s in signals if s)
    
    # Need at least 3 strong signals for pump potential
    return signal_count >= 3

