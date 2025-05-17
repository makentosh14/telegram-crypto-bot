from bollinger import calculate_bollinger_bands
from rsi import calculate_rsi
from whale_detector import detect_whale_activity
from volume import get_average_volume
from pattern_detector import detect_pattern

def score_mean_reversion(symbol, candles_by_tf, regime):
    """
    Score a potential mean reversion setup
    
    Args:
        symbol: Trading pair symbol
        candles_by_tf: Dictionary of candles by timeframe
        regime: Market regime (should be 'ranging' for this strategy)
        
    Returns:
        score, direction, confidence, reasons dictionary
    """
    # Early exit if not in ranging regime
    if regime != "ranging":
        return 0, "Not Ranging", "N/A", {}

    tf_to_check = ["5", "15"]
    score = 0
    reasons = {}
    direction = None

    for tf in tf_to_check:
        candles = candles_by_tf.get(tf)
        if not candles or len(candles) < 30:
            continue

        close = float(candles[-1]["close"])
        rsi_vals = calculate_rsi(candles)
        bb = calculate_bollinger_bands(candles)
        pattern = detect_pattern(candles)
        avg_vol = get_average_volume(candles)

        if not rsi_vals or not bb or not bb[-1]:
            continue

        rsi = rsi_vals[-1]
        lower = bb[-1]["lower"]
        upper = bb[-1]["upper"]

        # Check for lower Bollinger band breakout and oversold RSI
        if close < lower and rsi < 30:
            direction = "Long"
            score += 2
            reasons[f"{tf}m_boll_rsi_long"] = True

        # Check for upper Bollinger band breakout and overbought RSI
        if close > upper and rsi > 70:
            direction = "Short"
            score += 2
            reasons[f"{tf}m_boll_rsi_short"] = True

        if pattern in ["hammer", "inside_bar"]:
            score += 0.5
            reasons[f"{tf}m_pattern_support"] = pattern

        if pattern in ["inverted_hammer", "bearish_engulfing"]:
            score += 0.5
            reasons[f"{tf}m_pattern_resist"] = pattern

        if avg_vol and avg_vol < 1000:
            score -= 1
            reasons[f"{tf}m_low_vol"] = True

        if detect_whale_activity(candles):
            score += 1
            reasons[f"{tf}m_whale"] = True

    # FIX: Add a clear minimum threshold for this strategy
    min_mean_reversion_score = 4.0
    if score < min_mean_reversion_score:
        from logger import log
        log(f"⚠️ Mean reversion score for {symbol} too low: {score:.2f} < {min_mean_reversion_score}")
        return 0, "Score too low", 0, {}
    
    # Only return results if we have sufficient reasons
    if len(reasons) < 2:
        from logger import log
        log(f"⚠️ Mean reversion for {symbol} has insufficient indicators: {len(reasons)} < 2")
        return 0, "Not enough indicators", 0, {}

    confidence = round((score / 5) * 100)
    
    # FIX: Ensure we have a direction before returning a valid score
    if not direction:
        from logger import log
        log(f"⚠️ Mean reversion for {symbol} has no clear direction")
        return 0, "No direction", 0, {}
        
    from logger import log
    log(f"✅ Valid mean reversion setup for {symbol}: Score {score:.2f}, Dir: {direction}, Conf: {confidence}%")
    
    return score, direction, confidence, reasons
