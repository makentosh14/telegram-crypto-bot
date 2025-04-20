import numpy as np

def detect_bollinger_breakout(close_prices, window=20, num_std=2):
    if len(close_prices) < window:
        return False

    recent_closes = np.array(close_prices[-window:])
    sma = np.mean(recent_closes)
    std_dev = np.std(recent_closes)

    upper_band = sma + num_std * std_dev
    lower_band = sma - num_std * std_dev

    last_price = close_prices[-1]

    if last_price > upper_band:
        return "breakout_up"
    elif last_price < lower_band:
        return "breakout_down"
    else:
        return None
