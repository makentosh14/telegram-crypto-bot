# main.py

import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import TRADING_MODE, MIN_SCORE_THRESHOLD, BASE_SCAN_INTERVAL
from performance_tracker import track_signal
from logger import log

TIMEFRAMES = ['1']

async def run_bot():
    log("🚀 Bot starting...")

    symbols = await fetch_symbols()
    top_symbols = symbols  # ✅ Now scanning ALL symbols
    log(f"✅ Scanning ALL {len(top_symbols)} symbols...")

    asyncio.create_task(stream_candles(top_symbols, interval='1'))
    await asyncio.sleep(5)

    while True:
        try:
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            max_risk = 0.015 if btc_trend == "downtrend" else (0.04 if altseason else 0.025)

            top_signals = []
            signals_this_round = 0

            log(f"🔄 Starting scan of {len(top_symbols)} symbols...")

            for i, symbol in enumerate(top_symbols, 1):
                if symbol not in live_candles:
                    log(f"⏩ [{i}/{len(top_symbols)}] Skipping {symbol}: no live candles yet")
                    continue

                candles_by_tf = {
                    tf: list(live_candles[symbol]) for tf in TIMEFRAMES
                }

                if any(len(c) < 30 for c in candles_by_tf.values()):
                    log(f"⏩ [{i}/{len(top_symbols)}] Skipping {symbol}: not enough candle history")
                    continue

                score, tf_scores = score_symbol(symbol, candles_by_tf)
                log(f"🔍 [{i}/{len(top_symbols)}] {symbol} | Total Score: {score} | TF Scores: {tf_scores}")

                if score >= MIN_SCORE_THRESHOLD:
                    if not is_duplicate_signal(symbol):
                        log_signal(symbol)
                        track_signal(symbol, score)
                        signals_this_round += 1

                        if TRADING_MODE == "auto":
                            await execute_trade_if_valid({
                                'symbol': symbol,
                                'score': score,
                                'tf_scores': tf_scores,
                                'btc_trend': btc_trend,
                                'altseason': altseason
                            }, max_risk=max_risk)
                        else:
                            await send_telegram_message(
                                f"🚨 <b>Trade Signal</b>\nSymbol: <b>{symbol}</b>\nScore: {score}\nTFs: {tf_scores}"
                            )

                        top_signals.append(symbol)

            log(f"✅ Round complete | High-quality signals: {signals_this_round} / {len(top_symbols)}")

            if not top_signals:
                log("⚠️ No high-quality signals this round.")
                await send_telegram_message("⚠️ No high-quality signals this round.")

        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")
            
if __name__ == "__main__":
    asyncio.run(run_bot())
