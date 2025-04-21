# score.py

from rsi import calculate_rsi
from macd import detect_macd_cross
from supertrend import calculate_supertrend_signal
from ema import detect_ema_crossover
from bollinger import calculate_bollinger_bands
from pattern_detector import detect_pattern
from volume import is_volume_spike

def score_symbol(symbol, candles_by_timeframe):
    total_score = 0
    tf_scores = {}

    for tf, candles in candles_by_timeframe.items():
        score = 0
        
if is_volume_spike(candles, multiplier=2.5):
    score += 1  # reward confirmed breakout volume
        # RSI
        rsi_vals = calculate_rsi(candles)
        if rsi_vals:
            latest_rsi = rsi_vals[-1]
            if latest_rsi < 30:
                score += 1
            elif latest_rsi > 70:
                score -= 1

        # MACD
        macd_cross = detect_macd_cross(candles)
        if macd_cross == "bullish":
            score += 1
        elif macd_cross == "bearish":
            score -= 1

        # Supertrend
        supertrend_signal = calculate_supertrend_signal(candles)
        if supertrend_signal == "bullish":
            score += 1
        elif supertrend_signal == "bearish":
            score -= 1

        # EMA Crossover
        ema_cross = detect_ema_crossover(candles)
        if ema_cross == "bullish":
            score += 1
        elif ema_cross == "bearish":
            score -= 1

        # Bollinger Squeeze / Breakout
        bb = calculate_bollinger_bands(candles)
        if bb and bb[-1]:
            band = bb[-1]
            close = float(candles[-1]["close"])
            if close > band["upper"]:
                score += 1
            elif close < band["lower"]:
                score -= 1

        # Pattern Detection
        pattern = detect_pattern(candles)
        if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
            score += 1
        elif pattern in ["bearish_engulfing", "inverted_hammer"]:
            score -= 1

        tf_scores[tf] = score
        total_score += score

    return total_score, tf_scores
