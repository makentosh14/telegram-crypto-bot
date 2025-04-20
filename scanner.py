import asyncio
import json
import websockets
import sys
from logger import log

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

URL = "wss://stream.bybit.com/v5/public/linear"
symbol_category_map = {}  # Only linear used now
live_candles = {}  # Stores live candles per symbol

# This replaces the REST-based fetch_candles
async def stream_candles(symbols, interval='1'):
    async with websockets.connect(URL) as ws:
        args = [f"kline.{interval}.{symbol}" for symbol in symbols]
        subscribe_msg = {"op": "subscribe", "args": args}
        await ws.send(json.dumps(subscribe_msg))
        log(f"✅ Subscribed to {len(symbols)} symbols on {interval}m candles")

        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)

                if "data" in data:
                    candles = data["data"]
                    if isinstance(candles, list):
                        for candle in candles:
                            update_candle(candle)
                    elif isinstance(candles, dict):
                        update_candle(candles)

            except Exception as e:
                log(f"❌ WebSocket error: {e}")
                break

def update_candle(candle):
    symbol = candle.get("symbol")
    if not symbol:
        return
    live_candles[symbol] = {
        'timestamp': int(candle['start']),
        'open': candle['open'],
        'high': candle['high'],
        'low': candle['low'],
        'close': candle['close'],
        'volume': candle['volume']
    }
    log(f"📊 Updated candle for {symbol}: {live_candles[symbol]}")

# Reuse your existing fetch_symbols function to get tradable pairs
import aiohttp
from config import BYBIT_API_URL

async def fetch_symbols():
    symbols = set()
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    cursor = None

    try:
        async with aiohttp.ClientSession() as session:
            while True:
                full_url = url + (f"&cursor={cursor}" if cursor else "")
                log(f"🌐 Fetching symbols from linear | URL: {full_url}")
                async with session.get(full_url) as resp:
                    raw = await resp.text()
                    try:
                        data = await resp.json()
                    except Exception:
                        log(f"❌ Failed to parse JSON. Raw:\n{raw}")
                        break

                    if data.get("retCode") != 0:
                        log(f"❌ Error fetching symbols: {data}")
                        break

                    instruments = data.get("result", {}).get("list", [])
                    for instrument in instruments:
                        symbol = instrument.get("symbol", "")
                        status = instrument.get("status", "")
                        if symbol.endswith("USDT") and status == "Trading":
                            symbols.add(symbol)
                            symbol_category_map[symbol] = "linear"

                    next_cursor = data.get("result", {}).get("nextPageCursor")
                    if not next_cursor or next_cursor == cursor:
                        break
                    cursor = next_cursor

        log(f"✅ Total linear symbols fetched: {len(symbols)}")
        return list(symbols)

    except Exception as e:
        log(f"❌ Exception while fetching linear symbols: {e}")
        return []

# Entry point to start everything
if __name__ == "__main__":
    async def main():
        symbols = await fetch_symbols()
        top_symbols = symbols[:5]  # Limit for testing, adjust as needed
        await stream_candles(top_symbols, interval='1')

    asyncio.run(main())

