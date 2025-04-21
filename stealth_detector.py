# stealth_detector.py

def detect_volume_divergence(candles):
    """
    Detects stealth accumulation where volume rises while price is flat or declining.
    Returns True if detected, False otherwise.
    """
    if len(candles) < 20:
        return False

    recent = candles[-10:]
    prices = [float(c['close']) for c in recent]
    volumes = [float(c['volume']) for c in recent]

    price_change = prices[-1] - prices[0]
    volume_change = volumes[-1] - volumes[0]

    if price_change <= 0 and volume_change > 0:
        return True
    return False

def detect_slow_breakout(candles, window=15):
    """
    Detects slow, creeping breakout — not a sudden spike.
    Useful for meme coin stealth pumps.
    """
    if len(candles) < window:
        return False

    closes = [float(c['close']) for c in candles[-window:]]
    avg = sum(closes) / len(closes)
    recent = closes[-1]

    return recent > avg * 1.01  # >1% slow climb
