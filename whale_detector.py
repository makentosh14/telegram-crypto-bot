def detect_whale_activity(candles, threshold_ratio=1.8):
    if len(candles) < 6:
        return False

    recent = candles[-3:]
    earlier = candles[-6:-3]

    avg_early_volume = sum(float(c['volume']) for c in earlier) / len(earlier)
    avg_recent_volume = sum(float(c['volume']) for c in recent) / len(recent)

    # Candle body size increase (whale-style candle)
    body_sizes = [abs(float(c['close']) - float(c['open'])) for c in recent]
    avg_body = sum(body_sizes) / len(body_sizes)

    whale_detected = avg_recent_volume > avg_early_volume * threshold_ratio and avg_body > 0.5

    return whale_detected
