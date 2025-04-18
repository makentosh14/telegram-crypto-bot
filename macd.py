def calculate_ema(prices, period):
    if len(prices) < period:
        return sum(prices) / len(prices)
    
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    if len(prices) < long_period + signal_period:
        return 0, 0  # Not enough data

    short_ema = [calculate_ema(prices[i - short_period:i], short_period) for i in range(short_period, len(prices))]
    long_ema = [calculate_ema(prices[i - long_period:i], long_period) for i in range(long_period, len(prices))]

    macd_line = [s - l for s, l in zip(short_ema[-len(long_ema):], long_ema)]
    signal_line = [calculate_ema(macd_line[i - signal_period:i], signal_period) for i in range(signal_period, len(macd_line))]

    return round(macd_line[-1], 5), round(signal_line[-1], 5)
