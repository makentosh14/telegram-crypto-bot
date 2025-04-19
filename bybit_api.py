import requests
import time
import hmac
import hashlib
import json
from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_API_URL, TRADE_MODE

def sign_request(params):
    sorted_params = sorted(params.items())
    query_string = '&'.join(f"{k}={v}" for k, v in sorted_params)
    timestamp = str(int(time.time() * 1000))
    to_sign = f"{timestamp}{BYBIT_API_KEY}{query_string}"
    signature = hmac.new(
        BYBIT_API_SECRET.encode(),
        to_sign.encode(),
        hashlib.sha256
    ).hexdigest()
    return timestamp, signature

def get_headers():
    return {
        "Content-Type": "application/json",
        "X-BYBIT-API-KEY": BYBIT_API_KEY
    }

def get_balance():
    endpoint = f"{BYBIT_API_URL}/v5/account/wallet-balance?accountType=UNIFIED"
    headers = get_headers()
    timestamp = str(int(time.time() * 1000))
    sign_payload = f"{timestamp}{BYBIT_API_KEY}"
    signature = hmac.new(BYBIT_API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()
    headers["X-BYBIT-API-SIGN"] = signature
    headers["X-BYBIT-API-TIMESTAMP"] = timestamp
    headers["X-BYBIT-API-RECV-WINDOW"] = "5000"
    try:
        resp = requests.get(endpoint, headers=headers)
        data = resp.json()
        return float(data["result"]["list"][0]["totalEquity"])
    except Exception:
        return 0

def place_order(symbol, side, qty, sl=None, tp=None):
    endpoint = f"{BYBIT_API_URL}/v5/order/create"
    headers = get_headers()
    timestamp = str(int(time.time() * 1000))

    body = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "GoodTillCancel",
    }

    if TRADE_MODE == "spot":
        body["category"] = "spot"

    if sl:
        body["stopLoss"] = str(sl)
    if tp:
        body["takeProfit"] = str(tp)

    sign_payload = f"{timestamp}{BYBIT_API_KEY}{json.dumps(body)}"
    signature = hmac.new(BYBIT_API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

    headers["X-BYBIT-API-SIGN"] = signature
    headers["X-BYBIT-API-TIMESTAMP"] = timestamp
    headers["X-BYBIT-API-RECV-WINDOW"] = "5000"

    try:
        resp = requests.post(endpoint, headers=headers, data=json.dumps(body))
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def set_leverage(symbol, leverage=10):
    endpoint = f"{BYBIT_API_URL}/v5/position/set-leverage"
    headers = get_headers()
    timestamp = str(int(time.time() * 1000))

    body = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": str(leverage),
        "sellLeverage": str(leverage),
    }

    sign_payload = f"{timestamp}{BYBIT_API_KEY}{json.dumps(body)}"
    signature = hmac.new(BYBIT_API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

    headers["X-BYBIT-API-SIGN"] = signature
    headers["X-BYBIT-API-TIMESTAMP"] = timestamp
    headers["X-BYBIT-API-RECV-WINDOW"] = "5000"

    try:
        resp = requests.post(endpoint, headers=headers, data=json.dumps(body))
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def set_margin_mode(symbol, mode="ISOLATED"):
    endpoint = f"{BYBIT_API_URL}/v5/position/set-margin-mode"
    headers = get_headers()
    timestamp = str(int(time.time() * 1000))

    body = {
        "category": "linear",
        "symbol": symbol,
        "tradeMode": 1 if mode == "ISOLATED" else 0
    }

    sign_payload = f"{timestamp}{BYBIT_API_KEY}{json.dumps(body)}"
    signature = hmac.new(BYBIT_API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

    headers["X-BYBIT-API-SIGN"] = signature
    headers["X-BYBIT-API-TIMESTAMP"] = timestamp
    headers["X-BYBIT-API-RECV-WINDOW"] = "5000"

    try:
        resp = requests.post(endpoint, headers=headers, data=json.dumps(body))
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def get_open_positions():
    endpoint = f"{BYBIT_API_URL}/v5/position/list?category=linear"
    headers = get_headers()
    timestamp = str(int(time.time() * 1000))
    sign_payload = f"{timestamp}{BYBIT_API_KEY}"
    signature = hmac.new(BYBIT_API_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

    headers["X-BYBIT-API-SIGN"] = signature
    headers["X-BYBIT-API-TIMESTAMP"] = timestamp
    headers["X-BYBIT-API-RECV-WINDOW"] = "5000"

    try:
        resp = requests.get(endpoint, headers=headers)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
