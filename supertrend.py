def calculate_atr(candles, period=10):
    tr_values = []
    for i in range(1, len(candles)):
        high = float(candles[i]['high'])
        low = float(candles[i]['low'])
        prev_close = float(candles[i-1]['close'])

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_values.append(tr)

    if len(tr_values) < period:
        return []

    atr = []
    initial = sum(tr_values[:period]) / period
    atr.append(initial)

    for i in range(period, len(tr_values)):
        value = (atr[-1] * (period - 1) + tr_values[i]) / period
        atr.append(value)

    return atr

def get_supertrend_signal(candles, period=10, multiplier=3.0):
    if len(candles) < period + 1:
        return "neutral"

    atr = calculate_atr(candles, period)
    if not atr or len(atr) < len(candles) - period:
        return "neutral"

    supertrend = []
    final_upperband = []
    final_lowerband = []
    trend = []

    for i in range(period, len(candles)):
        hl2 = (float(candles[i]['high']) + float(candles[i]['low'])) / 2
        upperband = hl2 + (multiplier * atr[i - period])
        lowerband = hl2 - (multiplier * atr[i - period])

        if i == period:
            supertrend.append(lowerband)
            trend.append(True)  # Uptrend
        else:
            if float(candles[i - 1]['close']) > final_upperband[-1]:
                trend.append(True)
            elif float(candles[i - 1]['close']) < final_lowerband[-1]:
                trend.append(False)
            else:
                trend.append(trend[-1])

            if trend[-1]:
                supertrend.append(max(lowerband, supertrend[-1]))
            else:
                supertrend.append(min(upperband, supertrend[-1]))

        final_upperband.append(upperband)
        final_lowerband.append(lowerband)

    current_trend = trend[-1]
    if current_trend:
        return "buy"
    else:
        return "sell"

