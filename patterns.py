def detect_bullish_patterns(candles):
    score = 0
    if len(candles) < 4:
        return score

    def body(c):
        return abs(float(c['close']) - float(c['open']))

    def is_bullish(c):
        return float(c['close']) > float(c['open'])

    def is_bearish(c):
        return float(c['close']) < float(c['open'])

    c1 = candles[-4]
    c2 = candles[-3]
    c3 = candles[-2]
    c4 = candles[-1]

    # Bullish Engulfing
    if is_bearish(c2) and is_bullish(c3) and float(c3['close']) > float(c2['open']) and float(c3['open']) < float(c2['close']):
        score += 1

    # Hammer
    if is_bullish(c4):
        body_len = body(c4)
        lower_shadow = float(c4['open']) - float(c4['low']) if float(c4['open']) > float(c4['low']) else float(c4['close']) - float(c4['low'])
        if lower_shadow > 2 * body_len:
            score += 1

    # Morning Star
    if is_bearish(c1) and abs(float(c2['open']) - float(c2['close'])) < body(c1) * 0.3 and is_bullish(c3):
        if float(c3['close']) > ((float(c1['open']) + float(c1['close'])) / 2):
            score += 1

    return score
