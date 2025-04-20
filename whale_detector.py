# whale_detector.py

import random

def detect_whale_activity(symbol, candles):
    """
    Simulate whale detection logic.
    In production, this would include:
    - Unusual buy volume
    - Large wallet inflows
    - On-chain transfers
    - Repeated large candle spikes
    """
    if not candles or len(candles) < 5:
        return False

    large_candle_count = 0
    for c in candles[-5:]:
        body = abs(float(c['close']) - float(c['open']))
        high_low = float(c['high']) - float(c['low'])
        if high_low > 0 and (body / high_low) > 0.6:
            large_candle_count += 1

    # Simulate whale logic
    whale_detected = large_candle_count >= 3 or random.random() < 0.05
    return whale_detected
