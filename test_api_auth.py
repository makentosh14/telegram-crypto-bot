import os
import aiohttp
import hmac
import hashlib
import asyncio
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return str(data["result"]["timeSecond"])

def sign(params: dict, secret: str):
    sorted_params = dict(sorted(params.items()))
    query = "&".join([f"{k}={v}" for k, v in sorted_params.items()])
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

async def test():
    timestamp = await get_server_time()
    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": "5000"
    }

    signature = sign(params, BYBIT_API_SECRET)
    params["sign"] = signature

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "Content-Type": "application/json"
    }

    url = f"{BYBIT_API_URL}/v5/account/wallet-balance"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

asyncio.run(test())
