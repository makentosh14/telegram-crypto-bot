def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50  # Neutral RSI if not enough data

    gains = []
    losses = []

    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta > 0:
            gains.append(delta)
        else:
            losses.append(abs(delta))

    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0

    if avg_loss == 0:
        return 100  # RSI maxed out

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

