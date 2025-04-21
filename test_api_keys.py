import os
from dotenv import load_dotenv
import aiohttp
import asyncio
import hmac
import hashlib

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return int(data["time"])

def sign(params, secret):
    sorted_params = dict(sorted(params.items()))
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params.items())
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def test_signed_request():
    print(f"🔐 API KEY: {BYBIT_API_KEY}")
    print(f"🔐 SECRET (masked): {BYBIT_API_SECRET[:4]}****")

    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        print("❌ API keys not loaded from .env")
        return

    timestamp = str(await get_server_time())
    params = {
        "timestamp": timestamp,
        "recvWindow": "5000",
        "accountType": "UNIFIED"
    }

    signature = sign(params, BYBIT_API_SECRET)
    params["sign"] = signature

    headers = {
        "Content-Type": "application/json",
        "X-BYBIT-API-KEY": BYBIT_API_KEY
    }

    async with aiohttp.ClientSession() as session:
        url = f"{BYBIT_API_URL}/v5/account/wallet-balance"
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

asyncio.run(test_signed_request())
