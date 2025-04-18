import asyncio
from bybit_api import fetch_klines
from score import score_symbol

TIMEFRAMES = ['5m', '15m', '1h']

async def scan_symbol(symbol):
    candles_by_timeframe = {}
    for tf in TIMEFRAMES:
        candles = await fetch_klines(symbol, tf)
        if candles:
            candles_by_timeframe[tf] = candles
    total_score, tf_scores = score_symbol(symbol, candles_by_timeframe)
    return {
        'symbol': symbol,
        'total_score': total_score,
        'scores': tf_scores
    }

async def scan_symbols(symbols):
    tasks = [scan_symbol(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks)
    return [res for res in results if res['total_score'] > 0]
