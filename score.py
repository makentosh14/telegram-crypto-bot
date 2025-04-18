from rsi import calculate_rsi
from macd import calculate_macd
from supertrend import get_supertrend_signal
from volume import detect_volume_spike
from patterns import detect_bullish_patterns
from bollinger import detect_bollinger_breakout
from ema import detect_ema_crossover
from trend_filters import detect_breakout

def score_symbol(symbol, candles_by_tf):
    scores = {}
    total_score = 0
    weights = {'5m': 0.3, '15m': 0.4, '1h': 0.3}

    for tf, candles in candles_by_tf.items():
        tf_score = 0
        if not candles or len(candles) < 50:
            scores[tf] = 0
            continue

        close_prices = [float(c['close']) for c in candles]
        high_prices = [float(c['high']) for c in candles]
        low_prices = [float(c['low']) for c in candles]

        # RSI Score
        rsi = calculate_rsi(close_prices)
        if rsi < 30:
            tf_score += 1
        elif rsi > 70:
            tf_score -= 1

        # MACD Score
        macd, signal = calculate_macd(close_prices)
        if macd > signal:
            tf_score += 1
        elif macd < signal:
            tf_score -= 1

        # Supertrend Score
        st = get_supertrend_signal(candles)
        if st == "buy":
            tf_score += 1
        elif st == "sell":
            tf_score -= 1

        # Volume Spike Detection
        if detect_volume_spike(candles):
            tf_score += 1

        # Bullish Pattern Detection
        tf_score += detect_bullish_patterns(candles)

        # Bollinger Bands Breakout
        if detect_bollinger_breakout(close_prices):
            tf_score += 1

        # EMA Crossover
        if detect_ema_crossover(close_prices):
            tf_score += 1

        # Resistance Breakout
        if detect_breakout(candles):
            tf_score += 1

        scores[tf] = tf_score
        total_score += tf_score * weights[tf]

    return round(total_score, 2), scores

