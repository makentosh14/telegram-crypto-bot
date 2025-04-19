def get_supertrend_signal(candles, period=10, multiplier=3):
    if len(candles) < period + 1:
        return None

    # Prepare lists
    high = [float(c['high']) for c in candles]
    low = [float(c['low']) for c in candles]
    close = [float(c['close']) for c in candles]

    atr = calculate_atr(high, low, close, period)
    if not atr:
        return None

    # Supertrend calculation
    final_upperband = []
    final_lowerband = []
    supertrend = []
    direction = []

    for i in range(period, len(close)):
        hl2 = (high[i] + low[i]) / 2
        upperband = hl2 + (multiplier * atr[i - period])
        lowerband = hl2 - (multiplier * atr[i - period])

        if i == period:
            final_upperband.append(upperband)
            final_lowerband.append(lowerband)
            supertrend.append(lowerband)
            direction.append(True)
            continue

        if close[i] > final_upperband[-1]:
            direction.append(True)
        elif close[i] < final_lowerband[-1]:
            direction.append(False)
        else:
            direction.append(direction[-1])

            if direction[-1] and lowerband < final_lowerband[-1]:
                lowerband = final_lowerband[-1]
            if not direction[-1] and upperband > final_upperband[-1]:
                upperband = final_upperband[-1]

        final_upperband.append(upperband)
        final_lowerband.append(lowerband)

        if direction[-1]:
            supertrend.append(lowerband)
        else:
            supertrend.append(upperband)

    # Determine signal
    if direction[-1] and not direction[-2]:
        return "buy"
    elif not direction[-1] and direction[-2]:
        return "sell"
    else:
        return None


def calculate_atr(high, low, close, period=10):
    tr_list = []
    for i in range(1, len(close)):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        tr_list.append(tr)

    if len(tr_list) < period:
        return []

    atr = []
    atr.append(sum(tr_list[:period]) / period)  # first ATR value is SMA

    for i in range(period, len(tr_list)):
        atr.append((atr[-1] * (period - 1) + tr_list[i]) / period)

    return atr
