import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch(session, url):
    try:
        async with session.get(url) as response:
            return await response.json()
    except Exception as e:
        log(f"Fetch error: {e}")
        return None

async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        if data and data.get("result") and data["result"].get("list"):
            return [item["symbol"] for item in data["result"]["list"] if "USDT" in item["symbol"]]
    return []

async def fetch_candle_data(session, symbol, interval):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=100"
    data = await fetch(session, url)
    if data and data.get("result") and data["result"].get("list"):
        return [
            {
                "timestamp": int(candle[0]),
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5]
            }
            for candle in data["result"]["list"]
        ]
    return []

async def fetch_candles(symbol, timeframes=TIMEFRAMES):
    candles_by_tf = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candle_data(session, symbol, tf) for tf in timeframes]
        results = await asyncio.gather(*tasks)
        for i, tf in enumerate(timeframes):
            candles_by_tf[tf] = results[i]
    return candles_by_tf

def fetch_symbols_sync():
    return asyncio.run(fetch_symbols())

def fetch_candles_sync(symbol, timeframes=TIMEFRAMES):
    return asyncio.run(fetch_candles(symbol, timeframes))
