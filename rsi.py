# rsi.py

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50  # Neutral default

    gains = []
    losses = []

    for i in range(1, period + 1):
        delta = prices[-i] - prices[-i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(delta))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100
    rs = average_gain / average_loss
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)
