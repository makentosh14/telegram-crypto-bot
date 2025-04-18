import statistics

def calculate_bollinger_bands(close_prices, window=20, num_std=2):
    """
    Calculates Bollinger Bands for given closing prices.
    Returns a tuple: (sma, upper_band, lower_band)
    """
    if len(close_prices) < window:
        return None, None, None

    sma = statistics.mean(close_prices[-window:])
    std_dev = statistics.stdev(close_prices[-window:])

    upper_band = sma + num_std * std_dev
    lower_band = sma - num_std * std_dev

    return sma, upper_band, lower_band


def detect_bollinger_breakout(close_prices, window=20, num_std=2):
    """
    Returns True if price breaks out above the upper Bollinger Band.
    """
    sma, upper_band, lower_band = calculate_bollinger_bands(close_prices, window, num_std)

    if sma is None:
        return False

    current_price = close_prices[-1]
    return current_price > upper_band


def detect_bollinger_squeeze(close_prices, window=20, squeeze_threshold=0.01):
    """
    Detects a Bollinger Band 'squeeze' (volatility compression) that may precede a breakout.
    Returns True if the band width is below the threshold.
    """
    sma, upper_band, lower_band = calculate_bollinger_bands(close_prices, window)
    
    if sma is None or upper_band is None or lower_band is None:
        return False

    band_width = upper_band - lower_band
    if sma == 0:
        return False

    relative_width = band_width / sma
    return relative_width < squeeze_threshold
