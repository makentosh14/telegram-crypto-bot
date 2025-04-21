# main.py

import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol
from telegram_bot import send_telegram_message
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import MIN_SCORE_THRESHOLD, BASE_SCAN_INTERVAL
from performance_tracker import track_signal
from logger import log

TIMEFRAMES = SUPPORTED_INTERVALS  # ✅ Scanning multiple timeframes

async def run_bot():
    log("🚀 Bot starting...")

    symbols = await fetch_symbols()
    log(f"✅ Scanning ALL {len(symbols)} symbols...")

    asyncio.create_task(stream_candles(symbols, interval='1'))
    await asyncio.sleep(5)  # Wait for initial candles

    while True:
        try:
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            high_signals = 0
            log(f"🔄 Starting scan of {len(symbols)} symbols...")

            for i, symbol in enumerate(symbols, 1):
                if symbol not in live_candles:
                    log(f"⏩ [{i}/{len(symbols)}] Skipping {symbol}: no live candles yet")
                    continue

                candles_by_tf = {
                    tf: list(live_candles[symbol]) for tf in TIMEFRAMES
                }

                if any(len(c) < 30 for c in candles_by_tf.values()):
                    log(f"⏩ [{i}/{len(symbols)}] Skipping {symbol}: insufficient candle history")
                    continue

                score, tf_scores, trade_type = score_symbol(symbol, candles_by_tf)
                log(f"🔍 [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type}")

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    log_signal(symbol)
                    track_signal(symbol, score)
                    high_signals += 1

                    await send_telegram_message(
                        f"🚨 <b>Trade Signal</b> ({trade_type.upper()})\nSymbol: <b>{symbol}</b>\nScore: {score}\nTFs: {tf_scores}\nTrend: BTC={btc_trend}, Altseason={altseason}"
                    )

            log(f"✅ Round complete | Signals sent: {high_signals} / {len(symbols)}")

            if high_signals == 0:
                log("⚠️ No high-quality signals this round.")
                await send_telegram_message("⚠️ No high-quality signals this round.")

        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")

        await asyncio.sleep(BASE_SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_bot())
