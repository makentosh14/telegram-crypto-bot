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

# === SIGNATURE GENERATION ===
def generate_signature(timestamp, api_key, recv_window, body, secret):
    payload = str(timestamp) + api_key + recv_window + body
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

# === SIGNED REQUEST ===
async def signed_request(method, endpoint, body_dict=None):
    if body_dict is None:
        body_dict = {}

    body_json = json.dumps(body_dict) if body_dict else ""

    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, BYBIT_API_KEY, RECV_WINDOW, body_json, BYBIT_API_SECRET)

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
            async with session.post(url, headers=headers, data=body_json) as resp:
                print(f"\n🔗 [POST] {endpoint}")
                print(f"✅ Status: {resp.status}")
                print(f"📨 Response: {await resp.text()}")
        else:
            raise ValueError("Unsupported method")

# === MAIN TEST ===
async def main():
    print("🚀 Testing Bybit v5 API Connection...")

    # Test Wallet Balance
    await signed_request("GET", "/v5/account/wallet-balance")

    # Test Cancel All Orders (linear futures)
    await signed_request("POST", "/v5/order/cancel-all", {
        "category": "linear"
    })

    # Test Position List (linear futures)
    await signed_request("GET", "/v5/position/list", {
        "category": "linear"
    })

if __name__ == "__main__":
    asyncio.run(main())
