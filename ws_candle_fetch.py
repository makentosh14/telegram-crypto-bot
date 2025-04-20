import asyncio
import json
import websockets
import sys

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

URL = "wss://stream.bybit.com/v5/public/linear"
SYMBOL = "BTCUSDT"
INTERVAL = "1"  # 1-minute candles

async def fetch_candles():
    async with websockets.connect(URL) as ws:
        # Subscribe to kline stream
        subscribe_msg = {
            "op": "subscribe",
            "args": [f"kline.{INTERVAL}.{SYMBOL}"]
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"✅ Subscribed to kline.{INTERVAL}.{SYMBOL}")

        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)
                if "data" in data:
                    candle = data["data"]
                    print(f"\n📊 Candle Update [{SYMBOL}]:")
                    print(f" - Time: {candle['start']}")
                    print(f" - Open: {candle['open']}")
                    print(f" - High: {candle['high']}")
                    print(f" - Low: {candle['low']}")
                    print(f" - Close: {candle['close']}")
                    print(f" - Volume: {candle['volume']}")
            except Exception as e:
                print(f"❌ Error receiving candle data: {e}")
                break

if __name__ == "__main__":
    asyncio.run(fetch_candles())
