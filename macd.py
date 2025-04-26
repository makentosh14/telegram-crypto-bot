def calculate_ema(values, period):
    ema = []
    multiplier = 2 / (period + 1)

    for i, value in enumerate(values):
        if i == 0:
            ema.append(value)
        else:
            ema.append((value - ema[-1]) * multiplier + ema[-1])

    return ema

def calculate_macd(candles, fast_period=12, slow_period=26, signal_period=9):
    closes = [float(c['close']) for c in candles]
    macd_result = []

    fast_ema = calculate_ema(closes, fast_period)
    slow_ema = calculate_ema(closes, slow_period)

    macd_line = [fast - slow for fast, slow in zip(fast_ema, slow_ema)]
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = [macd - signal for macd, signal in zip(macd_line, signal_line)]

    for i in range(len(macd_line)):
        macd_result.append({
            'macd': macd_line[i],
            'signal': signal_line[i],
            'histogram': histogram[i]
        })

    return macd_result

def detect_macd_cross(candles):
    macd_data = calculate_macd(candles)
    if len(macd_data) < 2:
        return None

    prev = macd_data[-2]
    curr = macd_data[-1]

    if prev["macd"] < prev["signal"] and curr["macd"] > curr["signal"]:
        return "bullish"
    elif prev["macd"] > prev["signal"] and curr["macd"] < curr["signal"]:
        return "bearish"
    else:
        return None
