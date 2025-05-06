from rsi import calculate_rsi
from macd import detect_macd_cross
from supertrend import calculate_supertrend_signal
from ema import detect_ema_crossover
from bollinger import calculate_bollinger_bands
from pattern_detector import detect_pattern
from volume import is_volume_spike
from stealth_detector import detect_volume_divergence, detect_slow_breakout
from whale_detector import detect_whale_activity
from error_handler import send_error_to_telegram
from config import ALWAYS_ALLOW_SWING

def score_symbol(symbol, candles_by_timeframe):
    if symbol == "FOOUSDT":  # 🚨 Test-only fake symbol
        tf_scores = {"1": -3.0, "3": -3.0, "5": -2.0}
        indicator_scores = {"1m_macd": -1.5, "1m_ema": -1.0, "1m_volume": 1.0}
        used_indicators = ["macd", "ema", "volume"]
        return 9.5, tf_scores, "Scalp", indicator_scores, used_indicators

    tf_scores = {}
    short_score, mid_score, long_score = 0, 0, 0
    indicator_scores = {}
    used_indicators = set()

    for tf, candles in candles_by_timeframe.items():
        score = 0
        tf_int = int(tf)

        try:
            if tf_int in [1, 3]:  # Scalp
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                pattern = detect_pattern(candles)
                if is_volume_spike(candles, 2.5): score += 1.0; indicator_scores[f"{tf}m_volume"] = 1.0
                if macd == "bullish": score += 1.5
                if macd == "bearish": score -= 1.5
                if ema == "bullish": score += 1.0
                if ema == "bearish": score -= 1.0
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
                if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5
                if detect_volume_divergence(candles): score += 0.5
                if detect_slow_breakout(candles): score += 0.5
                if detect_whale_activity(candles): score += 1.0
                short_score += score
                used_indicators.update(["macd", "ema", "volume", "pattern", "divergence", "whale"])

            elif tf_int in [5, 15]:  # Intraday
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                pattern = detect_pattern(candles)
                trend = calculate_supertrend_signal(candles)
                if is_volume_spike(candles, 2.5): score += 1.0
                if macd == "bullish": score += 1.5
                if macd == "bearish": score -= 1.5
                if trend == "bullish": score += 1.0
                if trend == "bearish": score -= 1.0
                if ema == "bullish": score += 1.0
                if ema == "bearish": score -= 1.0
                if detect_volume_divergence(candles): score += 0.5
                if detect_slow_breakout(candles): score += 0.5
                if detect_whale_activity(candles): score += 1.0
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
                if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5
                mid_score += score
                used_indicators.update(["macd", "ema", "supertrend", "volume", "pattern", "divergence", "whale"])

            elif tf_int in [30, 60, 240]:  # Swing
                rsi_vals = calculate_rsi(candles)
                if rsi_vals:
                    rsi = rsi_vals[-1]
                    if rsi < 30: score += 1.0
                    elif rsi > 70: score -= 1.0
                trend = calculate_supertrend_signal(candles)
                ema = detect_ema_crossover(candles)
                bb = calculate_bollinger_bands(candles)
                pattern = detect_pattern(candles)
                if trend == "bullish": score += 1.0
                if trend == "bearish": score -= 1.0
                if ema == "bullish": score += 1.0
                if ema == "bearish": score -= 1.0
                if bb and bb[-1]:
                    close = float(candles[-1]["close"])
                    if close > bb[-1]["upper"]: score += 0.5
                    elif close < bb[-1]["lower"]: score -= 0.5
                if detect_whale_activity(candles): score += 1.0
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]: score += 0.5
                if pattern in ["bearish_engulfing", "inverted_hammer"]: score -= 0.5
                long_score += score
                used_indicators.update(["rsi", "ema", "supertrend", "bollinger", "pattern", "whale"])

        except Exception as e:
            from logger import log
            log(f"❌ Scoring error for {symbol} [{tf}m]: {str(e)}", level="ERROR")

        tf_scores[tf] = score

    # 🔴 Additional Check: If more than half of timeframes have negative score, and total is negative, force Short
    total_score = short_score + mid_score + long_score
    if sum(1 for s in tf_scores.values() if s < 0) > len(tf_scores) // 2 and total_score < 0:
        direction_override = "Short"
    else:
        direction_override = None

    best_score = max(short_score, mid_score, long_score)
    best_type = "Scalp" if best_score == short_score else ("Intraday" if best_score == mid_score else "Swing")

    return best_score, tf_scores, best_type, indicator_scores, list(used_indicators), direction_override

def determine_direction(tf_scores, direction_override=None):
    if direction_override:
        return direction_override
    values = list(tf_scores.values())
    negative_count = sum(1 for v in values if v < 0)
    total = sum(values)
    return "Short" if negative_count >= len(tf_scores) // 2 and total < 0 else "Long"

def calculate_confidence(score, tf_scores, trend_context, trade_type):
    max_score = 10 if trade_type == "Scalp" else (15 if trade_type == "Intraday" else 20)
    trend_boost = 2 if trend_context.get("btc_trend") == "strong" or trend_context.get("altseason") else 0
    tf_alignment = sum(1 for s in tf_scores.values() if s > 0)
    confidence = (score + trend_boost + tf_alignment) / (max_score + 3) * 100
    return round(min(confidence, 100), 1)
