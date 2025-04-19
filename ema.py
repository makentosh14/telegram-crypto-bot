# ema.py

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    ema = prices[0]
    multiplier = 2 / (period + 1)
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema

def detect_ema_crossover(prices, short=9, long=21):
    if len(prices) < long:
        return False

    short_ema = calculate_ema(prices[-short * 3:], short)
    long_ema = calculate_ema(prices[-long * 3:], long)

    return short_ema > long_ema
