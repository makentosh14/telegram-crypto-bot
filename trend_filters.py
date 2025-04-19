from volume import fetch_btc_eth_dominance, fetch_eth_btc_ratio
from scanner import fetch_candles

def detect_breakout(candles, lookback=20):
    if len(candles) < lookback:
        return False
    highs = [float(c['high']) for c in candles[-lookback:-1]]
    current_close = float(candles[-1]['close'])
    return current_close > max(highs)

def detect_btc_trend():
    candles = fetch_candles("BTCUSDT", "1h")
    if len(candles) < 50:
        return 'unknown'
    closes = [float(c['close']) for c in candles]
    return 'uptrend' if closes[-1] > sum(closes[-20:]) / 20 else 'downtrend'

def detect_altseason():
    try:
        btc_dominance = fetch_btc_eth_dominance()
        eth_btc_ratio = fetch_eth_btc_ratio()

        if btc_dominance < 48 and eth_btc_ratio > 0.065:
            return True
        return False
    except:
        return False

def get_trend_context():
    btc_trend = detect_btc_trend()
    altseason = detect_altseason()
    return {
        "btc_trend": btc_trend,
        "altseason": altseason
    }
