import asyncio
import json
import websockets
from collections import defaultdict
from logger import log

# Shared dictionary for real-time price updates
live_trade_prices = defaultdict(dict)

# Set of active symbols to watch
active_symbols = set()

# Update interval
RECONNECT_DELAY = 5
WS_URL = "wss://stream.bybit.com/v5/public/linear"

async def track_active_prices():
    while True:
        if not active_symbols:
            await asyncio.sleep(2)
            continue

        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                args = [f"tickers.{symbol}" for symbol in active_symbols]
                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log(f"[ACTIVE STREAM] Subscribed to {len(args)} active tickers")

                while True:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(message)

                        topic = data.get("topic", "")
                        symbol = topic.split(".")[-1] if topic else None

                        if "data" in data and symbol:
                            tick = data["data"]
                            price = float(tick.get("lastPrice", 0))
                            live_trade_prices[symbol] = {
                                "price": price,
                                "timestamp": tick.get("ts")
                            }
                            log(f"[ACTIVE] {symbol} = {price}")

                    except asyncio.TimeoutError:
                        log("[ACTIVE STREAM] Timeout — reconnecting...", level="WARNING")
                        break
                    except Exception as e:
                        log(f"[ACTIVE STREAM] Error: {e}", level="ERROR")
                        break

        except Exception as e:
            log(f"[ACTIVE STREAM] Connection failed: {e}", level="ERROR")

        await asyncio.sleep(RECONNECT_DELAY)

def add_active_symbol(symbol):
    active_symbols.add(symbol)

def remove_active_symbol(symbol):
    active_symbols.discard(symbol)

def get_live_price(symbol):
    return live_trade_prices.get(symbol, {}).get("price")
