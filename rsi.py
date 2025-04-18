def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50  # neutral default
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta > 0:
            gains.append(delta)
        else:
            losses.append(abs(delta))
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 1  # avoid division by zero
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
