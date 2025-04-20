import aiohttp
import asyncio
import os
from dotenv import load_dotenv
import sys

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_URL = "https://api.bybit.com"

async def test_fetch_candles(symbol="BTCUSDT", timeframe="5m", limit=100):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit={limit}"
    headers = {
        "X-BYBIT-API-KEY": "tL7vmTEDT5B8mp4Yer"
    }

    print(f"📦 Testing candle fetch with API key for {symbol} [{timeframe}]...")
    print(f"🔗 URL: {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                raw = await resp.text()
                try:
                    data = await resp.json()
                    print("\n✅ Parsed JSON:")
                    print(data)

                    candle_list = data.get("result", {}).get("list", [])
                    print(f"\n📊 Number of candles received: {len(candle_list)}")
                    if candle_list:
                        print(f"📈 First candle (latest): {candle_list[-1]}")
                    else:
                        print("⚠️ Candle list is EMPTY!")

                except Exception as e:
                    print("❌ Failed to parse JSON response.")
                    print(f"Raw:\n{raw}")
                    print(f"Error: {e}")

    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch_candles())
