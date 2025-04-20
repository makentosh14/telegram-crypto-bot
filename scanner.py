import aiohttp
import asyncio
from config import BYBIT_API_URL, TIMEFRAMES
from logger import log
from trend_filters import detect_breakout

async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if 'result' in data and 'list' in data['result']:
                    symbols = [item['symbol'] for item in data['result']['list']]
                    return symbols
                else:
                    log("⚠️ Unexpected response structure.")
                    return []
    except Exception as e:
        log(f"❌ Error fetching symbols: {e}")
        return []

async def fetch_candles(symbol, timeframe='5m', limit=100):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit={limit}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if 'result' in data and 'list' in data['result']:
                    candles = []
                    for item in data['result']['list']:
                        candles.append({
                            'timestamp': int(item[0]),
                            'open': item[1],
                            'high': item[2],
                            'low': item[3],
                            'close': item[4],
                            'volume': item[5]
                        })
                    return candles
                else:
                    log(f"⚠️ Invalid candle response for {symbol}")
                    return []
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol}: {e}")
        return []
