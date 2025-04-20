def detect_ema_crossover(close_prices, short=9, long=21):
    if len(close_prices) < long:
        return False

    short_ema = sum(close_prices[-short:]) / short
    long_ema = sum(close_prices[-long:]) / long

    return short_ema > long_ema
