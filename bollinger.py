def calculate_bollinger_bands(prices, window=20, num_std_dev=2):
    if len(prices) < window:
        return None, None, None

    sma = sum(prices[-window:]) / window
    variance = sum((price - sma) ** 2 for price in prices[-window:]) / window
    std_dev = variance ** 0.5

    upper_band = sma + (num_std_dev * std_dev)
    lower_band = sma - (num_std_dev * std_dev)
    return upper_band, sma, lower_band

def detect_bollinger_breakout(close_prices, window=20, num_std_dev=2):
    if len(close_prices) < window:
        return False

    upper, middle, lower = calculate_bollinger_bands(close_prices, window, num_std_dev)
    if not upper or not lower:
        return False

    latest_price = close_prices[-1]
    return latest_price > upper  # breakout above upper band

def is_bollinger_squeeze(close_prices, window=20, num_std_dev=2, threshold=0.02):
    if len(close_prices) < window:
        return False

    upper, middle, lower = calculate_bollinger_bands(close_prices, window, num_std_dev)
    if not upper or not lower:
        return False

    band_width = upper - lower
    squeeze_threshold = middle * threshold  # e.g. 2% of price

    return band_width < squeeze_threshold
