import requests
from config import BTC_SYMBOL

def get_trend_context():
    btc_candles = fetch_btc_candles()

    btc_trend = detect_btc_trend(btc_candles)
    altseason = detect_altseason()

    return {
        "btc_trend": btc_trend,
        "altseason": altseason
    }

def fetch_btc_candles():
    url = f"https://api.bybit.com/v5/market/kline?symbol={BTC_SYMBOL}&interval=60&limit=50"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get("result", {}).get("list", [])
    except Exception as e:
        print(f"Error fetching BTC candles: {e}")
        return []

def detect_btc_trend(candles):
    if len(candles) < 2:
        return "unknown"
    last_close = float(candles[-1][4])
    prev_close = float(candles[-2][4])
    return "uptrend" if last_close > prev_close else "downtrend"

def detect_altseason():
    # Placeholder for real altseason detection logic (e.g. ETH/BTC ratio, meme coin volume)
    return False

def detect_breakout(candles, lookback=20):
    if len(candles) < lookback:
        return False
    highs = [float(c['high']) for c in candles[-lookback:-1]]
    close = float(candles[-1]['close'])
    return close > max(highs)
