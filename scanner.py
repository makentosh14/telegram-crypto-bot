import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch_candles_async(session, symbol, interval):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=100"
    async with session.get(url) as response:
        data = await response.json()
        if data["retCode"] == 0 and "list" in data["result"]:
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

async def fetch_candles_for_timeframes(symbol):
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_candles_async(session, symbol, tf)
            for tf in TIMEFRAMES
        ]
        results = await asyncio.gather(*tasks)
        return {tf: result for tf, result in zip(TIMEFRAMES, results)}

def fetch_symbols():
    import requests
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    response = requests.get(url)
    data = response.json()
    symbols = [
        x["symbol"] for x in data["result"]["list"]
        if "USDT" in x["symbol"] and x["status"] == "Trading"
    ]
    log(f"✅ Fetched {len(symbols)} symbols.")
    return symbols

def fetch_candles(symbol, interval):
    import requests
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=100"
    try:
        response = requests.get(url)
        data = response.json()
        if data["retCode"] == 0:
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
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol} - {interval}: {e}")
        return []
