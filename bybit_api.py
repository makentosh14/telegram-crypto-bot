import requests
import hmac
import hashlib
import time
import json
from config import BYBIT_API_KEY, BYBIT_API_SECRET

BASE_URL = "https://api.bybit.com"

def get_server_time():
    return int(time.time() * 1000)

def sign_request(secret, params):
    sorted_params = sorted(params.items())
    query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
    return hmac.new(bytes(secret, "utf-8"), bytes(query_string, "utf-8"), hashlib.sha256).hexdigest()

def private_request(method, endpoint, params=None):
    if params is None:
        params = {}

    params["api_key"] = BYBIT_API_KEY
    params["timestamp"] = get_server_time()
    params["recvWindow"] = 5000
    params["sign"] = sign_request(BYBIT_API_SECRET, params)

    if method == "GET":
        response = requests.get(BASE_URL + endpoint, params=params)
    elif method == "POST":
        response = requests.post(BASE_URL + endpoint, data=params)
    else:
        raise ValueError("Unsupported method")

    if response.status_code != 200:
        print(f"❌ API Error: {response.text}")
    return response.json()

def get_balance():
    result = private_request("GET", "/v2/private/wallet/balance", {"coin": "USDT"})
    return float(result["result"]["USDT"]["available_balance"])

def get_open_positions(symbol):
    data = private_request("GET", "/v2/private/position/list", {"symbol": symbol})
    return data.get("result", [])

def set_leverage(symbol, leverage):
    private_request("POST", "/v2/private/position/leverage/save", {
        "symbol": symbol,
        "leverage": leverage
    })

def set_leverage_mode(symbol, mode="Cross"):
    if mode.lower() not in ["cross", "isolated"]:
        mode = "Cross"
    private_request("POST", "/v2/private/position/switch-isolated", {
        "symbol": symbol,
        "is_isolated": 0 if mode.lower() == "cross" else 1,
        "buy_leverage": 10,
        "sell_leverage": 10
    })

def place_order(symbol, side, qty, entry_price, tp_price=None, sl_price=None):
    print(f"📤 Placing order: {symbol} | {side} | Qty: {qty}")
    params = {
        "side": side,
        "symbol": symbol,
        "order_type": "Market",
        "qty": qty,
        "time_in_force": "GoodTillCancel",
        "reduce_only": False,
        "close_on_trigger": False
    }
    response = private_request("POST", "/v2/private/order/create", params)
    print(f"🟢 Order Response: {response}")

    if tp_price:
        set_tp(symbol, side, qty, tp_price)
    if sl_price:
        set_sl(symbol, side, qty, sl_price)

def set_tp(symbol, side, qty, tp_price):
    trigger = {
        "symbol": symbol,
        "side": "Sell" if side == "Buy" else "Buy",
        "order_type": "Limit",
        "qty": qty,
        "price": tp_price,
        "time_in_force": "GoodTillCancel",
        "reduce_only": True
    }
    res = private_request("POST", "/v2/private/order/create", trigger)
    print(f"🎯 TP Order: {res}")

def set_sl(symbol, side, qty, sl_price):
    trigger = {
        "symbol": symbol,
        "side": "Sell" if side == "Buy" else "Buy",
        "order_type": "Market",
        "qty": qty,
        "stop_loss": sl_price,
        "reduce_only": True,
        "time_in_force": "ImmediateOrCancel"
    }
    res = private_request("POST", "/v2/private/order/create", trigger)
    print(f"🛡 SL Order: {res}")

