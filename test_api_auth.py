# test_api_auth.py
import aiohttp
import asyncio
import time
import hmac
import hashlib
import json
import os

# === CONFIG ===
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY") or "YOUR_API_KEY"
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET") or "YOUR_API_SECRET"
BASE_URL = "https://api.bybit.com"

RECV_WINDOW = "5000"

# === SIGNATURE FUNCTION ===
def sign(timestamp, api_key, recv_window, body, secret):
    payload = f"{timestamp}{api_key}{recv_window}{body}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

# === SIGNED REQUEST FUNCTION ===
async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    body = json.dumps(params) if params else "{}"

    timestamp = str(int(time.time() * 1000))
    signature = sign(timestamp, BYBIT_API_KEY, RECV_WINDOW, body, BYBIT_API_SECRET)

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-RECV-WINDOW": RECV_WINDOW,
        "Content-Type": "application/json"
    }

    url = BASE_URL + endpoint

    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                print(f"\n🔗 [GET] {endpoint}")
                print(f"✅ Status: {resp.status}")
                print(f"📨 Response: {await resp.text()}")
        elif method == "POST":
            async with session.post(url, headers=headers, data=body) as resp:
                print(f"\n🔗 [POST] {endpoint}")
                print(f"✅ Status: {resp.status}")
                print(f"📨 Response: {await resp.text()}")

# === MAIN TEST RUN ===
async def main():
    print("🚀 Testing Bybit API Authentication...")

    await signed_request("GET", "/v5/account/wallet-balance", {})
    await signed_request("POST", "/v5/order/cancel-all", {"category": "linear"})
    await signed_request("GET", "/v5/position/list", {"category": "linear"})

if __name__ == "__main__":
    asyncio.run(main())
