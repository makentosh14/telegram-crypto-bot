import asyncio
import json
import websockets
from collections import defaultdict, deque
from scanner import symbol_category_map
from logger import log

live_candles = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))
SUPPORTED_INTERVALS = ['1', '5', '15']

async def stream_candles(symbols):
    futures_url = "wss://stream.bybit.com/v5/public/linear"
    spot_url = "wss://stream.bybit.com/v5/public/spot"

    async def handle_stream(url, symbols, category, interval):
        try:
            async with websockets.connect(url) as ws:
                args = [f"kline.{interval}.{symbol}" for symbol in symbols if symbol_category_map.get(symbol) == category]
                if not args:
                    return

                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log(f"📡 Subscribed to {len(args)} {category.upper()} @ {interval}m")

                while True:
                    try:
                        message = await ws.recv()
                        data = json.loads(message)

                        topic = data.get("topic", "")
                        symbol = topic.split(".")[-1] if topic else None
                        interval_from_topic = topic.split(".")[1] if topic else None

                        if not symbol or "data" not in data or not interval_from_topic:
                            continue

                        candles = data["data"]

                        # If data is a list (snapshot)
                        if isinstance(candles, list):
                            for k in candles:
                                candle = {
                                    "timestamp": int(k["start"]),
                                    "open": k["open"],
                                    "high": k["high"],
                                    "low": k["low"],
                                    "close": k["close"],
                                    "volume": k["volume"]
                                }
                                live_candles[symbol][interval_from_topic].append(candle)

                        # If data is a dict (update)
                        elif isinstance(candles, dict):
                            k = candles
                            candle = {
                                "timestamp": int(k["start"]),
                                "open": k["open"],
                                "high": k["high"],
                                "low": k["low"],
                                "close": k["close"],
                                "volume": k["volume"]
                            }
                            live_candles[symbol][interval_from_topic].append(candle)

                        log(f"📈 {symbol} [{category}] @{interval_from_topic} updated | total: {len(live_candles[symbol][interval_from_topic])}")

                    except Exception as e:
                        log(f"❌ WebSocket error in {category} {interval}m: {e}", level="ERROR")
                        await asyncio.sleep(2)
                        return

        except Exception as e:
            log(f"❌ Connection failed for {category} {interval}m: {e}", level="ERROR")

    tasks = []
    for interval in SUPPORTED_INTERVALS:
        tasks.append(asyncio.create_task(handle_stream(futures_url, symbols, "linear", interval)))
        tasks.append(asyncio.create_task(handle_stream(spot_url, symbols, "spot", interval)))

    await asyncio.gather(*tasks)
