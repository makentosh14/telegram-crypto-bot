from rsi import calculate_rsi
from macd import detect_macd_cross
from supertrend import calculate_supertrend_signal
from ema import detect_ema_crossover
from bollinger import calculate_bollinger_bands
from pattern_detector import detect_pattern
from volume import is_volume_spike
from stealth_detector import detect_volume_divergence, detect_slow_breakout
from whale_detector import detect_whale_activity

# Weighted scoring function (optimized per trade type)
def score_symbol(symbol, candles_by_timeframe):
    total_score = 0
    tf_scores = {}

    for tf, candles in candles_by_timeframe.items():
        score = 0
        tf_int = int(tf)

        # --- SCALP STRATEGY: 1m, 3m ---
        if tf_int in [1, 3]:
            if is_volume_spike(candles, 2.5): score += 1.0
            if detect_macd_cross(candles) == "bullish": score += 1.5
            if detect_macd_cross(candles) == "bearish": score -= 1.5
            if detect_ema_crossover(candles) == "bullish": score += 1.0
            if detect_ema_crossover(candles) == "bearish": score -= 1.0
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5
            if detect_volume_divergence(candles): score += 0.5

        # --- INTRADAY STRATEGY: 5m, 15m ---
        elif tf_int in [5, 15]:
            if is_volume_spike(candles, 2.5): score += 1.0
            if detect_macd_cross(candles) == "bullish": score += 1.5
            if detect_macd_cross(candles) == "bearish": score -= 1.5
            if calculate_supertrend_signal(candles) == "bullish": score += 1.0
            if calculate_supertrend_signal(candles) == "bearish": score -= 1.0
            if detect_ema_crossover(candles) == "bullish": score += 1.0
            if detect_ema_crossover(candles) == "bearish": score -= 1.0
            if detect_volume_divergence(candles): score += 0.5
            if detect_slow_breakout(candles): score += 0.5
            if detect_whale_activity(candles): score += 1.0
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5

        # --- SWING STRATEGY: 30m, 1h, 4h ---
        elif tf_int in [30, 60, 240]:
            rsi_vals = calculate_rsi(candles)
            if rsi_vals:
                latest_rsi = rsi_vals[-1]
                if latest_rsi < 30: score += 1.0
                elif latest_rsi > 70: score -= 1.0
            if calculate_supertrend_signal(candles) == "bullish": score += 1.0
            if calculate_supertrend_signal(candles) == "bearish": score -= 1.0
            if detect_ema_crossover(candles) == "bullish": score += 1.0
            if detect_ema_crossover(candles) == "bearish": score -= 1.0
            bb = calculate_bollinger_bands(candles)
            if bb and bb[-1]:
                close = float(candles[-1]["close"])
                if close > bb[-1]["upper"]: score += 0.5
                elif close < bb[-1]["lower"]: score -= 0.5
            if detect_whale_activity(candles): score += 1.0
            pattern = detect_pattern(candles)
            if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
            if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5

        tf_scores[tf] = score
        total_score += score

    return total_score, tf_scores

# Trade type logic
def determine_trade_type(tf_scores):
    tf_score = {int(k): v for k, v in tf_scores.items()}
    short = sum(v for k, v in tf_score.items() if k in [1, 3])
    mid = sum(v for k, v in tf_score.items() if k in [5, 15])
    long = sum(v for k, v in tf_score.items() if k in [30, 60, 240])

    if short >= mid and short >= long:
        return "Scalp"
    elif mid >= short and mid >= long:
        return "Intraday"
    else:
        return "Swing"

# Direction logic
def determine_direction(tf_scores):
    values = list(tf_scores.values())
    negative_count = sum(1 for v in values if v < 0)
    total = sum(values)
    if negative_count >= len(tf_scores) // 2 and total < 0:
        return "Short"
    return "Long"

# Confidence Score Logic
def calculate_confidence(score, tf_scores, trend_context, trade_type):
    max_score = 10 if trade_type == "Scalp" else (15 if trade_type == "Intraday" else 20)
    trend_boost = 2 if trend_context['btc_trend'] == "strong" or trend_context['altseason'] else 0
    tf_alignment = sum(1 for s in tf_scores.values() if s > 0)
    confidence = (score + trend_boost + tf_alignment) / (max_score + 3) * 100
    return round(min(confidence, 100), 1)
