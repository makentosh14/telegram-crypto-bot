import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

CATEGORIES = ['linear', 'inverse', 'spot']
symbol_category_map = {}  # Global cache to track each symbol's category

async def fetch_symbols():
    symbols = set()

    try:
        async with aiohttp.ClientSession() as session:
            for category in CATEGORIES:
                cursor = None
                while True:
                    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category={category}"
                    if cursor:
                        url += f"&cursor={cursor}"

                    async with session.get(url) as resp:
                        data = await resp.json()
                        if data.get("retCode") != 0:
                            log(f"❌ Error fetching symbols ({category}): {data}")
                            break

                        instruments = data.get("result", {}).get("list", [])
                        for instrument in instruments:
                            symbol = instrument.get("symbol", "")
                            status = instrument.get("status", "")
                            quote = instrument.get("quoteCoin", "")

                            if symbol.endswith("USDT") and status == "Trading":
                                symbols.add(symbol)
                                symbol_category_map[symbol] = category

                        next_cursor = data.get("result", {}).get("nextPageCursor")
                        if not next_cursor or next_cursor == cursor:
                            break
                        cursor = next_cursor

        log(f"✅ Total tradable symbols fetched: {len(symbols)}")
        return list(symbols)

    except Exception as e:
        log(f"❌ Exception while fetching symbols: {e}")
        return []


async def fetch_candles(symbol, timeframe='5m', limit=100):
    try:
        category = symbol_category_map.get(symbol, "linear")
        url = f"{BYBIT_API_URL}/v5/market/kline?category={category}&symbol={symbol}&interval={timeframe}&limit={limit}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                candle_list = data.get("result", {}).get("list", [])

                if not candle_list or len(candle_list) < 50:
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
        log(f"❌ Error fetching candles for {symbol} [{timeframe}]: {e}")
        return []
