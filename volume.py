def detect_volume_spike(candles, multiplier=2.5):
    """
    Detects if the latest candle has a significant volume spike.
    """
    if len(candles) < 20:
        return False

    volumes = [float(c['volume']) for c in candles[:-1]]
    avg_volume = sum(volumes[-20:]) / 20
    latest_volume = float(candles[-1]['volume'])

    return latest_volume > avg_volume * multiplier


def detect_volume_divergence(candles, lookback=15):
    """
    Detects when price is going sideways/down but volume is increasing.
    """
    if len(candles) < lookback:
        return False

    closes = [float(c['close']) for c in candles[-lookback:]]
    volumes = [float(c['volume']) for c in candles[-lookback:]]

    price_change = closes[-1] - closes[0]
    volume_change = volumes[-1] - volumes[0]

    return price_change <= 0 and volume_change > 0


def detect_hidden_accumulation(candles, lookback=20):
    """
    Flags stealth accumulation: increasing volume with flat price range.
    """
    if len(candles) < lookback:
        return False

    closes = [float(c['close']) for c in candles[-lookback:]]
    highs = [float(c['high']) for c in candles[-lookback:]]
    lows = [float(c['low']) for c in candles[-lookback:]]
    volumes = [float(c['volume']) for c in candles[-lookback:]]

    price_range = max(highs) - min(lows)
    avg_volume = sum(volumes) / len(volumes)
    recent_volume = sum(volumes[-5:]) / 5

    # Steady price with increasing volume
    return price_range < (sum(closes) / len(closes)) * 0.015 and recent_volume > avg_volume * 1.5
