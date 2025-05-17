from volume import is_volume_spike
from macd import detect_macd_cross
from rsi import calculate_rsi

def score_breakout_sniper(symbol, candles_by_tf, regime):
    """
    Score a potential breakout setup
    Returns score, direction, confidence, and reasons dictionary
    """
    # Exit early if not in volatile regime
    if regime != "volatile":
        return 0, None, 0, {"reason": "Not volatile regime"}

    tf = "5"
    candles = candles_by_tf.get(tf)
    if not candles or len(candles) < 30:
        return 0, None, 0, {"reason": "Not enough candles"}

    close = float(candles[-1]["close"])
    high = float(candles[-1]["high"])
    low = float(candles[-1]["low"])
    open_price = float(candles[-1]["open"])
    body_size = abs(close - open_price)
    full_range = high - low

    if full_range == 0:
        return 0, None, 0, {"reason": "Zero range candle"}

    body_ratio = body_size / full_range
    prev_highs = [float(c["high"]) for c in candles[-21:-1]]
    prev_lows = [float(c["low"]) for c in candles[-21:-1]]

    volume_ok = is_volume_spike(candles, multiplier=2)
    momentum_ok = body_ratio > 0.7

    breakout_up = close > max(prev_highs)
    breakout_down = close < min(prev_lows)

    macd = detect_macd_cross(candles)
    rsi_vals = calculate_rsi(candles)
    rsi = rsi_vals[-1] if rsi_vals else 50

    score = 0
    direction = None
    reasons = {}

    if breakout_up:
        score += 2
        direction = "Long"
        reasons["breakout_up"] = True
    elif breakout_down:
        score += 2
        direction = "Short"
        reasons["breakout_down"] = True
    else:
        # FIX: Early exit if no breakout detected
        from logger import log
        log(f"⚠️ No breakout detected for {symbol}")
        return 0, None, 0, {"reason": "No breakout detected"}

    if volume_ok:
        score += 1
        reasons["volume_spike"] = True

    if momentum_ok:
        score += 1
        reasons["momentum_body"] = True

    if (macd == "bullish" and direction == "Long") or (macd == "bearish" and direction == "Short"):
        score += 1
        reasons["macd_confirmation"] = macd

    if direction == "Long" and rsi > 55:
        score += 1
        reasons["rsi_trend"] = rsi
    elif direction == "Short" and rsi < 45:
        score += 1
        reasons["rsi_trend"] = rsi

    # FIX: Add a clear minimum threshold for this strategy
    min_breakout_score = 4.0
    if score < min_breakout_score:
        from logger import log
        log(f"⚠️ Breakout score for {symbol} too low: {score:.2f} < {min_breakout_score}")
        return 0, None, 0, {"reason": f"Score too low: {score}"}

    # FIX: Ensure we have at least 3 reasons
    if len(reasons) < 3:
        from logger import log
        log(f"⚠️ Breakout for {symbol} has insufficient indicators: {len(reasons)} < 3")
        return 0, None, 0, {"reason": "Not enough confirmation indicators"}

    confidence = round((score / 6) * 100)
    
    from logger import log
    log(f"✅ Valid breakout setup for {symbol}: Score {score:.2f}, Dir: {direction}, Conf: {confidence}%")
    
    return score, direction, confidence, reasons
