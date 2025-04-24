# pump_detector.py

import time
from volume import is_volume_spike
from whale_detector import detect_whale_activity
from stealth_detector import detect_slow_breakout
from social_sentiment import check_social_sentiment

def detect_early_pump(candles_by_tf, symbol):
    results = {
        "volume_spike": False,
        "whale_activity": False,
        "base_breakout": False,
        "social_hype": False,
        "trigger_count": 0
    }

    # Use 1m and 3m for most signals
    tf1 = candles_by_tf.get("1", [])
    tf3 = candles_by_tf.get("3", [])

    if tf1 and is_volume_spike(tf1, multiplier=2.5):
        results["volume_spike"] = True
        results["trigger_count"] += 1

    if tf3 and detect_whale_activity(tf3, threshold_ratio=1.8):
        results["whale_activity"] = True
        results["trigger_count"] += 1

    if tf3 and detect_slow_breakout(tf3):
        results["base_breakout"] = True
        results["trigger_count"] += 1

    if check_social_sentiment(symbol):
        results["social_hype"] = True
        results["trigger_count"] += 1

    return results
