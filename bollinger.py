# bollinger.py

def calculate_bollinger_bands(prices, window=20, num_std=2):
    if len(prices) < window:
        return None, None, None

    sma = sum(prices[-window:]) / window
    std = (sum((p - sma) ** 2 for p in prices[-window:]) / window) ** 0.5
    upper_band = sma + num_std * std
    lower_band = sma - num_std * std

    return upper_band, sma, lower_band

def detect_bollinger_breakout(prices, window=20, num_std=2):
    if len(prices) < window:
        return False

    upper, _, _ = calculate_bollinger_bands(prices, window, num_std)
    return prices[-1] > upper
