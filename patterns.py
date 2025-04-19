# patterns.py

def detect_bullish_patterns(candles):
    """Returns a pattern score based on bullish reversal candlestick patterns."""
    score = 0
    if len(candles) < 3:
        return score

    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]

    # Helper: Convert to float once
    o1, h1, l1, cl1 = map(float, (c1['open'], c1['high'], c1['low'], c1['close']))
    o2, h2, l2, cl2 = map(float, (c2['open'], c2['high'], c2['low'], c2['close']))
    o3, h3, l3, cl3 = map(float, (c3['open'], c3['high'], c3['low'], c3['close']))

    # Bullish Engulfing
    if cl2 < o2 and cl3 > o3 and cl3 > o2 and o3 < cl2:
        score += 1

    # Hammer
    if (cl3 > o3) and ((o3 - l3) > 2 * abs(cl3 - o3)) and (h3 - cl3 < 0.3 * (cl3 - l3)):
        score += 1

    # Morning Star
    if cl1 < o1 and abs(cl2 - o2) < 0.1 * o2 and cl3 > o3 and cl3 > (o1 + cl1) / 2:
        score += 1

    return score
