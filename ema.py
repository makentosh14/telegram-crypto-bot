# ema.py

def calculate_ema(candles, period):
    closes = [float(c['close']) for c in candles]
    ema = []
    multiplier = 2 / (period + 1)

    for i in range(len(closes)):
        if i == 0:
            ema.append(closes[0])
        else:
            ema.append((closes[i] - ema[i - 1]) * multiplier + ema[i - 1])

    return ema

def detect_ema_crossover(candles, fast_period=9, slow_period=21):
    """
    Detects bullish or bearish EMA crossover
    Returns: 'bullish', 'bearish', or None
    """
    fast_ema = calculate_ema(candles, fast_period)
    slow_ema = calculate_ema(candles, slow_period)

    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return None

    if fast_ema[-2] < slow_ema[-2] and fast_ema[-1] > slow_ema[-1]:
        return "bullish"
    elif fast_ema[-2] > slow_ema[-2] and fast_ema[-1] < slow_ema[-1]:
        return "bearish"
    else:
        return None
