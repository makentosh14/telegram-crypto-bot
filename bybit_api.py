import requests
import time
import hmac
import hashlib
import json

API_KEY = 'your_api_key_here'
API_SECRET = 'your_api_secret_here'
BASE_URL = 'https://api.bybit.com'

HEADERS = {
    'Content-Type': 'application/json',
    'X-BYBIT-API-KEY': API_KEY
}

def get_timestamp():
    return str(int(time.time() * 1000))

def sign(params):
    sorted_params = sorted(params.items())
    query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
    return hmac.new(
        bytes(API_SECRET, "utf-8"),
        bytes(query_string, "utf-8"),
        hashlib.sha256
    ).hexdigest()

def get_wallet_balance():
    url = f"{BASE_URL}/v5/account/wallet-balance"
    params = {
        "accountType": "UNIFIED"
    }
    timestamp = get_timestamp()
    sign_params = {
        "apiKey": API_KEY,
        "timestamp": timestamp,
        **params
    }
    signature = sign(sign_params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-TIMESTAMP": timestamp
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def place_order(symbol, side, qty, leverage=10, reduce_only=False):
    url = f"{BASE_URL}/v5/order/create"
    timestamp = get_timestamp()
    order_data = {
        "category": "linear",
        "symbol": symbol,
        "side": side.upper(),
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "GoodTillCancel",
        "reduceOnly": reduce_only,
        "isLeverage": True
    }
    sign_params = {
        "apiKey": API_KEY,
        "timestamp": timestamp,
        **order_data
    }
    signature = sign(sign_params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-TIMESTAMP": timestamp
    }

    response = requests.post(url, headers=headers, data=json.dumps(order_data))
    return response.json()

def set_leverage(symbol, leverage):
    url = f"{BASE_URL}/v5/position/set-leverage"
    timestamp = get_timestamp()
    params = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": str(leverage),
        "sellLeverage": str(leverage)
    }
    sign_params = {
        "apiKey": API_KEY,
        "timestamp": timestamp,
        **params
    }
    signature = sign(sign_params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-TIMESTAMP": timestamp
    }

    response = requests.post(url, headers=headers, json=params)
    return response.json()

def get_open_positions():
    url = f"{BASE_URL}/v5/position/list"
    params = {
        "category": "linear"
    }
    timestamp = get_timestamp()
    sign_params = {
        "apiKey": API_KEY,
        "timestamp": timestamp,
        **params
    }
    signature = sign(sign_params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-TIMESTAMP": timestamp
    }

    response = requests.get(url, headers=headers, params=params)
    return response.json()
