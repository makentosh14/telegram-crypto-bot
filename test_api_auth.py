# final_test_api_auth.py

import aiohttp
import asyncio
import time
import hmac
import hashlib
import urllib.parse

# === YOUR API KEYS ===
API_KEY = "9LSEH2ZksKPSk1fJud"
API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"
BASE_URL = "https://api.bybit.com"
RECV_WINDOW = "5000"

# === SIGNATURE ===
def generate_signature(params, secret):
    sorted_params = sorted(params.items())
    encoded = urllib.parse.urlencode(sorted_params)
    return hmac.new(secret.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).hexdigest()

# === SIGNED GET REQUEST ===
async def signed_get(endpoint, params):
    params.update({
        "api_key": API_KEY,
        "timestamp": str(int(time.time() * 1000)),
        "recvWindow": RECV_WINDOW
    })
    params["sign"] = generate_signature(params, API_SECRET)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(BASE_URL + endpoint, params=params, headers=headers) as resp:
            print(f"\n🔗 GET {BASE_URL}{endpoint}")
            print(f"📦 Full URL: {str(resp.url)}")
            print(f"✅ Status: {resp.status}")
            body = await resp.text()
            print(f"📨 Response Body: {body}")
            return resp.status, body

# === SIGNED POST REQUEST ===
async def signed_post(endpoint, payload):
    payload.update({
        "api_key": API_KEY,
        "timestamp": str(int(time.time() * 1000)),
        "recvWindow": RECV_WINDOW
    })
    payload["sign"] = generate_signature(payload, API_SECRET)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(BASE_URL + endpoint, data=payload, headers=headers) as resp:
            print(f"\n🔗 POST {BASE_URL}{endpoint}")
            print(f"📦 Payload: {payload}")
            print(f"✅ Status: {resp.status}")
            body = await resp.text()
            print(f"📨 Response Body: {body}")
            return resp.status, body

# === MAIN TEST ===
async def main():
    print("\n🚀 Testing Bybit API Connection...\n")

    await asyncio.sleep(1)

    # Wallet Balance Test (GET)
    await signed_get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})

    await asyncio.sleep(1)

    # Cancel All Orders Test (POST)
    await signed_post("/v5/order/cancel-all", {"category": "linear"})

    await asyncio.sleep(1)

    # Get Position List Test (GET)
    await signed_get("/v5/position/list", {"category": "linear"})

if __name__ == "__main__":
    asyncio.run(main())
