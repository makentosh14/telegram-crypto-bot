import requests
import time
import hmac
import hashlib
import json
import uuid
from urllib.parse import urlencode

BASE_URL = "https://api.bybit.com"
API_KEY = "tL7vmTEDT5B8mp4Yer"
API_SECRET = "xH5S3U3dkLeQJ739cl9AZ0MMNQkerD53vAXN"

HEADERS = {
    "X-BYBIT-API-KEY": API_KEY,
    "Content-Type": "application/json"
}


def get_timestamp():
    return str(int(time.time() * 1000))


def sign_request(params):
    param_str = urlencode(sorted(params.items()))
    signature = hmac.new(bytes(API_SECRET, "utf-8"), bytes(param_str, "utf-8"), hashlib.sha256).hexdigest()
    return signature


def get_balance(coin="USDT"):
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": "UNIFIED"}
    timestamp = get_timestamp()
    params["timestamp"] = timestamp
    signature = sign_request(params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.get(BASE_URL + endpoint, headers=headers, params=params)
    if response.status_code == 200:
        balances = response.json()["result"]["list"][0]["coin"]
        for item in balances:
            if item["coin"] == coin:
                return float(item["availableToTrade"])
    return 0.0


def get_open_orders(symbol):
    endpoint = "/v5/order/realtime"
    params = {
        "category": "linear",
        "symbol": symbol,
        "timestamp": get_timestamp()
    }
    signature = sign_request(params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.get(BASE_URL + endpoint, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()["result"]["list"]
    return []


def cancel_all_orders(symbol):
    endpoint = "/v5/order/cancel-all"
    data = {
        "category": "linear",
        "symbol": symbol,
        "timestamp": get_timestamp()
    }
    signature = sign_request(data)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.post(BASE_URL + endpoint, headers=headers, json=data)
    return response.status_code == 200


def set_leverage(symbol, buy_leverage=10, sell_leverage=10):
    endpoint = "/v5/position/set-leverage"
    data = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": str(buy_leverage),
        "sellLeverage": str(sell_leverage),
        "timestamp": get_timestamp()
    }
    signature = sign_request(data)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.post(BASE_URL + endpoint, headers=headers, json=data)
    return response.status_code == 200


def switch_margin_mode(symbol, mode="CROSS"):
    endpoint = "/v5/position/switch-isolated"
    data = {
        "category": "linear",
        "symbol": symbol,
        "tradeMode": 0 if mode.upper() == "CROSS" else 1,
        "buyLeverage": "10",
        "sellLeverage": "10",
        "timestamp": get_timestamp()
    }
    signature = sign_request(data)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.post(BASE_URL + endpoint, headers=headers, json=data)
    return response.status_code == 200


def place_order(symbol, side, qty, entry_price=None, sl_price=None, tp_price=None, reduce_only=False):
    endpoint = "/v5/order/create"
    order_link_id = str(uuid.uuid4())

    data = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market" if entry_price is None else "Limit",
        "qty": str(qty),
        "timeInForce": "GTC",
        "reduceOnly": reduce_only,
        "orderLinkId": order_link_id,
        "timestamp": get_timestamp()
    }

    if entry_price:
        data["price"] = str(entry_price)

    signature = sign_request(data)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }

    response = requests.post(BASE_URL + endpoint, headers=headers, json=data)

    if response.status_code == 200 and response.json().get("result"):
        order_id = response.json()["result"]["orderId"]
        if sl_price or tp_price:
            time.sleep(1)
            place_sl_tp_order(symbol, side, qty, sl_price, tp_price)
        return order_id
    else:
        print(f"Order failed: {response.text}")
        return None


def place_sl_tp_order(symbol, side, qty, sl_price=None, tp_price=None):
    endpoint = "/v5/order/create"
    opposite_side = "Sell" if side == "Buy" else "Buy"
    timestamp = get_timestamp()

    if tp_price:
        tp_data = {
            "category": "linear",
            "symbol": symbol,
            "side": opposite_side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(tp_price),
            "timeInForce": "GTC",
            "reduceOnly": True,
            "timestamp": timestamp,
            "orderLinkId": str(uuid.uuid4())
        }
        tp_data["X-BYBIT-SIGN"] = sign_request(tp_data)
        headers = {**HEADERS, "X-BYBIT-SIGN": sign_request(tp_data)}
        requests.post(BASE_URL + endpoint, headers=headers, json=tp_data)

    if sl_price:
        sl_data = {
            "category": "linear",
            "symbol": symbol,
            "side": opposite_side,
            "orderType": "Market",
            "qty": str(qty),
            "triggerDirection": 2 if side == "Buy" else 1,
            "triggerPrice": str(sl_price),
            "reduceOnly": True,
            "timeInForce": "GTC",
            "stopLoss": str(sl_price),
            "timestamp": timestamp,
            "orderLinkId": str(uuid.uuid4())
        }
        sl_data["X-BYBIT-SIGN"] = sign_request(sl_data)
        headers = {**HEADERS, "X-BYBIT-SIGN": sign_request(sl_data)}
        requests.post(BASE_URL + endpoint, headers=headers, json=sl_data)


def get_symbols():
    endpoint = "/v5/market/instruments-info"
    params = {
        "category": "linear",
        "limit": 1000,
        "timestamp": get_timestamp()
    }
    signature = sign_request(params)
    headers = {
        **HEADERS,
        "X-BYBIT-SIGN": signature
    }
    response = requests.get(BASE_URL + endpoint, headers=headers, params=params)
    if response.status_code == 200:
        return [item["symbol"] for item in response.json()["result"]["list"] if "USDT" in item["symbol"]]
    return []


