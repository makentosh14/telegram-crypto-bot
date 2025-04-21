# scanner.py

import aiohttp
from config import BYBIT_API_URL
from logger import log

symbol_category_map = {}

async def fetch_symbols():
    symbols = set()
    futures_url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    spot_url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=spot"

    try:
        async with aiohttp.ClientSession() as session:
            for url, category in [(futures_url, "linear"), (spot_url, "spot")]:
                cursor = None
                while True:
                    full_url = url + (f"&cursor={cursor}" if cursor else "")
                    log(f"🌐 Fetching {category} symbols | URL: {full_url}")
                    async with session.get(full_url) as resp:
                        raw = await resp.text()
                        try:
                            data = await resp.json()
                        except Exception:
                            log(f"❌ Failed to parse {category} JSON. Raw:\n{raw}")
                            break

                        if data.get("retCode") != 0:
                            log(f"❌ Error fetching {category} symbols: {data}")
                            break

                        instruments = data.get("result", {}).get("list", [])
                        for instrument in instruments:
                            symbol = instrument.get("symbol", "")
                            status = instrument.get("status", "")
                            if symbol.endswith("USDT") and status == "Trading":
                                symbols.add(symbol)
                                symbol_category_map[symbol] = category

                        next_cursor = data.get("result", {}).get("nextPageCursor")
                        if not next_cursor or next_cursor == cursor:
                            break
                        cursor = next_cursor

        log(f"✅ Total symbols fetched: {len(symbols)}")
        return list(symbols)

    except Exception as e:
        log(f"❌ Exception while fetching symbols: {e}")
        return []
