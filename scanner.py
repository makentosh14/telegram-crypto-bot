import aiohttp
import asyncio
from config import BYBIT_API_URL
from logger import log

symbol_category_map = {}  # Only linear used now

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

async def fetch_candles(symbol, timeframe='5m', limit=100):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit={limit}"
    log(f"📦 Fetching candles for {symbol} [{timeframe}] (linear)")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                raw = await resp.text()
                try:
                    data = await resp.json()
                except Exception:
                    log(f"❌ Failed to parse candle JSON for {symbol}. Raw:\n{raw}")
                    return []

                candle_list = data.get("result", {}).get("list", [])
                if not candle_list:
                    log(f"⚠️ {symbol} [{timeframe}] - Empty candle list. Full response:\n{data}")
                    return []

                if len(candle_list) < 30:
                    log(f"⚠️ {symbol} [{timeframe}] - Not enough candles ({len(candle_list)})")
                    return []

                candles = []
                for item in candle_list:
                    if len(item) < 6:
                        continue
                    candles.append({
                        'timestamp': int(item[0]),
                        'open': item[1],
                        'high': item[2],
                        'low': item[3],
                        'close': item[4],
                        'volume': item[5]
                    })

                log(f"✅ {symbol} [{timeframe}] - {len(candles)} candles fetched")
                return candles

    except Exception as e:
        log(f"❌ Error fetching candles for {symbol}: {e}")
        return []

async def fetch_candles_with_fallback(symbol, timeframes=['5m', '15m', '1h']):
    for tf in timeframes:
        candles = await fetch_candles(symbol, tf)
        if candles:
            return candles
    log(f"⛔ {symbol} - All fallback timeframes failed")
    return []
