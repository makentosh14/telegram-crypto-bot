def detect_volume_divergence(candles, min_growth_ratio=1.2):
    """
    Detects stealth accumulation where volume rises while price stays flat or declines.
    Returns True if detected, False otherwise.
    """
    if len(candles) < 20:
        return False

    recent = candles[-10:]
    prices = [float(c['close']) for c in recent]
    volumes = [float(c['volume']) for c in recent]

    price_change = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0
    volume_growth = (volumes[-1] - volumes[0]) / volumes[0] if volumes[0] != 0 else 0

    if price_change <= 0 and volume_growth >= (min_growth_ratio - 1):
        return True
    return False

def detect_slow_breakout(candles, window=15):
    """
    Detects slow, creeping breakout — useful for early meme pumps.
    Looks for the last 3 candles consistently closing above average.
    """
    if len(candles) < window:
        return False

    closes = [float(c['close']) for c in candles[-window:]]
    avg = sum(closes) / len(closes)
    last_close = closes[-1]

    recent_3 = closes[-3:]
    if all(c > avg for c in recent_3) and last_close > avg * 1.01:
        return True

    return False
