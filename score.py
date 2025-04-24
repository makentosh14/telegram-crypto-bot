from rsi import calculate_rsi
from macd import detect_macd_cross
from supertrend import calculate_supertrend_signal
from ema import detect_ema_crossover
from bollinger import calculate_bollinger_bands
from pattern_detector import detect_pattern
from volume import is_volume_spike
from stealth_detector import detect_volume_divergence, detect_slow_breakout
from whale_detector import detect_whale_activity

# Scoring logic per timeframe and trade type
def score_symbol(symbol, candles_by_timeframe):
    tf_scores = {}
    short_score, mid_score, long_score = 0, 0, 0

    for tf, candles in candles_by_timeframe.items():
        score = 0
        tf_int = int(tf)

        # --- SCALP STRATEGY: 1m, 3m ---
        if tf_int in [1, 3]:
            if is_volume_spike(candles, 2.5): score += 1.5
            if detect_macd_cross(candles) == "bullish": score += 2.0
            if detect_macd_cross(candles) == "bearish": score -= 2.0
            if detect_ema_crossover(candles) == "bullish": score += 1.5
            if detect_ema_crossover(candles) == "bearish": score -= 1.5
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 1.0
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 1.0
            if detect_volume_divergence(candles): score += 1.0
            if detect_slow_breakout(candles): score += 1.0
            if detect_whale_activity(candles): score += 1.5
            short_score += score

        # --- INTRADAY STRATEGY: 5m, 15m ---
        elif tf_int in [5, 15]:
            if is_volume_spike(candles, 2.5): score += 1.5
            if detect_macd_cross(candles) == "bullish": score += 2.0
            if detect_macd_cross(candles) == "bearish": score -= 2.0
            if calculate_supertrend_signal(candles) == "bullish": score += 1.5
            if calculate_supertrend_signal(candles) == "bearish": score -= 1.5
            if detect_ema_crossover(candles) == "bullish": score += 1.5
            if detect_ema_crossover(candles) == "bearish": score -= 1.5
            if detect_volume_divergence(candles): score += 1.0
            if detect_slow_breakout(candles): score += 1.0
            if detect_whale_activity(candles): score += 1.5
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 1.0
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 1.0
            mid_score += score

        # --- SWING STRATEGY: 30m, 1h, 4h ---
        elif tf_int in [30, 60, 240]:
            rsi_vals = calculate_rsi(candles)
            if rsi_vals:
                latest_rsi = rsi_vals[-1]
                if latest_rsi < 30: score += 1.5
                elif latest_rsi > 70: score -= 1.5
            if calculate_supertrend_signal(candles) == "bullish": score += 1.5
            if calculate_supertrend_signal(candles) == "bearish": score -= 1.5
            if detect_ema_crossover(candles) == "bullish": score += 1.5
            if detect_ema_crossover(candles) == "bearish": score -= 1.5
            bb = calculate_bollinger_bands(candles)
            if bb and bb[-1]:
                close = float(candles[-1]["close"])
                if close > bb[-1]["upper"]: score += 1.0
                elif close < bb[-1]["lower"]: score -= 1.0
            if detect_whale_activity(candles): score += 1.5
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 1.0
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 1.0
            long_score += score

        tf_scores[tf] = score

    if short_score >= mid_score and short_score >= long_score:
        return short_score, tf_scores, "Scalp"
    elif mid_score >= short_score and mid_score >= long_score:
        return mid_score, tf_scores, "Intraday"
    else:
        return long_score, tf_scores, "Swing"

# Direction logic
def determine_direction(tf_scores):
    values = list(tf_scores.values())
    negative_count = sum(1 for v in values if v < 0)
    total = sum(values)
    if negative_count >= len(tf_scores) // 2 and total < 0:
        return "Short"
    return "Long"

# Confidence scoring
def calculate_confidence(score, tf_scores, trend_context, trade_type):
    max_score = 12 if trade_type == "Scalp" else (18 if trade_type == "Intraday" else 24)
    trend_boost = 2 if trend_context['btc_trend'] == "strong" or trend_context['altseason'] else 0
    tf_alignment = sum(1 for s in tf_scores.values() if s > 0)
    confidence = (score + trend_boost + tf_alignment) / (max_score + 3) * 100
    return round(min(confidence, 100), 1)
