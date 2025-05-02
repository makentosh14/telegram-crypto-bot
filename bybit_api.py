import httpx
import hmac
import hashlib
import json
import time
from logger import log

# === CONFIG ===
BYBIT_API_URL = "https://api.bybit.com"
BYBIT_API_KEY = "NuGJJSlzNeQG2bMb8h"
BYBIT_API_SECRET = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"

# === SIGNATURE UTILITY ===
def create_signature(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

# === SIGNED REQUEST WRAPPER ===
async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    url = BYBIT_API_URL + endpoint
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    if method.upper() == "GET":
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_string}"
        full_url = f"{url}?{query_string}" if query_string else url
        body = None
    else:
        body = json.dumps(params, separators=(",", ":"))
        sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body}"
        full_url = url

    signature = create_signature(BYBIT_API_SECRET, sign_payload)

    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    log(f"🔗 {method} {full_url}")
    log(f"📦 Headers: {headers}")
    if body:
        log(f"📦 Body: {body}")
    else:
        log(f"📦 Params: {params}")
    log(f"🧾 Signing payload: {sign_payload}")

    async with httpx.AsyncClient() as client:
        if method.upper() == "GET":
            response = await client.get(full_url, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(full_url, headers=headers, data=body)
        else:
            raise ValueError("Unsupported HTTP method")

    result = response.json()
    log(f"📨 Response: {result}")
    return result

# === BALANCE FUNCTIONS ===
async def get_wallet_balance():
    return await signed_request("GET", "/v5/account/wallet-balance", {
        "accountType": "UNIFIED"
    })

# ✅ NEW: Fetch only futures 'availableToTrade' balance for USDT
async def get_futures_available_balance():
    result = await get_wallet_balance()
    try:
        usdt = next(
            coin for coin in result["result"]["list"][0]["coin"] if coin["coin"] == "USDT"
        )
        return float(usdt.get("availableToTrade", 0))
    except Exception as e:
        log(f"❌ Failed to parse availableToTrade: {e}", level="ERROR")
        return 0

# === TRADE FUNCTION ===
async def place_market_order(symbol, side, qty, market_type="linear", reduce_only=False):
    return await signed_request("POST", "/v5/order/create", {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "reduceOnly": reduce_only
    })

async def get_futures_available_balance():
    try:
        response = await get_wallet_balance()
        if response.get("retCode") != 0:
            return 0.0
        return float(response["result"]["list"][0]["totalAvailableBalance"])
    except Exception as e:
        log(f"❌ Failed to fetch available futures balance: {e}", level="ERROR")
        return 0.0
