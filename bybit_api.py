import httpx
import hmac
import hashlib
import json
import time
from logger import log

BYBIT_API_URL = "https://api.bybit.com"
BYBIT_API_KEY = "9LSEH2ZksKPSk1fJud"
BYBIT_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"

def create_signature(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    url = BYBIT_API_URL + endpoint
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    body = json.dumps(params, separators=(",", ":")) if method.upper() == "POST" else ""

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
        if method.upper() == "GET":
            resp = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            resp = await client.post(url, headers=headers, content=body)
        else:
            raise ValueError("Unsupported HTTP method")

        result = resp.json()
        log(f"📨 Response: {result}")
        return result

# === TRADING ===

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

async def get_balance(asset="USDT"):
    result = await signed_request("GET", "/v5/account/wallet-balance", {
        "accountType": "UNIFIED"
    })
    try:
        coins = result["result"]["list"][0]["coin"]
        for coin in coins:
            if coin["coin"] == asset:
                return float(coin["availableToWithdraw"])
    except Exception as e:
        log(f"❌ Failed to parse balance: {e}")
    return 0
