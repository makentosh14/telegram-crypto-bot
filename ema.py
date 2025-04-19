def calculate_ema(prices, period=9):
    if len(prices) < period:
        return None
    ema = prices[0]
    k = 2 / (period + 1)
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def detect_ema_crossover(close_prices, short=9, long=21):
    if len(close_prices) < long:
        return False
    short_ema = calculate_ema(close_prices[-short:], short)
    long_ema = calculate_ema(close_prices[-long:], long)
    return short_ema > long_ema
