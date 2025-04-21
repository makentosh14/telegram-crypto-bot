import aiohttp
import asyncio
import time
import hmac
import hashlib
import os

# Replace with your working key and secret
BYBIT_API_KEY = "A6ucmdIu9DZCi3ZaDz"
BYBIT_API_SECRET = "M3Zz9RedjrwrC8CF0K8KlHQeHkf3eCpEQMCi"
BYBIT_API_URL = "https://api.bybit.com"

def generate_signature(params, secret):
    sorted_params = dict(sorted(params.items()))
    query = '&'.join([f"{k}={v}" for k, v in sorted_params.items()])
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

async def test_auth():
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    endpoint = "/v5/account/wallet-balance"
    url = f"{BYBIT_API_URL}{endpoint}"

    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": recv_window
    }

    signature = generate_signature(params, BYBIT_API_SECRET)
    params["sign"] = signature

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "Content-Type": "application/json"
    }

    print(f"🔐 API Key: {BYBIT_API_KEY}")
    print(f"🔑 Signature: {signature}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔄 HTTP Status: {resp.status}")
            response = await resp.text()
            print(f"📦 Response: {response}")

asyncio.run(test_auth())
