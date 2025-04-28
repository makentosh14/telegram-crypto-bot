# bybit_api_async.py

import aiohttp
import hmac
import hashlib
import json
import time
import socket
from logger import log

BYBIT_API_URL = "https://api.bybit.com"
BYBIT_API_KEY = "9LSEH2ZksKPSk1fJud"
BYBIT_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"


# === UTILS ===

async def get_server_time():
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return int(data["time"])

def create_signature(api_secret, payload):
    return hmac.new(api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

# === SIGNED REQUEST ===

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    url = BYBIT_API_URL + endpoint
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    body = json.dumps(params, separators=(",", ":"))

    sign_payload = timestamp + BYBIT_API_KEY + recv_window + body
    signature = create_signature(BYBIT_API_SECRET, sign_payload)

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    log(f"🔗 {method} {url}")
    log(f"📦 Headers: {headers}")
    log(f"📦 Params/Body: {params}")

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        if method.upper() == "GET":
            async with session.get(url, headers=headers, params=params) as resp:
                response = await resp.json()
                log(f"📨 Response: {response}")
                return response
        elif method.upper() == "POST":
            async with session.post(url, headers=headers, json=params) as resp:
                response = await resp.json()
                log(f"📨 Response: {response}")
                return response
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

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
        log(f"❌ Failed to parse balance: {e}")
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

# === HELPER ===

def get_category_for_symbol(symbol):
    return "linear" if symbol.endswith("USDT") else "spot"
