def calculate_atr(highs, lows, closes, period=10):
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else 0

def get_supertrend_signal(candles, period=10, multiplier=3):
    if len(candles) < period + 1:
        return 'neutral'

    highs = [float(c['high']) for c in candles]
    lows = [float(c['low']) for c in candles]
    closes = [float(c['close']) for c in candles]

    atr = calculate_atr(highs, lows, closes, period)
    hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
    upper_band = hl2[-1] + multiplier * atr
    lower_band = hl2[-1] - multiplier * atr

    previous_close = closes[-2]
    current_close = closes[-1]

    if current_close > upper_band and previous_close <= upper_band:
        return 'buy'
    elif current_close < lower_band and previous_close >= lower_band:
        return 'sell'
    else:
        return 'neutral'
