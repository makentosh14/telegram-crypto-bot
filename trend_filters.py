from websocket_candles import live_candles
import numpy as np

def detect_simple_trend(prices):
    if len(prices) < 30:
        return "ranging"
    short_ma = np.mean(prices[-10:])
    long_ma = np.mean(prices[-30:])
    if short_ma > long_ma * 1.01:
        return "uptrend"
    elif short_ma < long_ma * 0.99:
        return "downtrend"
    else:
        return "ranging"

def get_btc_trend():
    btc_candles = live_candles.get("BTCUSDT", {}).get("15", [])
    closes = [float(c['close']) for c in btc_candles]
    return detect_simple_trend(closes)

def is_altseason():
    ethbtc_candles = live_candles.get("ETHBTC", {}).get("15", [])
    if not ethbtc_candles or len(ethbtc_candles) < 30:
        return False

    closes = [float(c["close"]) for c in ethbtc_candles]
    short_ma = np.mean(closes[-10:])
    long_ma = np.mean(closes[-30:])

    return short_ma > long_ma * 1.01  # ETH gaining vs BTC = altseason-like

def get_trend_context():
    return {
        "btc_trend": get_btc_trend(),
        "altseason": is_altseason()
    }
