from rsi import calculate_rsi
from macd import calculate_macd
from supertrend import get_supertrend_signal
from volume import detect_volume_spike
from patterns import detect_bullish_patterns
from bollinger import detect_bollinger_breakout
from ema import detect_ema_crossover
from trend_filters import detect_breakout

def score_symbol(symbol, candles_by_timeframe):
    scores = {}
    total_score = 0
    weighted_scores = {
        '5m': 0.3,
        '15m': 0.4,
        '1h': 0.3
    }

    for tf, candles in candles_by_timeframe.items():
        tf_score = 0
        if not candles or len(candles) < 50:
            scores[tf] = 0
            continue

        close_prices = [float(c['close']) for c in candles]

        # RSI
        rsi = calculate_rsi(close_prices)
        if rsi < 30:
            tf_score += 1
        elif rsi > 70:
            tf_score -= 1

        # MACD
        macd, signal = calculate_macd(close_prices)
        if macd > signal:
            tf_score += 1
        elif macd < signal:
            tf_score -= 1

        # Supertrend
        supertrend_signal = get_supertrend_signal(candles)
        if supertrend_signal == 'buy':
            tf_score += 1
        elif supertrend_signal == 'sell':
            tf_score -= 1

        # Volume Spike
        if detect_volume_spike(candles):
            tf_score += 1

        # Bullish Patterns
        pattern_score = detect_bullish_patterns(candles)
        tf_score += pattern_score

        # Bollinger Band Breakout
        if detect_bollinger_breakout(close_prices):
            tf_score += 1

        # EMA Crossover
        if detect_ema_crossover(close_prices):
            tf_score += 1

        # Breakout Detection
        if detect_breakout(candles):
            tf_score += 1

        scores[tf] = tf_score
        total_score += tf_score * weighted_scores[tf]

    return round(total_score, 2), scores
