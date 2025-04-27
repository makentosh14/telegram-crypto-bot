# api_diagnostic.py

import aiohttp
import asyncio
import time
import hmac
import hashlib
import os

# Replace with your own API Key and Secret
BYBIT_API_KEY = "ZWnRCXNtjKrbPZxUjA"
BYBIT_API_SECRET = "rqayiOaNSdL25CmwwfIuOtExt077uXkqruLT"
BYBIT_API_URL = "https://api.bybit.com"

async def send_signed_request(endpoint="/v5/account/wallet-balance"):
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    params = {
        "accountType": "UNIFIED",
        "timestamp": timestamp,
        "recvWindow": recv_window
    }

    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    signature = hmac.new(BYBIT_API_SECRET.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
    params["sign"] = signature

    url = BYBIT_API_URL + endpoint

    print(f"🔗 URL: {url}")
    print(f"📦 Params: {params}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            status = response.status
            text = await response.text()
            print(f"✅ HTTP Status: {status}")
            print(f"📨 Server Response:\n{text}")

            if status == 401:
                print("\n❌ 401 Unauthorized → Possible reasons:")
                print("- Wrong API Key/Secret")
                print("- Not connected to 'My App'")
                print("- Not Unified Account")
                print("- Regional mismatch (US/Global)")
            elif status == 404:
                print("\n❌ 404 Not Found → Wrong endpoint OR using wrong API URL?")
            elif status == 200:
                print("\n✅ Success! Your account is connected properly.")

async def main():
    await send_signed_request()

if __name__ == "__main__":
    asyncio.run(main())
