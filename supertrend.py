def calculate_atr(candles, period=10):
    trs = []
    for i in range(1, len(candles)):
        high = float(candles[i]['high'])
        low = float(candles[i]['low'])
        prev_close = float(candles[i - 1]['close'])

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) < period:
        return sum(trs) / len(trs)

    atr = sum(trs[-period:]) / period
    return atr

def get_supertrend_signal(candles, period=10, multiplier=3):
    if len(candles) < period + 1:
        return 'neutral'

    atr = calculate_atr(candles, period)
    current = candles[-1]
    prev = candles[-2]

    hl2 = (float(current['high']) + float(current['low'])) / 2
    prev_hl2 = (float(prev['high']) + float(prev['low'])) / 2

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    if float(current['close']) > upper_band:
        return 'buy'
    elif float(current['close']) < lower_band:
        return 'sell'
    else:
        return 'neutral'
