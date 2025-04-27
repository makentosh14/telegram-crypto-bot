import aiohttp
import asyncio
import time
import hmac
import hashlib
import os

# Load API keys
BYBIT_API_KEY = "9LSEH2ZksKPSk1fJud"
BYBIT_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"
BYBIT_API_URL = "https://api.bybit.com"

def sign_message(secret, timestamp, method, endpoint, params=""):
    to_sign = f"{timestamp}{method}{endpoint}{params}"
    return hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    timestamp = str(int(time.time() * 1000))
    if method == "GET":
        query = "?" + "&".join([f"{k}={v}" for k, v in sorted(params.items())]) if params else ""
    else:
        query = ""

    signature = sign_message(
        BYBIT_API_SECRET,
        timestamp,
        method.upper(),
        endpoint,
        query[1:] if method == "GET" else ""  # without leading ?
    )

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": "5000",
        "Content-Type": "application/json"
    }

    url = BYBIT_API_URL + endpoint + (query if method == "GET" else "")
    
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                return resp.status, await resp.text()
        elif method == "POST":
            async with session.post(url, headers=headers, json=params) as resp:
                return resp.status, await resp.text()
        else:
            raise ValueError("Unsupported HTTP method.")

async def main():
    # Test GET Wallet Balance
    status, response = await signed_request("GET", "/v5/account/wallet-balance", {
        "accountType": "UNIFIED"
    })
    print(f"🔗 [GET] Wallet Balance\n✅ Status: {status}\n📨 Response: {response}\n")

    # Test POST Cancel All Orders
    status, response = await signed_request("POST", "/v5/order/cancel-all", {
        "category": "linear"
    })
    print(f"🔗 [POST] Cancel All Orders\n✅ Status: {status}\n📨 Response: {response}\n")

    # Test GET Positions
    status, response = await signed_request("GET", "/v5/position/list", {
        "category": "linear"
    })
    print(f"🔗 [GET] Position List\n✅ Status: {status}\n📨 Response: {response}\n")

if __name__ == "__main__":
    asyncio.run(main())
