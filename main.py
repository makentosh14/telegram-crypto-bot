import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_trade_type, determine_direction, calculate_confidence
from telegram_bot import send_telegram_message, format_trade_signal
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import MIN_SCORE_THRESHOLD, DEFAULT_LEVERAGE
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report
import time

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10  # number of cycles to wait before re-allowing same coin

async def run_bot():
    log("\U0001F680 Bot starting...")

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

                if recent_exits.get(symbol, 0) > 0:
                    recent_exits[symbol] -= 1
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
                confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)

                price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0

                sl_pct = 0.7 if trade_type == "Scalp" else (1.5 if trade_type == "Intraday" else 2.5)
                tp1_pct = 1.5 if trade_type == "Scalp" else (3.0 if trade_type == "Intraday" else 6.0)
                trailing_pct = 0.3 if trade_type == "Scalp" else (0.6 if trade_type == "Intraday" else 1.0)
                risk_pct = 3.0 if trade_type == "Scalp" else (2.0 if trade_type == "Intraday" else 1.0)
                leverage = DEFAULT_LEVERAGE

                sl = round(price * (1 - sl_pct / 100), 4) if direction == "Long" else round(price * (1 + sl_pct / 100), 4)
                tp1 = round(price * (1 + tp1_pct / 100), 4) if direction == "Long" else round(price * (1 - tp1_pct / 100), 4)

                log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type} | Dir: {direction} | Conf: {confidence}%")

                if trade_type == "Swing" and btc_trend != "strong":
                    continue  # skip swing trades when BTC not trending

                if symbol in active_signals:
                    data = active_signals[symbol]
                    previous_score = data['score']
                    data['score_history'].append(score)

                    if trade_type == "Scalp" and all(s < 5 for s in data['score_history'][-2:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Scalp setup.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(False, -1.0)
                        continue
                    if trade_type == "Intraday" and all(s < 5 for s in data['score_history'][-3:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Intraday setup.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(False, -2.0)
                        continue
                    if trade_type == "Swing" and all(s < 4 for s in data['score_history'][-4:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped to {score} on Swing setup.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(False, -3.0)
                        continue

                    if previous_score < 6 and score >= 8:
                        if recent_exits.get(symbol, 0) == 0:
                            await send_telegram_message(f"♻️ {symbol} score rebounded from {previous_score} to {score}. Re-entry?")

                    continue

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    await asyncio.sleep(2)  # recheck
                    re_score, re_tf_scores = score_symbol(symbol, candles_by_tf)
                    re_type = determine_trade_type(re_tf_scores)
                    re_direction = determine_direction(re_tf_scores)

                    if re_score < MIN_SCORE_THRESHOLD or re_type != trade_type or re_direction != direction:
                        continue  # false spike or changed setup

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
                        risk_pct=risk_pct,
                        confidence=confidence
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
