import os
import aiohttp
import asyncio
import time
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")
base_url = "https://api.bybit.com"

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/v5/market/time") as resp:
            data = await resp.json()
            return str(data["time"])

def create_signature(params, secret):
    sorted_params = dict(sorted(params.items()))
    query = "&".join(f"{k}={v}" for k, v in sorted_params.items())
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

async def test_auth():
    timestamp = await get_server_time()
    params = {
        "timestamp": timestamp,
        "recvWindow": "5000",
        "accountType": "UNIFIED"
    }

    signature = create_signature(params, api_secret)
    params["sign"] = signature

    headers = {
        "X-BYBIT-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    url = f"{base_url}/v5/account/wallet-balance"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔁 Status: {resp.status}")
            print(await resp.text())

asyncio.run(test_auth())
