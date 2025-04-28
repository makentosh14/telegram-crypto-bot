# bybit_api_async.py

import aiohttp
import hmac
import hashlib
import json
from config import BYBIT_API_URL, BYBIT_API_KEY, BYBIT_API_SECRET
from logger import log

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return int(data["time"])

def sign_request(params: dict, secret: str):
    sorted_params = dict(sorted(params.items()))
    query_string = "&".join([f"{k}={v}" for k, v in sorted_params.items()])
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    url = BASE_URL + endpoint

    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    payload = {
        "category": params.get("category"),
        "symbol": params.get("symbol"),
        "side": params.get("side"),
        "orderType": params.get("orderType"),
        "qty": params.get("qty"),
        "timeInForce": params.get("timeInForce"),
        "reduceOnly": params.get("reduceOnly", False)
    }

    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    body = json.dumps(payload)

    # Create signature
    sign_payload = timestamp + API_KEY + recv_window + body
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(url, headers=headers, data=body) as resp:
                return await resp.json()
        elif method == "GET":
            async with session.get(url, headers=headers, params=payload) as resp:
                return await resp.json()
                log(f"📨 Response: {response}")
                return response



    async with aiohttp.ClientSession() as session:
        if method.upper() == "GET":
            async with session.get(url, params=base_params, headers=headers) as resp:
                result = await resp.json()
                log(f"\ud83d\udce6 Response: {result}")
                return result
        elif method.upper() == "POST":
            async with session.post(url, json=base_params, headers=headers) as resp:
                result = await resp.json()
                log(f"\ud83d\udce6 Response: {result}")
                return result

# === TRADING FUNCTIONS ===

async def place_market_order(symbol, side, qty, market_type="linear", reduce_only=False):
    endpoint = "/v5/order/create"
    params = {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "reduceOnly": reduce_only
    }
    return await signed_request("POST", endpoint, params)

async def get_balance(asset="USDT", wallet_type="UNIFIED"):
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": wallet_type}
    result = await signed_request("GET", endpoint, params)
    try:
        balances = result["result"]["list"][0]["coin"]
        for coin in balances:
            if coin["coin"] == asset:
                return float(coin["availableToWithdraw"])
    except Exception as e:
        log(f"\u274c Failed to parse balance: {e}")
    return 0

async def set_leverage(symbol, buy_leverage=5, sell_leverage=5):
    endpoint = "/v5/position/set-leverage"
    params = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": str(buy_leverage),
        "sellLeverage": str(sell_leverage)
    }
    return await signed_request("POST", endpoint, params)

async def set_margin_mode(symbol, mode="ISOLATED"):
    endpoint = "/v5/position/set-margin-mode"
    params = {
        "category": "linear",
        "symbol": symbol,
        "tradeMode": 1 if mode == "ISOLATED" else 0
    }
    return await signed_request("POST", endpoint, params)

async def get_open_positions():
    endpoint = "/v5/position/list"
    params = {"category": "linear"}
    result = await signed_request("GET", endpoint, params)
    return result.get("result", {}).get("list", [])

async def cancel_all_orders(symbol, category="linear"):
    endpoint = "/v5/order/cancel-all"
    params = {
        "category": category,
        "symbol": symbol
    }
    return await signed_request("POST", endpoint, params)

async def get_open_orders(symbol, category="linear"):
    endpoint = "/v5/order/realtime"
    params = {
        "category": category,
        "symbol": symbol
    }
    result = await signed_request("GET", endpoint, params)
    return result.get("result", {}).get("list", [])

# Helper

def get_category_for_symbol(symbol):
    return "linear" if symbol.endswith("USDT") else "spot"
