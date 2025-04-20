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
    fallback_categories = ['linear', 'inverse', 'spot']

    for category in fallback_categories:
        try:
            url = f"{BYBIT_API_URL}/v5/market/kline?category={category}&symbol={symbol}&interval={timeframe}&limit={limit}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    candle_list = data.get("result", {}).get("list", [])

                    if not candle_list or len(candle_list) < 50:
                        log(f"⚠️ {symbol} [{timeframe}] - {category} - Not enough candles ({len(candle_list)})")
                        continue

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

                    symbol_category_map[symbol] = category  # Save working category
                    log(f"✅ {symbol} [{timeframe}] - {category} - {len(candles)} candles fetched")
                    return candles

        except Exception as e:
            log(f"❌ Exception fetching {symbol} in {category} [{timeframe}]: {e}")
            continue

    log(f"⛔ {symbol} [{timeframe}] - All category attempts failed.")
    return []
