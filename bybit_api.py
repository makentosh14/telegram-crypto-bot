import requests
import time
import hmac
import hashlib
import json

from config import BYBIT_API_KEY, BYBIT_API_SECRET, BASE_URL

def sign_request(params, api_secret):
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def get_server_time():
    return int(time.time() * 1000)

def make_request(method, endpoint, params=None, is_private=False):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if is_private:
        timestamp = str(get_server_time())
        signature = sign_request(params or {}, BYBIT_API_SECRET)
        headers.update({
            "X-BYBIT-API-KEY": BYBIT_API_KEY,
            "X-BYBIT-API-SIGN": signature,
            "X-BYBIT-API-TIMESTAMP": timestamp
        })
    try:
        response = requests.request(method, url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return None

def get_balance():
    endpoint = "/v5/account/wallet-balance"
    return make_request("GET", endpoint, is_private=True)

def place_order(symbol, side, qty, entry_price=None, sl=None, tp=None):
    endpoint = "/v5/order/create"
    order = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty,
        "timeInForce": "GoodTillCancel",
    }
    if sl:
        order["stopLoss"] = str(sl)
    if tp:
        order["takeProfit"] = str(tp)
    return make_request("POST", endpoint, order, is_private=True)

def set_leverage(symbol, buy_leverage, sell_leverage):
    endpoint = "/v5/position/set-leverage"
    payload = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": buy_leverage,
        "sellLeverage": sell_leverage
    }
    return make_request("POST", endpoint, payload, is_private=True)

def set_margin_mode(symbol, mode="ISOLATED"):
    endpoint = "/v5/position/set-margin-mode"
    payload = {
        "category": "linear",
        "symbol": symbol,
        "marginMode": mode,
    }
    return make_request("POST", endpoint, payload, is_private=True)

def get_open_positions():
    endpoint = "/v5/position/list"
    return make_request("GET", endpoint, {"category": "linear"}, is_private=True)

def close_position(symbol):
    endpoint = "/v5/order/create"
    order = {
        "category": "linear",
        "symbol": symbol,
        "side": "Sell",
        "orderType": "Market",
        "reduceOnly": True,
        "qty": 1
    }
    return make_request("POST", endpoint, order, is_private=True)
