# trend_filters.py (Real Market Trend Detection)

import aiohttp

async def fetch_kline(symbol, interval='60', limit=3, category='linear'):
    url = f"https://api.bybit.com/v5/market/kline?category={category}&symbol={symbol}&interval={interval}&limit={limit}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data.get('result', {}).get('list', []) if data.get('retCode') == 0 else []

async def get_btc_trend():
    candles = await fetch_kline("BTCUSDT")
    if len(candles) < 2:
        return "ranging"
    prev = float(candles[-2][4])  # previous close
    curr = float(candles[-1][4])  # current close
    if abs(curr - prev) < 0.001 * curr:
        return "ranging"
    return "uptrend" if curr > prev else "downtrend"

async def is_altseason():
    candles = await fetch_kline("ETHBTC", category="spot")
    if len(candles) < 2:
        return False
    prev = float(candles[-2][4])
    curr = float(candles[-1][4])
    return curr > prev  # ETHBTC rising implies altseason

async def get_trend_context():
    btc = await get_btc_trend()
    alt = await is_altseason()
    return {
        "btc_trend": btc,
        "altseason": alt
    }
