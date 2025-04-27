import aiohttp
import asyncio
import time
import hmac
import hashlib
import socket

# === YOUR BYBIT API KEYS ===
BYBIT_API_KEY = "ZWnRCXNtjKrbPZxUjA"
BYBIT_API_SECRET = "rqayiOaNSdL25CmwwfIuOtExt077uXkqruLT"
BYBIT_API_URL = "https://api.bybit.com"

def generate_signature(params, secret):
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()

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
    signature = generate_signature(params, BYBIT_API_SECRET)
    params["sign"] = signature

    url = BYBIT_API_URL + endpoint

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(family=socket.AF_INET)) as session:
        if method == "GET":
            async with session.get(url, params=params, headers=headers) as response:
                status = response.status
                text = await response.text()
                return status, text
        elif method == "POST":
            async with session.post(url, data=params, headers=headers) as response:
                status = response.status
                text = await response.text()
                return status, text

async def main():
    print("🚀 Testing Bybit API connection...\n")

    tests = [
        ("/v5/account/wallet-balance", "GET", None),
        ("/v5/order/cancel-all", "POST", {"category": "linear", "symbol": "BTCUSDT"}),
        ("/v5/position/list", "GET", {"category": "linear", "symbol": "BTCUSDT"})
    ]

    for endpoint, method, extra_params in tests:
        print(f"🔍 Testing {endpoint} ...")
        try:
            status, response = await send_signed_request(endpoint, method, extra_params)
            print(f"✅ Status: {status}")
            print(f"📨 Response: {response}\n")

            if status == 401:
                print("❌ 401 Unauthorized! Likely API signature/header issue.\n")
            elif status == 200:
                print("✅ 200 OK! This endpoint is properly authenticated.\n")
            else:
                print("⚠️ Unexpected status, check response.\n")

        except Exception as e:
            print(f"❌ Error testing {endpoint}: {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
