# bybit_ws_auth.py

import asyncio
import time
import hmac
import hashlib
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

async def bybit_auth_ws():
    url = "wss://stream.bybit.com/v5/private"

    async with websockets.connect(url) as ws:
        # === Step 1: Auth ===
        expires = int(time.time() * 1000) + 10000
        payload = f"{API_KEY}{expires}"
        signature = hmac.new(
            API_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        auth_msg = {
            "op": "auth",
            "args": [API_KEY, expires, signature]
        }

        await ws.send(json.dumps(auth_msg))
        print("🔐 Sent authentication message")

        while True:
            response = await ws.recv()
            data = json.loads(response)

            if data.get("op") == "auth" and data.get("success"):
                print("✅ Authenticated successfully!")

                # === Step 2: Subscribe to wallet or order updates ===
                await ws.send(json.dumps({
                    "op": "subscribe",
                    "args": ["wallet", "order"]
                }))
                print("📡 Subscribed to wallet & order updates")

            elif "topic" in data:
                print("📨 Data:", data)

            else:
                print("ℹ️ Message:", data)

# Run it
if __name__ == "__main__":
    asyncio.run(bybit_auth_ws())
