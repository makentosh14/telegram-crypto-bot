import aiohttp
import asyncio
import time
import hmac
import hashlib
import json

# API credentials
API_KEY = "9LSEH2ZksKPSk1fJud"
API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"
BASE_URL = "https://api.bybit.com"

def sign_message(secret, timestamp, method, endpoint, body=""):
    payload = f"{timestamp}{method}{endpoint}{body}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    timestamp = str(int(time.time() * 1000))
    if method == "GET":
        body_str = ""
        query = "?" + "&".join([f"{k}={v}" for k, v in sorted(params.items())]) if params else ""
    else:
        body_str = json.dumps(params)
        query = ""

    signature = sign_message(API_SECRET, timestamp, method.upper(), endpoint, body_str if method == "POST" else "")

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "X-BYBIT-API-SIGN": signature,
        "X-BYBIT-API-TIMESTAMP": timestamp,
        "X-BYBIT-API-RECV-WINDOW": "5000",
        "Content-Type": "application/json"
    }

    url = BASE_URL + endpoint + (query if method == "GET" else "")
    
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                return resp.status, await resp.text()
        elif method == "POST":
            async with session.post(url, headers=headers, data=body_str) as resp:
                return resp.status, await resp.text()
        else:
            raise ValueError("Unsupported HTTP method.")

async def main():
    print("🔍 Testing /v5/account/wallet-balance ...")
    status, response = await signed_request("GET", "/v5/account/wallet-balance", {
        "accountType": "UNIFIED"
    })
    print(f"✅ Status: {status}\n📨 Response: {response}\n")

    print("🔍 Testing /v5/order/cancel-all ...")
    status, response = await signed_request("POST", "/v5/order/cancel-all", {
        "category": "linear"
    })
    print(f"✅ Status: {status}\n📨 Response: {response}\n")

    print("🔍 Testing /v5/position/list ...")
    status, response = await signed_request("GET", "/v5/position/list", {
        "category": "linear"
    })
    print(f"✅ Status: {status}\n📨 Response: {response}\n")

if __name__ == "__main__":
    asyncio.run(main())
