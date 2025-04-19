def detect_bollinger_breakout(close_prices, window=20, num_std=2):
    """
    Detects breakout above the upper Bollinger Band.
    """
    if len(close_prices) < window:
        return False

    sma = sum(close_prices[-window:]) / window
    std_dev = (sum((x - sma) ** 2 for x in close_prices[-window:]) / window) ** 0.5
    upper_band = sma + num_std * std_dev
    lower_band = sma - num_std * std_dev

    breakout_up = close_prices[-1] > upper_band
    breakout_down = close_prices[-1] < lower_band

    if breakout_up:
        return "bullish"
    elif breakout_down:
        return "bearish"
    else:
        return None
