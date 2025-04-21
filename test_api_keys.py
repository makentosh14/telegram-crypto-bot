import os
import aiohttp
import asyncio
import hmac
import hashlib
import time

# Replace these with your fresh keys
BYBIT_API_KEY = "ZWnRCXNtjKrbPZxUjA"
BYBIT_API_SECRET = "rqayiOaNSdL25CmwwfIuOtExt077uXkqruLT"
BYBIT_API_URL = "https://api.bybit.com"

def sign(params: dict, secret: str):
    query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def test_api_key():
    timestamp = str(int(time.time() * 1000))
    params = {
        "timestamp": timestamp,
        "recvWindow": "5000",
        "accountType": "UNIFIED"
    }

    signature = sign(params, BYBIT_API_SECRET)
    params["sign"] = signature

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        url = f"{BYBIT_API_URL}/v5/account/wallet-balance"
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔐 API Key: {BYBIT_API_KEY[:4]}****")
            print(f"🔑 Signature: {signature}")
            print(f"🔄 Status: {resp.status}")
            print("📦 Response:", await resp.text())

asyncio.run(test_api_key())
