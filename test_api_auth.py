import aiohttp
import asyncio
import time
import hmac
import hashlib
import os
import socket

# Your Bybit API keys
BYBIT_API_KEY = "ZWnRCXNtjKrbPZxUjA"
BYBIT_API_SECRET = "rqayiOaNSdL25CmwwfIuOtExt077uXkqruLT"
BYBIT_API_URL = "https://api.bybit.com"

async def send_signed_request(endpoint="/v5/account/wallet-balance", method="GET", extra_params=None):
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": recv_window
    }

    if extra_params:
        params.update(extra_params)

    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(BYBIT_API_SECRET.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
    params["sign"] = signature

    url = BYBIT_API_URL + endpoint

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(family=socket.AF_INET)) as session:
        if method == "GET":
            async with session.get(url, params=params) as response:
                status = response.status
                text = await response.text()
                return status, text
        elif method == "POST":
            async with session.post(url, data=params) as response:
                status = response.status
                text = await response.text()
                return status, text

async def run_tests():
    print("\n🚀 Testing Bybit API connection...\n")

    tests = [
        {"name": "Wallet Balance", "endpoint": "/v5/account/wallet-balance", "method": "GET"},
        {"name": "Order Cancel All", "endpoint": "/v5/order/cancel-all", "method": "POST", "extra_params": {"category": "linear", "symbol": "BTCUSDT"}},
        {"name": "Position List", "endpoint": "/v5/position/list", "method": "GET", "extra_params": {"category": "linear"}},
    ]

    for test in tests:
        print(f"🔍 Testing {test['name']} ...")
        status, response = await send_signed_request(
            endpoint=test["endpoint"],
            method=test["method"],
            extra_params=test.get("extra_params")
        )
        print(f"✅ Status: {status}")
        print(f"📨 Response:\n{response}\n")

        if status == 401:
            print("❌ 401 Unauthorized detected! Possible wrong API or settings.\n")
        elif status == 404:
            print("❌ 404 Not Found — Wrong endpoint OR wrong base URL?\n")
        elif status == 200:
            print("✅ OK! This endpoint is working.\n")
        else:
            print(f"⚠️ Unexpected Status {status}.\n")

async def main():
    await run_tests()

if __name__ == "__main__":
    asyncio.run(main())
