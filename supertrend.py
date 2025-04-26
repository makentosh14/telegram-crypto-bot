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
    if atr < 1e-8:  # Handle extremely small ATR
        return None

    latest_candle = candles[-1]
    previous_candle = candles[-2]

    avg_price = (float(latest_candle["high"]) + float(latest_candle["low"])) / 2
    upper_band = avg_price + multiplier * atr
    lower_band = avg_price - multiplier * atr

    close = float(latest_candle["close"])
    prev_close = float(previous_candle["close"])

    if close > upper_band and prev_close <= upper_band:
        return "bullish"
    elif close < lower_band and prev_close >= lower_band:
        return "bearish"
    else:
        return None
