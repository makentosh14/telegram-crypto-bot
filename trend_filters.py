import requests

def get_btc_trend(btc_candles):
    """
    Determines the BTC trend based on EMA cross and price position.
    Returns: 'uptrend', 'downtrend', or 'sideways'
    """
    closes = [float(c['close']) for c in btc_candles]
    if len(closes) < 100:
        return 'sideways'

    ema_short = sum(closes[-20:]) / 20
    ema_long = sum(closes[-50:]) / 50

    if ema_short > ema_long and closes[-1] > ema_short:
        return 'uptrend'
    elif ema_short < ema_long and closes[-1] < ema_short:
        return 'downtrend'
    else:
        return 'sideways'

def get_eth_btc_ratio():
    """
    Fetches the ETH/BTC ratio from Binance or another source.
    """
    try:
        response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=ETHBTC", timeout=3)
        if response.status_code == 200:
            eth_btc = float(response.json()['price'])
            return eth_btc
    except:
        pass
    return None

def detect_altseason(btc_dominance_data, eth_btc_ratio):
    """
    Uses BTC dominance drop + rising ETH/BTC ratio to detect early altseason.
    """
    if not btc_dominance_data or not eth_btc_ratio:
        return False

    recent = btc_dominance_data[-1]
    previous = btc_dominance_data[-5]

    if recent < previous - 1.0 and eth_btc_ratio > 0.06:
        return True
    return False

def get_trend_context():
    """
    Used by the bot to determine if it should:
    - Be aggressive with alts (altseason)
    - Be meme-focused (meme season)
    - Be conservative (BTC dominance)
    Returns: {
        'btc_trend': 'uptrend'/'downtrend'/'sideways',
        'eth_btc_ratio': float,
        'altseason': True/False
    }
    """
    btc_candles = fetch_btc_candles()  # from Bybit or Binance
    btc_dominance = fetch_btc_dominance()  # from CoinGecko or alt API
    eth_btc = get_eth_btc_ratio()

    btc_trend = get_btc_trend(btc_candles)
    altseason = detect_altseason(btc_dominance, eth_btc)

    return {
        'btc_trend': btc_trend,
        'eth_btc_ratio': eth_btc,
        'altseason': altseason
    }

# Mock placeholder functions – you can replace these with real Bybit/WebSocket sources.
def fetch_btc_candles():
    return []

def fetch_btc_dominance():
    return [52.1, 52.0, 51.8, 51.4, 50.8]  # Example mock data
