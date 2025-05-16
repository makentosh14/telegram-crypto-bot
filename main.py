import asyncio
import traceback
import time
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
from monitor import track_active_trade, monitor_trades, load_active_trades, check_and_restore_sl
from pattern_detector import detect_pattern
from volume import is_volume_spike
from whale_detector import detect_whale_activity
from ai_memory import load_memory
from mean_reversion import score_mean_reversion
from breakout_sniper import score_breakout_sniper
from strategy_performance import get_strategy_stats
from risk_manager import calculate_dynamic_risk

load_memory()

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10

MIN_SCALP_SCORE = 6.5
MIN_INTRADAY_SCORE = 7.0
MIN_SWING_SCORE = 7.5

def extract_last_pattern(candles_by_tf):
    for tf in sorted(candles_by_tf, key=lambda x: int(x)):
        pattern = detect_pattern(candles_by_tf[tf])
        if pattern:
            return pattern
    return None

async def scan_for_new_signals(symbols):
    trend_context = await get_trend_context()
    regime = trend_context.get("regime", "trending")

    score_adjustments = {
        "volatile": {"scalp": 0.5, "intraday": 0.5, "swing": 0.5},
        "ranging": {"scalp": 1.0, "intraday": 1.0, "swing": 1.0},
        "trending": {"scalp": 0.0, "intraday": 0.0, "swing": 0.0},
    }
    adjust = score_adjustments.get(regime, {"scalp": 0, "intraday": 0, "swing": 0})
    adj_scalp = MIN_SCALP_SCORE + adjust["scalp"]
    adj_intraday = MIN_INTRADAY_SCORE + adjust["intraday"]
    adj_swing = MIN_SWING_SCORE + adjust["swing"]

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

        # ---- Primary strategy scoring ----
        score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(symbol, candles_by_tf)
        direction = determine_direction(tf_scores)
        confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
        price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0

        risk_pct = 9.0 if trade_type == "Scalp" else (6.0 if trade_type == "Intraday" else 3.0)
        strategy = "core_strategy"
        if tf_scores.get("mean_reversion"):
            strategy = "mean_reversion"
        elif tf_scores.get("breakout_sniper"):
            strategy = "breakout_sniper"
        
        if trade_type == "Scalp":
            base_risk = 0.09
        elif trade_type == "Intraday":
            base_risk = 0.06
        else:
            base_risk = 0.03
           
        risk_pct = calculate_dynamic_risk(symbol, confidence, strategy, base_risk)

        stats = get_strategy_stats(strategy)
        win_rate = stats["win_rate"]

        if win_rate >= 70:
            risk_pct = base_risk * 1.2
        elif win_rate <= 40:
            risk_pct = base_risk * 0.6
        else:
            risk_pct = base_risk

        tf_breakdown = ", ".join(f"{k}m: {v:.1f}" for k, v in tf_scores.items())
        log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score:.2f} | Type: {trade_type} | Dir: {direction} | Conf: {confidence:.1f}% | TFs: {tf_breakdown}")

        sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence, regime
        )

        pump_data = await detect_early_pump(candles_by_tf, symbol)
        if pump_data["trigger_count"] >= 3:
            pump_reasons = ', '.join([k for k, v in pump_data.items() if v is True and k != "trigger_count"])
            await send_telegram_message(
                f"🚀 <b>Early Pump Signal Detected!</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Triggers:</b> {pump_reasons} ({pump_data['trigger_count']}/4)"
            )

        if (trade_type == "Scalp" and score < adj_scalp) or \
           (trade_type == "Intraday" and score < adj_intraday) or \
           (trade_type == "Swing" and score < adj_swing):
            if trade_type == "Swing" and ALWAYS_ALLOW_SWING:
                log(f"⚠️ Swing setup below min score ({score} < {adj_swing}), but ALWAYS_ALLOW_SWING is enabled — skipping this one.")
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
            log(f"🔍 Checking new signal for {symbol} | Score: {score:.2f} | Direction: {direction} | Type: {trade_type}")
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
                leverage=DEFAULT_LEVERAGE,
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
                    tp2=None,
                    sl=trade.get("sl"),
                    qty=trade.get("qty"),
                    sl_order_id=trade.get("sl_order_id")
                )

                await verify_stop_loss_placement(symbol, trade, direction)

        # ✅ Additional Strategy: Mean Reversion Logic
        if regime == "ranging":
            rev_score, rev_dir, rev_conf, rev_reasons = score_mean_reversion(symbol, candles_by_tf, regime)
            if rev_score >= 4 and not is_duplicate_signal(symbol):
                log_signal(symbol)
                track_signal(symbol, rev_score)

                sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                    candles_by_tf, price, "Scalp", rev_dir, rev_score, rev_conf, regime
                )

                msg = format_trade_signal(
                    symbol=symbol,
                    score=rev_score,
                    tf_scores={"mean_reversion": rev_score},
                    trend=trend_context,
                    entry_price=price,
                    sl=sl,
                    tp1=tp1,
                    trade_type="Scalp",
                    direction=rev_dir,
                    trailing_pct=trailing_pct,
                    leverage=DEFAULT_LEVERAGE,
                    risk_pct=6.0,
                    confidence=rev_conf,
                    sl_pct=sl_pct
                )
                msg += f"\n🧠 Mean Reversion Signal\nTriggers: {', '.join(rev_reasons.keys())}"
                await send_telegram_message(msg)

        # ✅ Additional Strategy: Breakout Sniper Logic
        if regime == "volatile":
            bo_score, bo_dir, bo_conf, bo_reasons = score_breakout_sniper(symbol, candles_by_tf, regime)
            if bo_score >= 4 and not is_duplicate_signal(symbol):
                log_signal(symbol)
                track_signal(symbol, bo_score)

                sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                    candles_by_tf, price, "Scalp", bo_dir, bo_score, bo_conf, regime
                )

                msg = format_trade_signal(
                    symbol=symbol,
                    score=bo_score,
                    tf_scores={"breakout_sniper": bo_score},
                    trend=trend_context,
                    entry_price=price,
                    sl=sl,
                    tp1=tp1,
                    trade_type="Scalp",
                    direction=bo_dir,
                    trailing_pct=trailing_pct,
                    leverage=DEFAULT_LEVERAGE,
                    risk_pct=6.5,
                    confidence=bo_conf,
                    sl_pct=sl_pct
                )
                msg += f"\n💥 Breakout Sniper Signal\nTriggers: {', '.join(bo_reasons.keys())}"
                await send_telegram_message(msg)

