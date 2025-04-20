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
                    candles = data["data"]

                    # If it's a list of candles (initial push), loop over them
                    if isinstance(candles, list):
                        for candle in candles:
                            print_candle(candle)
                    # If it's a single candle update (tick)
                    elif isinstance(candles, dict):
                        print_candle(candles)

            except Exception as e:
                print(f"❌ Error receiving candle data: {e}")
                break

def print_candle(candle):
    print(f"\n📊 Candle Update [{SYMBOL}]")
    print(f" - Time: {candle['start']}")
    print(f" - Open: {candle['open']}")
    print(f" - High: {candle['high']}")
    print(f" - Low: {candle['low']}")
    print(f" - Close: {candle['close']}")
    print(f" - Volume: {candle['volume']}")

if __name__ == "__main__":
    asyncio.run(fetch_candles())
