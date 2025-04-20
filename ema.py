def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def detect_ema_crossover(close_prices, short=9, long=21):
    if len(close_prices) < long + 1:
        return False
    short_ema_prev = calculate_ema(close_prices[-(short+2):-1], short)
    long_ema_prev = calculate_ema(close_prices[-(long+2):-1], long)
    short_ema_now = calculate_ema(close_prices[-(short+1):], short)
    long_ema_now = calculate_ema(close_prices[-(long+1):], long)
    return short_ema_prev < long_ema_prev and short_ema_now > long_ema_now
