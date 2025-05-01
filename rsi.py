# rsi.py

def calculate_rsi(candles, period=14):
    """
    Calculates Relative Strength Index (RSI) for a list of candles.
    Returns a list of RSI values starting from index [period].
    """
    closes = [float(c['close']) for c in candles]

    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    # Initial average gain/loss
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rsi_values = []

    # Smoothed RSI
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0)
        loss = abs(min(delta, 0))

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values.append(round(rsi, 2))

    return rsi_values
