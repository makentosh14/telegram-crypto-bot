# trend_filters.py

import random

def get_btc_trend():
    # This is a placeholder — normally use real candle MA logic
    return random.choice(["uptrend", "downtrend", "ranging"])

def is_altseason():
    """
    Simulated logic for altseason detection.
    Replace with:
    - ETH/BTC trend rising
    - Meme volume surging
    - BTC dominance falling
    """
    roll = random.randint(0, 10)
    return roll > 7  # ~30% chance to simulate altseason trigger

def get_trend_context():
    return {
        "btc_trend": get_btc_trend(),
        "altseason": is_altseason()
    }