async def verify_stop_loss_placement(symbol, trade, direction):
    """Verifies that the stop-loss order was properly placed and attempts to fix if not"""
    from monitor import check_and_restore_sl
    
    if not trade or not trade.get("sl_order_id"):
        log(f"⚠️ No SL order ID found for {symbol}, attempting to restore", level="WARN")
        # Create a temporary trade object with the minimum needed info for check_and_restore_sl
        temp_trade = {
            "direction": direction,
            "qty": trade.get("qty"),
            "original_sl": trade.get("sl"),
            "entry_price": trade.get("entry"),
            "exited": False
        }
        await check_and_restore_sl(symbol, temp_trade)
        await send_telegram_message(f"🔄 <b>SL Verification</b>: Attempted to restore missing SL for {symbol}")
    else:
        log(f"✅ SL order confirmed for {symbol}: {trade.get('sl_order_id')}")


async def monitor_loop():
    while True:
        try:
            await monitor_trades(live_candles)
        except Exception as e:
            log(f"❌ Error in monitor loop: {e}", level="ERROR")
            await send_error_to_telegram(traceback.format_exc())
        await asyncio.sleep(5)


async def sl_verification_loop():
    """New function to periodically verify all stop-losses for active trades"""
    from telegram_bot import send_telegram_message
    
    while True:
        try:
            from monitor import active_trades
            
            # Only check after the bot has been running for at least 3 minutes
            if time.time() - startup_time < 180:
                await asyncio.sleep(30)
                continue
                
            log(f"🛡️ Running SL verification for {len(active_trades)} active trades")
            
            for symbol, trade in active_trades.items():
                if not trade or trade.get("exited"):
                    continue
                
                await check_and_restore_sl(symbol, trade)
                
            log("✅ SL verification complete")
            
        except Exception as e:
            log(f"❌ Error in SL verification loop: {e}", level="ERROR")
            await send_error_to_telegram(f"SL verification error: {str(e)}")
        
        # Run every 15 minutes
        await asyncio.sleep(900)


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
    
    # Add the new SL verification loop
    asyncio.create_task(sl_verification_loop())

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
    
    # Store bot startup time for reference in various functions
    import time
    startup_time = time.time()

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
