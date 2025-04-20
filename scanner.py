import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

CATEGORIES = ['linear', 'inverse', 'spot']
symbol_category_map = {}  # Cache to speed up repeated lookups

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

                        instruments = data["result"].get("list", [])
                        for instrument in instruments:
                            symbol = instrument.get("symbol", "")
                            status = instrument.get("status", "")
                            quote = instrument.get("quoteCoin", "")

                            if symbol.endswith("USDT") and status == "Trading":
                                symbols.add(symbol)
                                symbol_category_map[symbol] = category  # store which category it belongs to

                        next_cursor = data["result"].get("nextPageCursor")
                        if not next_cursor or next_cursor == cursor:
                            break
                        cursor = next_cursor

        return list(symbols)

    except Exception as e:
        log(f"❌ Exception while fetching symbols: {e}")
        return []

async def fetch_candles(symbol, timeframe='5m', limit=100):
    try:
        # Determine the correct category for the symbol
        category = symbol_category_map.get(symbol, "linear")  # fallback default
        url = f"{BYBIT_API_URL}/v5/market/kline?category={category}&symbol={symbol}&interval={timeframe}&limit={limit}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if 'result' in data and 'list' in data['result']:
                    candles = []
                    for item in data['result']['list']:
                        candles.append({
                            'timestamp': int(item[0]),
                            'open': item[1],
                            'high': item[2],
                            'low': item[3],
                            'close': item[4],
                            'volume': item[5]
                        })
                    return candles
                else:
                    log(f"⚠️ Invalid candle response for {symbol}")
                    return []
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol}: {e}")
        return []
