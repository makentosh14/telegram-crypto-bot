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
    log(f"📦 Body: {body}")

    async with httpx.AsyncClient() as client:
        if method.upper() == "POST":
            response = await client.post(url, headers=headers, content=body)
        elif method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        else:
            raise ValueError("Unsupported HTTP method")

    data = response.json()
    log(f"📨 Response: {data}")
    return data

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
