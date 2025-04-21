# volume.py

def get_average_volume(candles, window=20):
    """
    Calculates average volume over the last N candles.
    """
    volumes = [float(c['volume']) for c in candles[-window:] if 'volume' in c]
    if not volumes:
        return 0
    return sum(volumes) / len(volumes)

def is_volume_spike(candles, multiplier=2.0, window=20):
    """
    Detects if latest candle volume is a spike vs avg.
    """
    if len(candles) < window + 1:
        return False
    avg = get_average_volume(candles, window)
    latest = float(candles[-1]['volume'])
    return latest > avg * multiplier
