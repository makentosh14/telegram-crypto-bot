import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log

async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                symbols = [
                    item['symbol'] for item in data['result']['list']
                    if "USDT" in item['symbol']
                ]
                log(f"✅ Fetched {len(symbols)} symbols.")
                return symbols
    except Exception as e:
        log(f"❌ Failed to fetch symbols: {e}")
        return []

async def fetch_candles_for_symbol(session, symbol, interval):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=200"
    try:
        async with session.get(url) as resp:
            data = await resp.json()
            if data["retCode"] == 0:
                candles = [
                    {
                        "timestamp": int(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                    }
                    for item in data["result"]["list"]
                ]
                return candles
            else:
                return []
    except Exception as e:
        log(f"❌ Error fetching {symbol} - {interval}: {e}")
        return []

async def fetch_all_candles(symbol):
    candles_by_tf = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candles_for_symbol(session, symbol, tf) for tf in TIMEFRAMES]
        results = await asyncio.gather(*tasks)
        for tf, result in zip(TIMEFRAMES, results):
            candles_by_tf[tf] = result
    return candles_by_tf

def fetch_candles(symbol, tf):
    return asyncio.run(fetch_candles_for_symbol(aiohttp.ClientSession(), symbol, tf))
