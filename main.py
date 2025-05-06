import asyncio
import traceback
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_direction, calculate_confidence
from telegram_bot import send_telegram_message, format_trade_signal, send_error_to_telegram
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import DEFAULT_LEVERAGE, ALWAYS_ALLOW_SWING
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report
from trade_executor import calculate_dynamic_sl_tp, execute_trade_if_valid
from pump_detector import detect_early_pump
from symbol_info import fetch_symbol_info
from activity_logger import write_log, log_trade_to_file
from monitor import track_active_trade, monitor_trades, load_active_trades
from pattern_detector import detect_pattern
from volume import is_volume_spike
from whale_detector import detect_whale_activity
from ai_memory import load_memory

load_memory()

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10

MIN_SCALP_SCORE = 6.5
MIN_INTRADAY_SCORE = 7
MIN_SWING_SCORE = 7.5


def extract_last_pattern(candles_by_tf):
    for tf in sorted(candles_by_tf, key=lambda x: int(x)):
        pattern = detect_pattern(candles_by_tf[tf])
        if pattern:
            return pattern
    return None


async def scan_for_new_signals(symbols):
    trend_context = await get_trend_context()

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

        score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(symbol, candles_by_tf)
        direction = determine_direction(tf_scores)
        confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
        price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0
        leverage = DEFAULT_LEVERAGE
        risk_pct = 9.0 if trade_type == "Scalp" else (6.0 if trade_type == "Intraday" else 3.0)

        tf_breakdown = ", ".join(f"{k}m: {v:.1f}" for k, v in tf_scores.items())
        log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score:.2f} | Type: {trade_type} | Dir: {direction} | Conf: {confidence:.1f}% | TFs: {tf_breakdown}")

        sl, tp1, tp2, sl_pct, trailing_pct, tp1_pct, tp2_pct = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence
        )

        pump_data = await detect_early_pump(candles_by_tf, symbol)
        if pump_data["trigger_count"] >= 3:
            pump_reasons = ', '.join([k for k, v in pump_data.items() if v is True and k != "trigger_count"])
            await send_telegram_message(
                f"🚀 <b>Early Pump Signal Detected!</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Triggers:</b> {pump_reasons} ({pump_data['trigger_count']}/4)"
            )

        if (trade_type == "Scalp" and score < MIN_SCALP_SCORE) or \
           (trade_type == "Intraday" and score < MIN_INTRADAY_SCORE) or \
           (trade_type == "Swing" and score < MIN_SWING_SCORE):
            if trade_type == "Swing" and ALWAYS_ALLOW_SWING:
                log(f"⚠️ Swing setup below min score ({score} < {MIN_SWING_SCORE}), but ALWAYS_ALLOW_SWING is enabled — skipping this one.")
                continue
            continue

        if symbol in active_signals:
            data = active_signals[symbol]
            data['score_history'].append(score)
            exit_required = (
                (trade_type == "Scalp" and all(s < 5 for s in data['score_history'][-2:])) or
                (trade_type == "Intraday" and all(s < 5 for s in data['score_history'][-3:])) or
                (trade_type == "Swing" and all(s < 4 for s in data['score_history'][-4:]))
            )
            if exit_required:
                await send_telegram_message(f"❌ Exit {symbol} | Score dropped.")
                del active_signals[symbol]
                recent_exits[symbol] = EXIT_COOLDOWN
                await log_trade_result(symbol, "loss", -1.0)
            continue

        if not is_duplicate_signal(symbol):
            await asyncio.sleep(2)
            re_score, re_tf_scores, re_type, _, _ = score_symbol(symbol, candles_by_tf)
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

            trade = await execute_trade_if_valid({
                "symbol": symbol,
                "price": price,
                "trade_type": trade_type,
                "direction": direction,
                "score": score,
                "confidence": confidence,
                "candles": candles_by_tf,
                "indicator_scores": indicator_scores,
                "used_indicators": used_indicators,
                "tf_scores": tf_scores,
                "pattern": extract_last_pattern(candles_by_tf),
                "whale": detect_whale_activity(candles_by_tf.get("5", [])),
                "volume_spike": is_volume_spike(candles_by_tf.get("1", []), 2.5)
            })

            if trade:
                log(f"🛒 Trade placed successfully for {symbol} at {trade['entry']}")
                write_log(f"TRADE SENT: {symbol} | Entry: {trade['entry']} | SL: {trade['sl']} | TP1: {trade['tp1']}")

                track_active_trade(
                    symbol=symbol,
                    trade_type=trade_type,
                    initial_score=score,
                    entry_price=price,
                    direction=direction,
                    trailing_pct=trade.get("trailing_pct"),
                    tp2=trade.get("tp2"),
                    sl=trade.get("sl")
                )



async def monitor_loop():
    while True:
        try:
            await monitor_trades(live_candles)
        except Exception as e:
            log(f"❌ Error in monitor loop: {e}", level="ERROR")
            await send_error_to_telegram(traceback.format_exc())
        await asyncio.sleep(5)


async def pattern_discovery_loop(symbols):
    while True:
        try:
            await pattern_discovery_scan(symbols)
        except Exception as e:
            log(f"❌ Error in pattern discovery loop: {e}", level="ERROR")
        await asyncio.sleep(60)


async def pattern_match_loop(symbols):
    while True:
        try:
            await pattern_match_scan(symbols)
        except Exception as e:
            log(f"❌ Error in pattern match loop: {e}")
        await asyncio.sleep(60)


async def pattern_summary_loop():
    while True:
        await asyncio.sleep(3600)
        from pattern_matcher import pattern_stats
        await send_telegram_message(
            f"⏱ <b>Pattern Scan Summary (last hour)</b>\n"
            f"Scans: {pattern_stats['scans']}\n"
            f"Matches: {pattern_stats['matches']}\n"
            f"Trades Triggered: {pattern_stats['trades']}"
        )
        pattern_stats['scans'] = 0
        pattern_stats['matches'] = 0
        pattern_stats['trades'] = 0


async def run_bot():
    log("🚀 Bot starting...")
    await fetch_symbol_info()
    symbols = await fetch_symbols()
    log(f"✅ Fetched {len(symbols)} symbols.")

    load_active_trades()
    asyncio.create_task(stream_candles(symbols))
    asyncio.create_task(monitor_loop())
    asyncio.create_task(pattern_discovery_loop(symbols))
    asyncio.create_task(pattern_match_loop(symbols))
    asyncio.create_task(pattern_summary_loop())

    await asyncio.sleep(5)

    while True:
        try:
            await scan_for_new_signals(symbols)
            await send_daily_report()
        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")
            write_log(f"MAIN LOOP ERROR: {str(e)}", level="ERROR")
            await send_error_to_telegram(traceback.format_exc())
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    log("🔧 DEBUG: main.py is running...")

    async def restart_forever():
        while True:
            try:
                await run_bot()
            except Exception as e:
                err_msg = f"🔁 Restarting bot due to crash:\n{traceback.format_exc()}"
                log(err_msg, level="ERROR")
                await send_error_to_telegram(err_msg)
                await asyncio.sleep(10)

    asyncio.run(restart_forever())
