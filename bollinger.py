def calculate_bollinger_bands(prices, window=20, num_std=2):
    if len(prices) < window:
        return None, None, None

    sma = sum(prices[-window:]) / window
    variance = sum((x - sma) ** 2 for x in prices[-window:]) / window
    std_dev = variance ** 0.5

    upper_band = sma + num_std * std_dev
    lower_band = sma - num_std * std_dev

    return upper_band, sma, lower_band

def detect_bollinger_breakout(prices, window=20, num_std=2):
    upper_band, sma, lower_band = calculate_bollinger_bands(prices, window, num_std)
    if upper_band is None:
        return False
    return prices[-1] > upper_band
