# test_api_auth_debug.py
import aiohttp
import asyncio
import time
import hmac
import hashlib
import json
import os

BYBIT_API_KEY = "9LSEH2ZksKPSk1fJud"
BYBIT_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"
BASE_URL = "https://api.bybit.com"

RECV_WINDOW = "5000"

def sign(timestamp, api_key, recv_window, body, secret):
    payload = f"{timestamp}{api_key}{recv_window}{body}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

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

    print(f"\n🔗 {method} {url}")
    print(f"📦 Headers: {headers}")
    print(f"📦 Body: {body}")

    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url, headers=headers) as resp:
                    status = resp.status
                    text = await resp.text()
                    print(f"✅ Status: {status}")
                    print(f"📨 Response Body: {text}")
                    print(f"📨 Response Headers: {dict(resp.headers)}")
            elif method == "POST":
                async with session.post(url, headers=headers, data=body) as resp:
                    status = resp.status
                    text = await resp.text()
                    print(f"✅ Status: {status}")
                    print(f"📨 Response Body: {text}")
                    print(f"📨 Response Headers: {dict(resp.headers)}")
        except Exception as e:
            print(f"❌ Request failed: {e}")

async def main():
    print("🚀 Detailed Debug Test Start")

    await signed_request("GET", "/v5/account/wallet-balance", {})
    await signed_request("POST", "/v5/order/cancel-all", {"category": "linear"})
    await signed_request("GET", "/v5/position/list", {"category": "linear"})

if __name__ == "__main__":
    asyncio.run(main())
