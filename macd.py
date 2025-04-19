# macd.py

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

    short_ema_list = []
    long_ema_list = []

    for i in range(len(prices)):
        short = calculate_ema(prices[max(0, i - short_period + 1):i + 1], short_period)
        long = calculate_ema(prices[max(0, i - long_period + 1):i + 1], long_period)
        short_ema_list.append(short)
        long_ema_list.append(long)

    macd_line = [s - l for s, l in zip(short_ema_list, long_ema_list)]
    signal_line = [calculate_ema(macd_line[max(0, i - signal_period + 1):i + 1], signal_period) for i in range(len(macd_line))]

    return round(macd_line[-1], 4), round(signal_line[-1], 4)
