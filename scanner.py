# scanner.py

import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.json()

async def fetch_all_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        symbols = [item['symbol'] for item in data['result']['list']
                   if 'USDT' in item['symbol'] and item['contractType'] == 'LinearPerpetual']
        return symbols

def fetch_symbols():
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(fetch_all_symbols())
    except Exception as e:
        log(f"Error fetching symbols: {e}")
        return []

async def fetch_candles_async(session, symbol, interval):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=100"
    async with session.get(url) as response:
        result = await response.json()
        if result["retCode"] != 0:
            return []
        candles = result["result"]["list"]
        return [
            {
                "timestamp": c[0],
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            }
            for c in candles
        ]

async def fetch_candles_for_all(symbol, timeframes):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candles_async(session, symbol, tf) for tf in timeframes]
        results = await asyncio.gather(*tasks)
        return dict(zip(timeframes, results))

def fetch_candles(symbol, tf):
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(fetch_candles_async(aiohttp.ClientSession(), symbol, tf))
    except Exception as e:
        log(f"Error fetching candles for {symbol}-{tf}: {e}")
        return []

def fetch_all_candles(symbols):
    data = {}
    try:
        loop = asyncio.get_event_loop()
        for symbol in symbols:
            candles = loop.run_until_complete(fetch_candles_for_all(symbol, TIMEFRAMES))
            data[symbol] = candles
        return data
    except Exception as e:
        log(f"Error fetching all candles: {e}")
        return {}
