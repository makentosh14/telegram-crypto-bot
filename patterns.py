def detect_bullish_patterns(candles):
    if len(candles) < 3:
        return 0

    score = 0
    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]

    o1, h1, l1, cl1 = float(c1['open']), float(c1['high']), float(c1['low']), float(c1['close'])
    o2, h2, l2, cl2 = float(c2['open']), float(c2['high']), float(c2['low']), float(c2['close'])
    o3, h3, l3, cl3 = float(c3['open']), float(c3['high']), float(c3['low']), float(c3['close'])

    # Bullish engulfing
    if cl2 < o2 and cl3 > o3 and cl3 > o2 and o3 < cl2:
        score += 1

    # Morning star
    if cl1 < o1 and abs(cl2 - o2) < (h2 - l2) * 0.3 and cl3 > o3 and cl3 > ((cl1 + o1) / 2):
        score += 1

    # Hammer
    if (cl3 > o3) and ((l3 - min(o3, cl3)) > 2 * abs(cl3 - o3)):
        score += 1

    return score
