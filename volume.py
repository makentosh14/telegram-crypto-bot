def detect_volume_spike(candles, multiplier=2.5, lookback=20):
    if not candles or len(candles) < lookback + 1:
        return False
    recent_volumes = [float(c['volume']) for c in candles[-(lookback + 1):-1]]
    avg_volume = sum(recent_volumes) / len(recent_volumes)
    latest_volume = float(candles[-1]['volume'])
    return latest_volume > avg_volume * multiplier

def calculate_average_volume(candles, period=20):
    if not candles or len(candles) < period:
        return 0
    volumes = [float(c['volume']) for c in candles[-period:]]
    return sum(volumes) / len(volumes)

def detect_stealth_accumulation(candles, lookback=20):
    if not candles or len(candles) < lookback:
        return False
    volumes = [float(c['volume']) for c in candles[-lookback:]]
    closes = [float(c['close']) for c in candles[-lookback:]]
    avg_volume = sum(volumes[:-1]) / (lookback - 1)
    if volumes[-1] > avg_volume and closes[-1] > closes[-2]:
        return True
    return False
