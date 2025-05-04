# active_trade_ws.py

import asyncio
import json
import websockets
from collections import defaultdict
from logger import log

active_symbols = set()
live_prices = defaultdict(lambda: None)

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"

async def price_stream():
    while True:
        try:
            if not active_symbols:
                await asyncio.sleep(1)
                continue

            async with websockets.connect(BYBIT_WS_URL, ping_interval=20, ping_timeout=10) as ws:
                args = [f"tickers.{symbol}" for symbol in active_symbols]
                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log(f"📡 Subscribed to {len(args)} active symbol tickers: {', '.join(active_symbols)}")

                while True:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=20)
                        data = json.loads(message)

                        if data.get("topic", "").startswith("tickers.") and "data" in data:
                            symbol = data["topic"].split(".")[-1]
                            price = float(data["data"].get("lastPrice", 0))
                            live_prices[symbol] = price
                    
                    except asyncio.TimeoutError:
                        log("⚠️ Active price stream timeout — reconnecting...")
                        break

        except Exception as e:
            log(f"❌ Active price stream error: {e}", level="ERROR")
            await asyncio.sleep(5)

        await asyncio.sleep(2)

def add_active_symbol(symbol):
    active_symbols.add(symbol)

def remove_active_symbol(symbol):
    active_symbols.discard(symbol)

def get_live_price(symbol):
    return live_prices.get(symbol)

def start_active_price_stream():
    asyncio.create_task(price_stream())
