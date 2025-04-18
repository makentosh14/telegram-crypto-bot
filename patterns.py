def is_bullish_engulfing(prev_candle, curr_candle):
    return (
        float(prev_candle['close']) < float(prev_candle['open']) and
        float(curr_candle['close']) > float(curr_candle['open']) and
        float(curr_candle['close']) > float(prev_candle['open']) and
        float(curr_candle['open']) < float(prev_candle['close'])
    )

def is_bearish_engulfing(prev_candle, curr_candle):
    return (
        float(prev_candle['close']) > float(prev_candle['open']) and
        float(curr_candle['close']) < float(curr_candle['open']) and
        float(curr_candle['open']) > float(prev_candle['close']) and
        float(curr_candle['close']) < float(prev_candle['open'])
    )

def is_hammer(candle):
    body = abs(float(candle['close']) - float(candle['open']))
    lower_shadow = float(candle['open']) - float(candle['low']) if float(candle['open']) > float(candle['close']) else float(candle['close']) - float(candle['low'])
    upper_shadow = float(candle['high']) - max(float(candle['close']), float(candle['open']))
    return lower_shadow > 2 * body and upper_shadow < body

def is_doji(candle):
    return abs(float(candle['close']) - float(candle['open'])) <= ((float(candle['high']) - float(candle['low'])) * 0.1)

def is_morning_star(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    return (
        float(c1['close']) < float(c1['open']) and
        is_doji(c2) and
        float(c3['close']) > float(c3['open']) and
        float(c3['close']) > (float(c1['open']) + float(c1['close'])) / 2
    )

def is_evening_star(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    return (
        float(c1['close']) > float(c1['open']) and
        is_doji(c2) and
        float(c3['close']) < float(c3['open']) and
        float(c3['close']) < (float(c1['open']) + float(c1['close'])) / 2
    )

def detect_bullish_patterns(candles):
    if len(candles) < 3:
        return 0

    score = 0

    if is_bullish_engulfing(candles[-2], candles[-1]):
        score += 1

    if is_hammer(candles[-1]):
        score += 1

    if is_morning_star(candles):
        score += 2  # Stronger pattern

    return score

def detect_bearish_patterns(candles):
    if len(candles) < 3:
        return 0

    score = 0

    if is_bearish_engulfing(candles[-2], candles[-1]):
        score += 1

    if is_evening_star(candles):
        score += 2  # Stronger pattern

    return score

