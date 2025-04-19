def detect_bullish_patterns(candles):
    if len(candles) < 4:
        return 0

    score = 0
    last = candles[-1]
    prev = candles[-2]

    open_price = float(last['open'])
    close_price = float(last['close'])
    high = float(last['high'])
    low = float(last['low'])

    prev_open = float(prev['open'])
    prev_close = float(prev['close'])

    # Bullish Engulfing
    if close_price > open_price and prev_close < prev_open:
        if close_price > prev_open and open_price < prev_close:
            score += 1

    # Hammer
    body = abs(close_price - open_price)
    lower_wick = open_price - low if close_price > open_price else close_price - low
    upper_wick = high - close_price if close_price > open_price else high - open_price
    if lower_wick > 2 * body and upper_wick < body:
        score += 1

    # Morning Star (3 candles)
    third = candles[-3]
    third_close = float(third['close'])
    if third_close > prev_close and close_price > prev_close:
        score += 1

    return score
