# whale_tracker.py

def detect_whale_activity(candles, volume_threshold=1000000):
    """
    Looks for a large volume spike vs prior average.
    Use with meme/low-cap coins for stealth entry alerts.
    """
    if len(candles) < 20:
        return False

    volumes = [float(c['volume']) for c in candles[-20:-1]]
    recent_volume = float(candles[-1]['volume'])
    avg_volume = sum(volumes) / len(volumes)

    return recent_volume > avg_volume * 3 and recent_volume > volume_threshold
