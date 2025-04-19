def detect_whale_heatmap_activity(candles, threshold_ratio=3.0):
    if len(candles) < 30:
        return False
    last_close = float(candles[-1]['close'])
    last_volume = float(candles[-1]['volume'])
    avg_volume = sum(float(c['volume']) for c in candles[-30:-1]) / 29
    return last_volume > avg_volume * threshold_ratio

def detect_volume_divergence(candles):
    if len(candles) < 10:
        return False
    recent_volumes = [float(c['volume']) for c in candles[-10:]]
    recent_closes = [float(c['close']) for c in candles[-10:]]

    avg_volume = sum(recent_volumes[:-1]) / (len(recent_volumes) - 1)
    volume_spike = recent_volumes[-1] > avg_volume * 2
    price_lag = recent_closes[-1] <= recent_closes[-2]

    return volume_spike and price_lag

def detect_liquidity_trap(candles):
    if len(candles) < 5:
        return False
    low_wicks = [float(c['low']) for c in candles[-5:-1]]
    last_low = float(candles[-1]['low'])
    last_close = float(candles[-1]['close'])
    fake_break = last_low < min(low_wicks) and last_close > last_low
    return fake_break

def scan_telegram_discord_mentions(symbol):
    # Placeholder - requires integration with actual services or scrapers
    return False
