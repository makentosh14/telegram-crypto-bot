import aiohttp
import asyncio
import time
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.json()

def fetch_symbols():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_fetch_symbols())
    except Exception as e:
        log(f"❌ Error fetching symbols: {str(e)}")
        return []

async def _fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        if not data or "result" not in data or "list" not in data["result"]:
            return []
        symbols = [
            item["symbol"] for item in data["result"]["list"]
            if item["status"] == "Trading" and item["symbol"].endswith("USDT")
        ]
        return symbols

def fetch_candles(symbol, timeframe):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_fetch_candles(symbol, timeframe))
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol} {timeframe}: {str(e)}")
        return []

async def _fetch_candles(symbol, timeframe):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit=200"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        if "result" not in data or "list" not in data["result"]:
            return []
        raw = data["result"]["list"]
        candles = [
            {
                "timestamp": int(r[0]),
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
            }
            for r in raw
        ]
        return candles
