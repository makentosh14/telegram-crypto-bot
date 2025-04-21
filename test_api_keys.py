import aiohttp
import asyncio
import hmac
import hashlib

# === Your actual API credentials (testing only) ===
BYBIT_API_KEY = "A6ucmdIu9DZCi3ZaDz"
BYBIT_API_SECRET = "M3Zz9RedjrwrC8CF0K8KlHQeHkf3eCpEQMCi"
BYBIT_API_URL = "https://api.bybit.com"

async def get_server_time():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BYBIT_API_URL}/v5/market/time") as resp:
            data = await resp.json()
            return str(data["result"]["time"])

def sign(params, secret):
    sorted_params = dict(sorted(params.items()))
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params.items())
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def test_signed_request():
    print(f"🔐 API KEY: {BYBIT_API_KEY}")
    print(f"🔐 SECRET (masked): {BYBIT_API_SECRET[:4]}****")

    timestamp = await get_server_time()
    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": "5000"
    }

    signature = sign(params, BYBIT_API_SECRET)
    params["sign"] = signature

    headers = {
        "Content-Type": "application/json",
        "X-BYBIT-API-KEY": BYBIT_API_KEY
    }

    url = f"{BYBIT_API_URL}/v5/account/wallet-balance"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print(f"🔄 Status: {resp.status}")
            print(await resp.text())

# Run the test
asyncio.run(test_signed_request())
