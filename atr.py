# atr.py
def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    trs = []
    for i in range(1, period + 1):
        high = float(candles[-i]['high'])
        low = float(candles[-i]['low'])
        prev_close = float(candles[-i - 1]['close'])
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    atr = sum(trs) / period
    return round(atr, 6)
