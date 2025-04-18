def detect_bullish_patterns(candles):
    if len(candles) < 5:
        return 0

    latest = candles[-1]
    prev = candles[-2]
    score = 0

    open1 = float(prev['open'])
    close1 = float(prev['close'])
    open2 = float(latest['open'])
    close2 = float(latest['close'])

    # Bullish Engulfing
    if close2 > open2 and open1 > close1 and open2 < close1 and close2 > open1:
        score += 1

    # Hammer
    body = abs(close2 - open2)
    lower_wick = min(open2, close2) - float(latest['low'])
    upper_wick = float(latest['high']) - max(open2, close2)
    if lower_wick > 2 * body and upper_wick < body:
        score += 1

    # Morning Star
    if len(candles) >= 3:
        c1 = candles[-3]
        c2 = candles[-2]
        c3 = candles[-1]
        if float(c1['close']) < float(c1['open']) and \
           float(c2['close']) < float(c2['open']) and \
           float(c3['close']) > float(c3['open']) and \
           float(c3['close']) > float(c1['open']):
            score += 1

    return score
