# symbol_info.py
import aiohttp
import asyncio

symbol_precisions = {}

async def fetch_symbol_info():
    url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            for item in data.get("result", {}).get("list", []):
                symbol = item["symbol"]
                min_qty = float(item["lotSizeFilter"]["minOrderQty"])
                tick_size = float(item["lotSizeFilter"]["qtyStep"])
                precision = abs(int(round(-1 * (tick_size).as_integer_ratio()[1].bit_length() - 1)))
                symbol_precisions[symbol] = {
                    "min_qty": min_qty,
                    "step": tick_size,
                    "precision": precision
                }

def get_precision(symbol):
    info = symbol_precisions.get(symbol, {})
    return info.get("precision", 0)

def round_qty(symbol, qty):
    precision = get_precision(symbol)
    return round(qty, precision)
