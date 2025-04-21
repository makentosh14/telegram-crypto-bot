import aiohttp
import hmac
import hashlib
from config import BYBIT_API_URL
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

async def signed_request(method: str, endpoint: str, params: dict):
    from config import BYBIT_API_KEY, BYBIT_API_SECRET

    timestamp = str(await get_server_time())
    base_params = {
        "timestamp": timestamp,
        "recvWindow": "5000",
        **params
    }

    signature = sign_request(base_params, BYBIT_API_SECRET)
    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-RECV-WINDOW": "5000",
        "Content-Type": "application/json"
    }

    url = f"{BYBIT_API_URL}{endpoint}"
    log(f"🔐 Using API Key: {BYBIT_API_KEY[:4]}****")

    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, params=params, headers=headers) as resp:
                return await resp.json()
        elif method == "POST":
            async with session.post(url, json=params, headers=headers) as resp:
                return await resp.json()

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
    result = await signed_request("POST", endpoint, params)
    log(f"📤 Order Result: {result}")
    return result

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

def get_category_for_symbol(symbol):
    return "linear" if symbol.endswith("USDT") else "spot"
