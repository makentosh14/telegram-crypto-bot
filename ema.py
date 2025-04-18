def calculate_ema(prices, period):
    if len(prices) < period:
        return []

    ema = []
    k = 2 / (period + 1)
    ema.append(sum(prices[:period]) / period)

    for price in prices[period:]:
        ema.append(price * k + ema[-1] * (1 - k))

    return ema

def detect_ema_crossover(prices, short=9, long=21):
    if len(prices) < long:
        return False

    short_ema = calculate_ema(prices, short)
    long_ema = calculate_ema(prices, long)

    if len(short_ema) < 1 or len(long_ema) < 1:
        return False

    return short_ema[-1] > long_ema[-1]
