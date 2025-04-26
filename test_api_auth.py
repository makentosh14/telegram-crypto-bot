import time
import hmac
import hashlib
import aiohttp

# Replace with your real API key and secret
API_KEY = "VFEBK9XrpC6polx31h"
API_SECRET = "WBFlSemMj1EMihM2CHkiVbyYT3vyRoUNFjYS"

async def signed_request(method, endpoint, params=None):
    if params is None:
        params = {}

    params["api_key"] = API_KEY
    params["timestamp"] = str(int(time.time() * 1000))
    params["recvWindow"] = "5000"

    # Create query string
    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["sign"] = signature

    url = "https://api.bybit.com" + endpoint

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    print(f"🔗 Sending request to: {url}")
    print(f"📦 Params: {params}")

    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, params=params, headers=headers) as response:
                status = response.status
                data = await response.text()
                print(f"✅ HTTP Status: {status}")
                print(f"📦 Response: {data}")
                return await response.json()
        elif method == "POST":
            async with session.post(url, data=params, headers=headers) as response:
                status = response.status
                data = await response.text()
                print(f"✅ HTTP Status: {status}")
                print(f"📦 Response: {data}")
                return await response.json()
        else:
            raise ValueError("Unsupported HTTP method")
