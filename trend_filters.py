# trend_filters.py (with Regime Detection)

import aiohttp

async def fetch_kline(symbol, interval='60', limit=5, category='linear'):
    url = f"https://api.bybit.com/v5/market/kline?category={category}&symbol={symbol}&interval={interval}&limit={limit}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data.get('result', {}).get('list', []) if data.get('retCode') == 0 else []

async def get_btc_trend():
    candles = await fetch_kline("BTCUSDT", interval="60", limit=3)
    if len(candles) < 2:
        return "ranging"
    prev = float(candles[-2][4])  # previous close
    curr = float(candles[-1][4])  # current close
    if abs(curr - prev) < 0.001 * curr:
        return "ranging"
    return "uptrend" if curr > prev else "downtrend"

async def is_altseason():
    candles = await fetch_kline("ETHBTC", interval="60", limit=3, category="spot")
    if len(candles) < 2:
        return False
    prev = float(candles[-2][4])
    curr = float(candles[-1][4])
    return curr > prev  # ETHBTC rising implies altseason

async def detect_market_regime():
    candles = await fetch_kline("BTCUSDT", interval="60", limit=4)
    if len(candles) < 3:
        return "unknown"

    movements = []
    directions = []

    for i in range(1, len(candles)):
        prev_close = float(candles[i - 1][4])
        curr_close = float(candles[i][4])
        body_size = abs(curr_close - prev_close) / prev_close
        movements.append(body_size)
        directions.append("up" if curr_close > prev_close else "down")

    avg_movement = sum(movements) / len(movements)
    same_dir = all(d == directions[0] for d in directions)

    if avg_movement > 0.015:  # >1.5% average movement per hour
        return "volatile"
    elif same_dir and avg_movement > 0.006:
        return "trending"
    else:
        return "ranging"

async def get_trend_context():
    btc = await get_btc_trend()
    alt = await is_altseason()
    regime = await detect_market_regime()
    return {
        "btc_trend": btc,
        "altseason": alt,
        "regime": regime
    }
