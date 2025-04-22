# main.py — DEBUG: log score for every coin

import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_trade_type
from telegram_bot import send_telegram_message
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import MIN_SCORE_THRESHOLD, BASE_SCAN_INTERVAL
from performance_tracker import track_signal
from logger import log

TIMEFRAMES = SUPPORTED_INTERVALS

async def run_bot():
    log("\U0001f680 Bot starting...")

    symbols = await fetch_symbols()
    log(f"✅ Scanning ALL {len(symbols)} symbols...")

    asyncio.create_task(stream_candles(symbols))
    await asyncio.sleep(5)

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

                candles_by_tf = {tf: list(live_candles[symbol]) for tf in TIMEFRAMES}
                candle_counts = {tf: len(candles_by_tf[tf]) for tf in TIMEFRAMES}
                log(f"🔗 {symbol} Candle counts: {candle_counts}")

                if not all(len(candles_by_tf[tf]) >= 30 for tf in TIMEFRAMES):
                    log(f"⏩ [{i}/{len(symbols)}] Skipping {symbol}: not all timeframes have enough candles")
                    continue

                # Log score for all coins regardless of value
                score, tf_scores = score_symbol(symbol, candles_by_tf)
                trade_type = determine_trade_type(tf_scores)

                log(f"🔍 [{i}/{len(symbols)}] {symbol} | Score: {score} | TF Scores: {tf_scores} | Type: {trade_type}")

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    log_signal(symbol)
                    track_signal(symbol, score)
                    high_signals += 1

                    await send_telegram_message(
                        f"🚨 <b>{trade_type} Signal</b>\n"
                        f"Symbol: <b>{symbol}</b>\n"
                        f"Score: {score} | TFs: {tf_scores}\n"
                        f"Trend: BTC={btc_trend}, Altseason={altseason}\n\n"
                        f"<i>Entry at market price</i>\n"
                        f"SL: Dynamic based on structure\n"
                        f"TP1: Based on {trade_type.lower()} target\n"
                        f"🧐 Smart Trailing SL will activate after TP1."
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
