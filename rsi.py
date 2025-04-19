def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return 50  # Neutral RSI if not enough data

    gains = []
    losses = []

    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta >= 0:
            gains.append(delta)
        else:
            losses.append(abs(delta))

    average_gain = sum(gains) / period if gains else 0
    average_loss = sum(losses) / period if losses else 0

    if average_loss == 0:
        return 100

    rs = average_gain / average_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)
