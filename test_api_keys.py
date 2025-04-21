# test_api_keys.py
import os
import time
import hmac
import hashlib
import aiohttp
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

async def main():
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": recv_window
    }

    # Signature
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(
        BYBIT_API_SECRET.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    url = f"{BYBIT_API_URL}/v5/account/wallet-balance"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

import asyncio
asyncio.run(main())
