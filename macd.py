def calculate_ema(data, period):
    if len(data) < period:
        return []

    ema = [sum(data[:period]) / period]
    multiplier = 2 / (period + 1)

    for price in data[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])

    return ema

def calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9):
    if len(prices) < slow_period + signal_period:
        return 0, 0

    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)

    if len(fast_ema) < len(slow_ema):
        fast_ema = fast_ema[-len(slow_ema):]
    else:
        slow_ema = slow_ema[-len(fast_ema):]

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = calculate_ema(macd_line, signal_period)

    if not macd_line or not signal_line:
        return 0, 0

    return macd_line[-1], signal_line[-1]
