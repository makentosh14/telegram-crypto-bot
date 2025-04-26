import aiohttp
import asyncio
import time
import hmac
import hashlib

# Your Bybit API keys
API_KEY = "VFEBK9XrpC6polx31h"
API_SECRET = "WBFlSemMj1EMihM2CHkiVbyYT3vyRoUNFjYS"

async def test_api_auth():
    url = "https://api.bybit.com/v5/account/wallet-balance"

    params = {
        "accountType": "UNIFIED",
        "timestamp": str(int(time.time() * 1000)),
        "recvWindow": "5000"
    }

    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["sign"] = signature

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    print(f"🔗 URL: {url}")
    print(f"📦 Params: {params}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"✅ Status: {resp.status}")
            response = await resp.text()
            print(f"📨 Response: {response}")

if __name__ == "__main__":
    asyncio.run(test_api_auth())
