# macd.py

def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    if len(prices) < long_period:
        return 0, 0

    def ema(data, period):
        k = 2 / (period + 1)
        ema_values = [sum(data[:period]) / period]
        for price in data[period:]:
            ema_values.append(price * k + ema_values[-1] * (1 - k))
        return ema_values

    short_ema = ema(prices, short_period)
    long_ema = ema(prices, long_period)
    macd_line = [s - l for s, l in zip(short_ema[-len(long_ema):], long_ema)]
    signal_line = ema(macd_line, signal_period)

    return macd_line[-1], signal_line[-1]
