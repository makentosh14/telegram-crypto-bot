import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log

async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            symbols = [item["symbol"] for item in data["result"]["list"] if "USDT" in item["symbol"]]
            log(f"✅ Fetched {len(symbols)} symbols.")
            return symbols

async def fetch_candles(symbol, interval="5m", limit=200):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if "result" in data and "list" in data["result"]:
                candles = data["result"]["list"]
                parsed = [
                    {
                        "timestamp": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5])
                    }
                    for c in candles
                ]
                return parsed
            return []

def fetch_symbols_sync():
    return asyncio.run(fetch_symbols())

def fetch_candles_sync(symbol, interval):
    return asyncio.run(fetch_candles(symbol, interval))
