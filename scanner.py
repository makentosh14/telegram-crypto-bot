import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                symbols = [item['symbol'] for item in data['result']['list'] if "USDT" in item['symbol']]
                return symbols
    except Exception as e:
        log(f"❌ Error fetching symbols: {e}")
        return []

async def fetch_candles_for_symbol(session, symbol, timeframe):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit=100"
    try:
        async with session.get(url) as response:
            data = await response.json()
            if data['retCode'] == 0:
                candles = [
                    {
                        'timestamp': int(entry[0]),
                        'open': entry[1],
                        'high': entry[2],
                        'low': entry[3],
                        'close': entry[4],
                        'volume': entry[5]
                    }
                    for entry in data['result']['list']
                ]
                return list(reversed(candles))
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol}-{timeframe}: {e}")
    return []

async def fetch_candles(symbol, timeframes=TIMEFRAMES):
    result = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candles_for_symbol(session, symbol, tf) for tf in timeframes]
        responses = await asyncio.gather(*tasks)
        for i, tf in enumerate(timeframes):
            result[tf] = responses[i]
    return result

def run_async(func, *args, **kwargs):
    return asyncio.get_event_loop().run_until_complete(func(*args, **kwargs))
