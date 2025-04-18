def get_supertrend_signal(candles, period=10, multiplier=3):
    if len(candles) < period:
        return None

    atr_values = []
    for i in range(period, len(candles)):
        tr_list = []
        for j in range(i - period + 1, i + 1):
            high = float(candles[j]['high'])
            low = float(candles[j]['low'])
            prev_close = float(candles[j - 1]['close']) if j > 0 else high
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        atr = sum(tr_list) / period
        atr_values.append(atr)

    final_index = len(candles) - 1
    close = float(candles[final_index]['close'])
    high = float(candles[final_index]['high'])
    low = float(candles[final_index]['low'])

    atr = atr_values[-1]
    upper_band = (high + low) / 2 + multiplier * atr
    lower_band = (high + low) / 2 - multiplier * atr

    if close > upper_band:
        return 'buy'
    elif close < lower_band:
        return 'sell'
    else:
        return 'hold'

