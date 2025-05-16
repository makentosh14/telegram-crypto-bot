from bollinger import calculate_bollinger_bands
from rsi import calculate_rsi
from whale_detector import detect_whale_activity
from volume import get_average_volume
from pattern_detector import detect_pattern

def score_mean_reversion(symbol, candles_by_tf, regime):
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

    confidence = round((score / 5) * 100)
    return score, direction, confidence, reasons
