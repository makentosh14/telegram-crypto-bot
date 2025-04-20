def detect_volume_spike(candles, multiplier=2.0):
    if len(candles) < 20:
        return False

    volumes = [float(c['volume']) for c in candles[-20:-1]]
    avg_volume = sum(volumes) / len(volumes)
    current_volume = float(candles[-1]['volume'])

    return current_volume > avg_volume * multiplier

def detect_volume_divergence(candles):
    if len(candles) < 5:
        return False

    prev_price = float(candles[-2]['close'])
    current_price = float(candles[-1]['close'])

    prev_volume = float(candles[-2]['volume'])
    current_volume = float(candles[-1]['volume'])

    price_rising = current_price > prev_price
    volume_falling = current_volume < prev_volume

    return price_rising and volume_falling
