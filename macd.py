def calculate_ema(prices, period):
    if len(prices) < period:
        return []
    ema = []
    multiplier = 2 / (period + 1)
    sma = sum(prices[:period]) / period
    ema.append(sma)
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def calculate_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0, 0
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    if len(ema_fast) < len(ema_slow):
        ema_fast = ema_fast[-len(ema_slow):]
    else:
        ema_slow = ema_slow[-len(ema_fast):]

    macd_line = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line, signal)

    if not macd_line or not signal_line:
        return 0, 0

    return macd_line[-1], signal_line[-1]
