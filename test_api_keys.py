import os, aiohttp, asyncio, time, hmac, hashlib
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")
url = "https://api.bybit.com/v5/account/wallet-balance"

timestamp = str(int(time.time() * 1000))
params = {
    "accountType": "UNIFIED",
    "timestamp": timestamp,
    "recvWindow": "5000"
}

def sign(params, secret):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

params["sign"] = sign(params, api_secret)

headers = {
    "Content-Type": "application/json",
    "X-BYBIT-API-KEY": api_key
}

async def test():
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

asyncio.run(test())
