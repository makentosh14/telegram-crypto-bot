# pattern_detector.py

def is_bullish_engulfing(prev, curr):
    return (
        float(prev["close"]) < float(prev["open"]) and
        float(curr["close"]) > float(curr["open"]) and
        float(curr["open"]) < float(prev["close"]) and
        float(curr["close"]) > float(prev["open"])
    )

def is_bearish_engulfing(prev, curr):
    return (
        float(prev["close"]) > float(prev["open"]) and
        float(curr["close"]) < float(curr["open"]) and
        float(curr["open"]) > float(prev["close"]) and
        float(curr["close"]) < float(prev["open"])
    )

def is_hammer(candle):
    high = float(candle["high"])
    low = float(candle["low"])
    open_ = float(candle["open"])
    close = float(candle["close"])
    body = abs(close - open_)
    tail = min(open_, close) - low
    return body < (high - low) * 0.3 and tail > body * 2

def is_inverted_hammer(candle):
    high = float(candle["high"])
    low = float(candle["low"])
    open_ = float(candle["open"])
    close = float(candle["close"])
    body = abs(close - open_)
    wick = high - max(open_, close)
    return body < (high - low) * 0.3 and wick > body * 2

def is_inside_bar(prev, curr):
    return (
        float(curr["high"]) < float(prev["high"]) and
        float(curr["low"]) > float(prev["low"])
    )

def detect_pattern(candles):
    if len(candles) < 2:
        return None

    prev = candles[-2]
    curr = candles[-1]

    if is_bullish_engulfing(prev, curr):
        return "bullish_engulfing"
    elif is_bearish_engulfing(prev, curr):
        return "bearish_engulfing"
    elif is_hammer(curr):
        return "hammer"
    elif is_inverted_hammer(curr):
        return "inverted_hammer"
    elif is_inside_bar(prev, curr):
        return "inside_bar"
    else:
        return None
