# supertrend.py

def calculate_atr(candles, period=10):
    trs = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else 0

def calculate_supertrend_signal(candles, period=10, multiplier=3):
    if len(candles) < period + 1:
        return None

    atr = calculate_atr(candles, period)
    if atr == 0:
        return None

    close = float(candles[-1]["close"])
    high = float(candles[-1]["high"])
    low = float(candles[-1]["low"])

    upper_band = (high + low) / 2 + multiplier * atr
    lower_band = (high + low) / 2 - multiplier * atr

    prev_close = float(candles[-2]["close"])

    if close > upper_band and prev_close < upper_band:
        return "bullish"
    elif close < lower_band and prev_close > lower_band:
        return "bearish"
    else:
        return None
