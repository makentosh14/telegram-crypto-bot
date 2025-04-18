import asyncio
import aiohttp
from config import BYBIT_API_URL, TIMEFRAMES
from rsi import calculate_rsi
from macd import calculate_macd
from supertrend import get_supertrend_signal
from volume import detect_volume_spike
from patterns import detect_bullish_patterns
from bollinger import detect_bollinger_breakout
from ema import detect_ema_crossover
from logger import log
from trend_filters import detect_breakout

async def fetch_symbols(session):
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    try:
        async with session.get(url) as resp:
            data = await resp.json()
            if data["retCode"] == 0:
                symbols = [
                    s["symbol"] for s in data["result"]["list"]
                    if "USDT" in s["symbol"] and s["status"] == "Trading"
                ]
                log(f"✅ Fetched {len(symbols)} symbols")
                return symbols
            else:
                log("❌ Failed to fetch symbols", data)
                return []
    except Exception as e:
        log(f"❌ Exception fetching symbols: {e}")
        return []

async def fetch_candles(session, symbol, interval, limit=100):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        async with session.get(url) as resp:
            res = await resp.json()
            candles = [
                {
                    'timestamp': int(i[0]),
                    'open': i[1],
                    'high': i[2],
                    'low': i[3],
                    'close': i[4],
                    'volume': i[5]
                }
                for i in res['result']['list']
            ]
            return candles[::-1]
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol} {interval}: {e}")
        return []

async def fetch_all_candles(session, symbol):
    tasks = []
    for tf in TIMEFRAMES:
        tasks.append(fetch_candles(session, symbol, tf))
    results = await asyncio.gather(*tasks)
    return dict(zip(TIMEFRAMES, results))

def score_symbol(symbol, candles_by_tf):
    scores = {}
    total_score = 0
    weights = {'5m': 0.3, '15m': 0.4, '1h': 0.3}

    for tf, candles in candles_by_tf.items():
        tf_score = 0
        if not candles or len(candles) < 50:
            scores[tf] = 0
            continue

        close_prices = [float(c['close']) for c in candles]
        high_prices = [float(c['high']) for c in candles]
        low_prices = [float(c['low']) for c in candles]

        rsi = calculate_rsi(close_prices)
        if rsi < 30:
            tf_score += 1
        elif rsi > 70:
            tf_score -= 1

        macd, signal = calculate_macd(close_prices)
        if macd > signal:
            tf_score += 1
        elif macd < signal:
            tf_score -= 1

        st = get_supertrend_signal(candles)
        if st == "buy":
            tf_score += 1
        elif st == "sell":
            tf_score -= 1

        if detect_volume_spike(candles):
            tf_score += 1

        tf_score += detect_bullish_patterns(candles)

        if detect_bollinger_breakout(close_prices):
            tf_score += 1

        if detect_ema_crossover(close_prices):
            tf_score += 1

        if detect_breakout(candles):
            tf_score += 1

        scores[tf] = tf_score
        total_score += tf_score * weights[tf]

    return round(total_score, 2), scores

async def scan_symbols():
    results = []
    async with aiohttp.ClientSession() as session:
        symbols = await fetch_symbols(session)
        tasks = []
        for symbol in symbols:
            tasks.append(process_symbol(session, symbol))
        results = await asyncio.gather(*tasks)
    ranked = sorted([r for r in results if r], key=lambda x: x["score"], reverse=True)
    return ranked[:5]

async def process_symbol(session, symbol):
    try:
        candles_by_tf = await fetch_all_candles(session, symbol)
        score, details = score_symbol(symbol, candles_by_tf)
        return {
            "symbol": symbol,
            "score": score,
            "details": details
        }
    except Exception as e:
        log(f"⚠️ Error scoring {symbol}: {e}")
        return None
