# main.py — Final Upgraded Version ✅

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
    log("\n🚀 Bot starting...")

    symbols = await fetch_symbols()
    log(f"✅ Loaded {len(symbols)} tradable symbols from Bybit")

    asyncio.create_task(stream_candles(symbols))
    await asyncio.sleep(5)

    while True:
        try:
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            high_signals = 0
            log(f"\n🔄 Starting scan of {len(symbols)} symbols...")

            for i, symbol in enumerate(symbols, 1):
                if symbol not in live_candles:
                    continue

                candles_by_tf = {tf: list(live_candles[symbol]) for tf in TIMEFRAMES}
                if any(len(candles) < 30 for candles in candles_by_tf.values()):
                    continue

                score, tf_scores = score_symbol(symbol, candles_by_tf)
                trade_type = determine_trade_type(tf_scores)

                log(f"🔍 [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type}")

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    log_signal(symbol)
                    track_signal(symbol, score)
                    high_signals += 1

                    entry_price = float(candles_by_tf['1'][-1]['close'])
                    sl_buffer = 0.01 if trade_type == "Scalp" else 0.015 if trade_type == "Intraday" else 0.025
                    tp1_buffer = 0.015 if trade_type == "Scalp" else 0.03 if trade_type == "Intraday" else 0.06
                    tp2_buffer = tp1_buffer * 1.5
                    trailing_sl_pct = 0.5 if trade_type == "Scalp" else 1.0 if trade_type == "Intraday" else 1.5

                    sl_price = round(entry_price * (1 - sl_buffer), 4)
                    tp1_price = round(entry_price * (1 + tp1_buffer), 4)
                    tp2_price = round(entry_price * (1 + tp2_buffer), 4)

                    await send_telegram_message(
                        f"🚨 <b>{trade_type} Signal</b>\n"
                        f"Symbol: <b>{symbol}</b>\n"
                        f"Entry: <code>{entry_price}</code>\n"
                        f"SL: <code>{sl_price}</code>\n"
                        f"TP1: <code>{tp1_price}</code>\n"
                        f"TP2: <code>{tp2_price}</code>\n"
                        f"Trailing SL: {trailing_sl_pct}%\n\n"
                        f"TF Scores: {tf_scores} | Total Score: {score}\n"
                        f"Trend: BTC={btc_trend} | Altseason={altseason}"
                    )

        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")

        await asyncio.sleep(BASE_SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_bot())
