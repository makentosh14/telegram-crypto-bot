# websocket_candles.py

import asyncio
import json
import websockets
from scanner import symbol_category_map
from logger import log

live_candles = {}

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
                        data = json.loads(message)

                        # Debug: Log raw data format once
                        if "topic" in data and "data" in data:
                            log(f"🔍 WS [{category.upper()}] topic: {data['topic']}")

                        if "data" in data and isinstance(data["data"], dict):
                            k = data["data"]
                            symbol = k.get("symbol")
                            if not symbol:
                                continue
                            live_candles[symbol] = {
                                "timestamp": int(k["start"]),
                                "open": k["open"],
                                "high": k["high"],
                                "low": k["low"],
                                "close": k["close"],
                                "volume": k["volume"]
                            }

                    except Exception as e:
                        log(f"❌ WebSocket error in {category}: {e}", level="ERROR")
                        await asyncio.sleep(2)
                        return  # reconnect loop will relaunch

        except Exception as e:
            log(f"❌ Connection failed for {category} stream: {e}", level="ERROR")

    tasks = []
    tasks.append(asyncio.create_task(handle_stream(futures_url, symbols, "linear")))
    tasks.append(asyncio.create_task(handle_stream(spot_url, symbols, "spot")))
    await asyncio.gather(*tasks)
