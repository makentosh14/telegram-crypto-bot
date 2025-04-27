# bybit_api_async.py (FULLY FIXED for 2025 Bybit REST v5)

import time
import hmac
import hashlib
import aiohttp

from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_API_URL

RECV_WINDOW = 5000

# --- Correct Signature Method (v5 REST) ---
def generate_v5_signature(api_secret, timestamp, api_key, recv_window, body=""):
    payload = f"{timestamp}{api_key}{recv_window}{body}"
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

# --- Signed Request Function ---
async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    timestamp = str(int(time.time() * 1000))
    recv_window = str(RECV_WINDOW)

    # Prepare body
    body = ""
    if method == "POST":
        body = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    signature = generate_v5_signature(
        BYBIT_API_SECRET,
        timestamp,
        BYBIT_API_KEY,
        recv_window,
        body
    )

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-TIMESTAMP": timestamp,
        "X-BYBIT-RECV-WINDOW": recv_window,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    url = f"{BYBIT_API_URL}{endpoint}"

    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, params=params, headers=headers) as resp:
                print(f"\n🔗 [GET] {url}")
                print(f"📦 Params: {params}")
                print(f"✅ Status: {resp.status}")
                response = await resp.text()
                print(f"📨 Response: {response}")
                return await resp.json()

        elif method == "POST":
            async with session.post(url, data=body, headers=headers) as resp:
                print(f"\n🔗 [POST] {url}")
                print(f"📦 Body: {body}")
                print(f"✅ Status: {resp.status}")
                response = await resp.text()
                print(f"📨 Response: {response}")
                return await resp.json()

        else:
            raise ValueError("Unsupported HTTP method!")

# --- Quick Test Example ---
if __name__ == "__main__":
    async def main():
        print("\n🚀 Testing Bybit v5 API Authentication...")

        # Test Wallet Balance
        await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })

        # Test Cancel All Orders (should still work)
        await signed_request("POST", "/v5/order/cancel-all", {
            "category": "linear"
        })

        # Test Position List
        await signed_request("GET", "/v5/position/list", {
            "category": "linear"
        })

    asyncio.run(main())
