import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_direction, calculate_confidence
from telegram_bot import send_telegram_message, format_trade_signal
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import DEFAULT_LEVERAGE
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report
from trade_executor import calculate_dynamic_sl_tp

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10

MIN_SCALP_SCORE = 6.5
MIN_INTRADAY_SCORE = 7.5
MIN_SWING_SCORE = 8.0

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

                score, tf_scores, trade_type = score_symbol(symbol, candles_by_tf)
                direction = determine_direction(tf_scores)
                confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
                price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0
                leverage = DEFAULT_LEVERAGE
                risk_pct = 3.0 if trade_type == "Scalp" else (2.0 if trade_type == "Intraday" else 1.0)

                sl, tp1, sl_pct, trailing_pct = calculate_dynamic_sl_tp(
                    candles_by_tf, price, trade_type, direction, score, confidence
                )

                log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type} | Dir: {direction} | Conf: {confidence}%")

                if trade_type == "Swing" and btc_trend != "strong":
                    continue
                if trade_type == "Scalp" and score < MIN_SCALP_SCORE:
                    continue
                if trade_type == "Intraday" and score < MIN_INTRADAY_SCORE:
                    continue
                if trade_type == "Swing" and score < MIN_SWING_SCORE:
                    continue

                if symbol in active_signals:
                    data = active_signals[symbol]
                    data['score_history'].append(score)
                    if trade_type == "Scalp" and all(s < 5 for s in data['score_history'][-2:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped on Scalp.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(symbol, "loss", -1.0)
                        continue
                    if trade_type == "Intraday" and all(s < 5 for s in data['score_history'][-3:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped on Intraday.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(symbol, "loss", -2.0)
                        continue
                    if trade_type == "Swing" and all(s < 4 for s in data['score_history'][-4:]):
                        await send_telegram_message(f"❌ Exit {symbol} | Score dropped on Swing.")
                        del active_signals[symbol]
                        recent_exits[symbol] = EXIT_COOLDOWN
                        log_trade_result(symbol, "loss", -3.0)
                        continue
                    continue

                if not is_duplicate_signal(symbol):
                    await asyncio.sleep(2)
                    re_score, re_tf_scores, re_type = score_symbol(symbol, candles_by_tf)
                    re_direction = determine_direction(re_tf_scores)
                    if re_score < score or re_type != trade_type or re_direction != direction:
                        continue

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
                        confidence=confidence,
                        sl_pct=sl_pct
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
