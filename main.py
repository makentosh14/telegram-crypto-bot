# main.py (Final Version: Full Strategy Logic + Smart Formatting + Per-Coin Live Scan + Direction + Monitoring + Score Rebuild)

import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_trade_type, determine_direction
from telegram_bot import send_telegram_message, format_trade_signal
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import MIN_SCORE_THRESHOLD, DEFAULT_LEVERAGE
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}

async def run_bot():
    log("🚀 Bot starting...")

    symbols = await fetch_symbols()
    log(f"✅ Fetched {len(symbols)} symbols.")

    asyncio.create_task(stream_candles(symbols))
    await asyncio.sleep(5)

    while True:
        try:
            trend_context = await get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            for i, symbol in enumerate(symbols, 1):
                if symbol not in live_candles:
                    continue

                try:
                    candles_by_tf = {
                        tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
                    }
                except Exception:
                    continue

                if not all(len(candles_by_tf[tf]) >= 30 for tf in TIMEFRAMES):
                    continue

                score, tf_scores = score_symbol(symbol, candles_by_tf)
                trade_type = determine_trade_type(tf_scores)
                direction = determine_direction(tf_scores)

                price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0

                sl_pct = 0.7 if trade_type == "Scalp" else (1.5 if trade_type == "Intraday" else 2.5)
                tp1_pct = 1.5 if trade_type == "Scalp" else (3.0 if trade_type == "Intraday" else 6.0)
                trailing_pct = 0.3 if trade_type == "Scalp" else (0.6 if trade_type == "Intraday" else 1.0)
                risk_pct = 3.0 if trade_type == "Scalp" else (2.0 if trade_type == "Intraday" else 1.0)
                leverage = DEFAULT_LEVERAGE

                sl = round(price * (1 - sl_pct / 100), 4) if direction == "Long" else round(price * (1 + sl_pct / 100), 4)
                tp1 = round(price * (1 + tp1_pct / 100), 4) if direction == "Long" else round(price * (1 - tp1_pct / 100), 4)

                log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type} | Dir: {direction}")

                # Monitoring logic
                if symbol in active_signals:
                    data = active_signals[symbol]
                    previous_score = data['score']
                    data['score_history'].append(score)

                    # Exit logic on score drop
                    if trade_type == "Scalp" and all(s < 5 for s in data['score_history'][-2:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Scalp setup.")
                        del active_signals[symbol]
                        log_trade_result(False, -1.0)
                        continue
                    if trade_type == "Intraday" and all(s < 5 for s in data['score_history'][-3:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Intraday setup.")
                        del active_signals[symbol]
                        log_trade_result(False, -2.0)
                        continue
                    if trade_type == "Swing" and all(s < 4 for s in data['score_history'][-4:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Swing setup.")
                        del active_signals[symbol]
                        log_trade_result(False, -3.0)
                        continue

                    # Rebound alert
                    if previous_score < 6 and score >= 8:
                        await send_telegram_message(f"♻️ {symbol} score rebounded from {previous_score} to {score}. Re-entry?")

                    continue  # skip sending new alert if it's already active

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    log_signal(symbol)
                    track_signal(symbol, score)

                    msg = format_trade_signal(
                        symbol=symbol,
                        score=score,
                        tf_scores=tf_scores,
                        trend=trend_context,
                        entry_price=price,
                        sl=sl,
                        tp1=tp1,
                        trade_type=trade_type,
                        direction=direction,
                        trailing_pct=trailing_pct,
                        leverage=leverage,
                        risk_pct=risk_pct
                    )

                    await send_telegram_message(msg)
                    active_signals[symbol] = {
                        'score': score,
                        'score_history': [score]
                    }

            await send_daily_report()

        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")

        await asyncio.sleep(0.5)

if __name__ == "__main__":
    log("🔧 DEBUG TEST: main.py is running...")
    asyncio.run(run_bot())

aaa
