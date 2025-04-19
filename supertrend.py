# supertrend.py

def calculate_supertrend(candles, period=10, multiplier=3):
    if len(candles) < period:
        return []

    atr_values = []
    supertrend = []
    final_upperband = []
    final_lowerband = []

    for i in range(len(candles)):
        high = float(candles[i]['high'])
        low = float(candles[i]['low'])
        close = float(candles[i]['close'])

        if i == 0:
            tr = high - low
        else:
            prev_close = float(candles[i - 1]['close'])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))

        if i < period:
            atr_values.append(tr)
            supertrend.append(None)
            final_upperband.append(None)
            final_lowerband.append(None)
        else:
            if i == period:
                atr = sum(atr_values[-period:]) / period
            else:
                atr = (atr_values[-1] * (period - 1) + tr) / period
            atr_values.append(atr)

            hl2 = (high + low) / 2
            upperband = hl2 + multiplier * atr
            lowerband = hl2 - multiplier * atr

            if close <= final_upperband[-1] if final_upperband[-1] is not None else True:
                trend = 'down'
            elif close >= final_lowerband[-1] if final_lowerband[-1] is not None else False:
                trend = 'up'
            else:
                trend = supertrend[-1] if supertrend[-1] else 'down'

            if trend == 'up':
                upperband = None
            else:
                lowerband = None

            supertrend.append(trend)
            final_upperband.append(upperband)
            final_lowerband.append(lowerband)

    return supertrend

def get_supertrend_signal(candles):
    trend = calculate_supertrend(candles)
    if not trend or len(trend) < 2:
        return None
    if trend[-2] == 'down' and trend[-1] == 'up':
        return 'buy'
    elif trend[-2] == 'up' and trend[-1] == 'down':
        return 'sell'
    return None
