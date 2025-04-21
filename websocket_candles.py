import asyncio
import json
import websockets
from collections import deque
from scanner import symbol_category_map
from logger import log

# Store a deque of up to 100 candles per symbol
live_candles = {}
MAX_CANDLES = 100

async def stream_candles(symbols, interval='1'):
    futures_url = "wss://stream.bybit.com/v5/public/linear"
    spot_url = "wss://stream.bybit.com/v5/public/spot"

    async def handle_stream(url, symbols, category):
        try:
            async with websockets.connect(url) as ws:
                args = [f"kline.{interval}.{symbol}" for symbol in symbols if symbol_category_map.get(symbol) == category]
                if not args:
                    return
                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log(f"📡 Subscribed to {len(args)} {category.upper()} pairs via WebSocket")

                while True:
                    try:
                        message = await ws.recv()
                        log(f"🟢 WS [{category.upper()}] message received")

                        data = json.loads(message)

                        # Check for new kline data in array format
                        if "data" in data and isinstance(data["data"], dict) and "data" in data["data"]:
                            data_block = data["data"]["data"]
                            symbol = data["data"].get("topic", "").split(".")[-1]

                            for k in data_block:
                                new_candle = {
                                    "timestamp": int(k["start"]),
                                    "open": k["open"],
                                    "high": k["high"],
                                    "low": k["low"],
                                    "close": k["close"],
                                    "volume": k["volume"]
                                }

                                if symbol not in live_candles:
                                    live_candles[symbol] = deque(maxlen=MAX_CANDLES)

                                live_candles[symbol].append(new_candle)

                            log(f"📈 {symbol} [{category}] updated | total: {len(live_candles[symbol])} candles")

                    except Exception as e:
                        log(f"❌ WebSocket error in {category}: {e}", level="ERROR")
                        await asyncio.sleep(2)
                        return  # reconnect loop will relaunch

        except Exception as e:
            log(f"❌ Connection failed for {category} stream: {e}", level="ERROR")

    tasks = [
        asyncio.create_task(handle_stream(futures_url, symbols, "linear")),
        asyncio.create_task(handle_stream(spot_url, symbols, "spot"))
    ]
    await asyncio.gather(*tasks)
