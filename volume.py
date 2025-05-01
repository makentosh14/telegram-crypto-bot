def is_volume_spike(candles, multiplier=2.0):
    """
    Detects if the most recent candle's volume is significantly higher than the average of the previous 10.
    """
    if len(candles) < 10:
        return False

    volumes = [float(c['volume']) for c in candles[-11:-1]]
    avg_volume = sum(volumes) / len(volumes)
    current_volume = float(candles[-1]['volume'])

    return current_volume > avg_volume * multiplier


def detect_slow_ramp(candles, lookback=6):
    """
    Detects gradual volume increase with flat price action and bullish last candle.
    Ideal for early stealth accumulation or meme ramps.
    """
    if len(candles) < lookback + 2:
        return False

    volumes = [float(c['volume']) for c in candles[-lookback:]]
    closes = [float(c['close']) for c in candles[-lookback:]]
    opens = [float(c['open']) for c in candles[-lookback:]]

    vol_uptrend = all(volumes[i] <= volumes[i + 1] for i in range(len(volumes) - 1))
    price_steady = abs(closes[-1] - opens[0]) / opens[0] < 0.02  # <2% price movement
    last_candle_bullish = closes[-1] > opens[-1]

    return vol_uptrend and price_steady and last_candle_bullish
