def calculate_supertrend(candles, period=10, multiplier=3):
    if len(candles) < period:
        return []

    tr_values = []
    atr_values = []
    hl2_values = []
    supertrend = []
    final_upperband = []
    final_lowerband = []

    for i in range(len(candles)):
        high = float(candles[i]['high'])
        low = float(candles[i]['low'])
        close = float(candles[i]['close'])
        hl2 = (high + low) / 2
        hl2_values.append(hl2)

        if i == 0:
            tr = high - low
        else:
            prev_close = float(candles[i - 1]['close'])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)

        if i < period:
            atr_values.append(0)  # Placeholder
            final_upperband.append(0)
            final_lowerband.append(0)
            supertrend.append(None)
            continue

        atr = sum(tr_values[i - period + 1:i + 1]) / period
        atr_values.append(atr)

        upper_band = hl2 - (multiplier * atr)
        lower_band = hl2 + (multiplier * atr)
        final_upperband.append(upper_band)
        final_lowerband.append(lower_band)

        if i == period:
            supertrend.append(True)  # Start with bullish
        else:
            if supertrend[i - 1] is True:
                if close > final_upperband[i]:
                    supertrend.append(True)
                else:
                    supertrend.append(False)
            else:
                if close < final_lowerband[i]:
                    supertrend.append(False)
                else:
                    supertrend.append(True)

    return supertrend

def get_supertrend_signal(candles):
    st = calculate_supertrend(candles)
    if not st or len(st) < 2:
        return None
    return "buy" if st[-1] else "sell"
