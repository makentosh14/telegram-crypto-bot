import os
from dotenv import load_dotenv
import aiohttp
import asyncio
import hmac
import hashlib

# Load .env
load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return str(data["time"])

def generate_signature(params: dict, secret: str) -> str:
    sorted_params = dict(sorted(params.items()))
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params.items())
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def test_signed_request():
    print(f"🔐 API KEY: {BYBIT_API_KEY}")
    print(f"🔐 SECRET (masked): {BYBIT_API_SECRET[:4]}****")

    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        print("❌ API keys not loaded from .env")
        return

    timestamp = await get_server_time()

    # ✅ Params for GET must exclude the sign in hash
    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": "5000"
    }

    signature = generate_signature(params, BYBIT_API_SECRET)

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": "5000",
        "X-BYBIT-API-SIGN": signature,
        "Content-Type": "application/json"
    }

    url = f"{BYBIT_API_URL}/v5/account/wallet-balance"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params={"accountType": "UNIFIED"}) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

# Run it
asyncio.run(test_signed_request())
