import httpx
import hmac
import hashlib
import json
import time
from logger import log

# === CONFIG ===
BYBIT_API_URL = "https://api.bybit.com"
BYBIT_API_KEY = "9LSEH2ZksKPSk1fJud"
BYBIT_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"

def create_signature(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

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
    else:
        body = json.dumps(params, separators=(",", ":"))
        sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body}"
        full_url = url

    signature = create_signature(BYBIT_API_SECRET, sign_payload)

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    log(f"🔗 {method} {full_url}")
    log(f"📦 Headers: {headers}")
    log(f"📦 Params: {params}")

    async with httpx.AsyncClient() as client:
        if method.upper() == "GET":
            response = await client.get(full_url, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(full_url, headers=headers, json=params)
        else:
            raise ValueError("Unsupported HTTP method")

    result = response.json()
    log(f"📨 Response: {result}")
    return result

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
