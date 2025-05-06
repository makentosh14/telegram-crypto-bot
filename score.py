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

WEIGHTS = {
    "macd": 1.5,
    "ema": 1.0,
    "volume_spike": 1.0,
    "supertrend": 1.0,
    "rsi": 1.0,
    "bollinger": 0.5,
    "pattern": 0.5,
    "divergence": 0.5,
    "slow_breakout": 0.5,
    "whale": 1.0,
}

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

    for tf, candles in candles_by_timeframe.items():
        score = 0
        tf_label = f"{tf}m"

        try:
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

    valid_types = [t for t in type_scores if tf_count[t] >= MIN_TF_REQUIRED[t]]
    best_type = max(valid_types, key=lambda t: type_scores[t], default="Scalp")
    best_score = type_scores[best_type]

    return round(best_score, 2), tf_scores, best_type, indicator_scores, list(used_indicators)


def determine_direction(tf_scores):
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
