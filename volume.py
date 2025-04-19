import requests

def detect_volume_spike(candles, multiplier=2):
    if len(candles) < 21:
        return False
    volumes = [float(c['volume']) for c in candles[-21:-1]]
    avg_volume = sum(volumes) / len(volumes)
    current_volume = float(candles[-1]['volume'])
    return current_volume > avg_volume * multiplier

def fetch_btc_eth_dominance():
    url = "https://api.coingecko.com/api/v3/global"
    response = requests.get(url)
    data = response.json()
    btc_dom = data['data']['market_cap_percentage']['btc']
    eth_dom = data['data']['market_cap_percentage']['eth']
    return btc_dom

def fetch_eth_btc_ratio():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "ethereum,bitcoin",
        "vs_currencies": "usd"
    }
    response = requests.get(url, params=params)
    prices = response.json()
    eth_price = prices['ethereum']['usd']
    btc_price = prices['bitcoin']['usd']
    return eth_price / btc_price if btc_price != 0 else 0
