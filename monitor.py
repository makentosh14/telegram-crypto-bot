import json
import os
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log, write_log
from exit_manager import should_trail_stop
from auto_reentry import log_exit, update_exit_cooldowns, should_reenter, handle_reentry
from ai_memory import log_trade_result
from activity_logger import log_trade_to_file  # ✅ NEW

PERSIST_PATH = "monitor_active_trades.json"
active_trades = {}

def save_active_trades():
    try:
        with open(PERSIST_PATH, 'w') as f:
            json.dump(active_trades, f, indent=2)
    except Exception as e:
        log(f"❌ Failed to save trades: {e}", level="ERROR")

def load_active_trades():
    global active_trades
    if os.path.exists(PERSIST_PATH):
        try:
            with open(PERSIST_PATH, 'r') as f:
                active_trades = json.load(f)
                for symbol in active_trades:
                    active_trades[symbol]["exited"] = False
            log("🔁 Loaded active trades from disk")
        except Exception as e:
            log(f"❌ Failed to load active trades: {e}", level="ERROR")

def track_active_trade(symbol, trade_type, initial_score, entry_price=None, direction=None, trailing_pct=None, tp2=None, sl=None):
    active_trades[symbol] = {
        "score_history": [initial_score],
        "trade_type": trade_type,
        "entry_price": entry_price,
        "direction": direction,
        "cycles": 0,
        "exited": False,
        "trailing_pct": trailing_pct,
        "trailing_sl": None,
        "original_sl": sl,
        "tp1_hit": False,
        "tp2_hit": False,
        "tp2": tp2
    }
    save_active_trades()

def remove_trade(symbol):
    if symbol in active_trades:
        del active_trades[symbol]
        save_active_trades()

def get_exit_threshold(trade_type):
    return {
        "Scalp": 6,
        "Intraday": 6,
        "Swing": 5
    }.get(trade_type, 6)

def get_exit_cycles(trade_type):
    return {
        "Scalp": 2,
        "Intraday": 3,
        "Swing": 4
    }.get(trade_type, 3)

async def monitor_trades(live_candles):
    from telegram_bot import send_telegram_message  # ✅ Lazy import to fix circular import
    update_exit_cooldowns()

    for symbol, trade in list(active_trades.items()):
        if trade.get("exited"):
            continue

        if not trade.get("entry_price") or not trade.get("direction"):
            write_log(f"🚫 Skipping ghost trade: {symbol} — Missing entry data")
            continue

        trade_type = trade["trade_type"]
        direction = trade["direction"]
        entry_price = trade["entry_price"]

        if symbol not in live_candles:
            continue

        try:
            candles_by_tf = {
                tf: list(live_candles[symbol][str(tf)]) for tf in ['1', '3', '5', '15', '30', '60', '240']
            }
        except Exception as e:
            log(f"Monitor: Failed to fetch candles for {symbol}: {e}", level="ERROR")
            write_log(f"MONITOR ERROR: {symbol} candle fetch failed: {e}", level="ERROR")
            continue

        score_data = score_symbol(symbol, candles_by_tf)
        score, tf_scores, trade_type, indicator_scores, used_indicators = score_data[:5]
        trade["score_history"].append(score)
        trade["cycles"] += 1

        current_price = float(candles_by_tf['1'][-1]['close'])
        trailing_pct = trade.get("trailing_pct")

        # ✅ SL Hit
        if not trade.get("tp1_hit") and trade.get("original_sl"):
            sl_price = trade["original_sl"]
            if (direction == "Long" and current_price <= sl_price) or (direction == "Short" and current_price >= sl_price):
                trade["exited"] = True
                await send_telegram_message(
                    f"❌ <b>SL Hit</b> on <b>{symbol}</b>\nSL {sl_price:.4f} reached at price {current_price:.4f}"
                )
                write_log(f"SL HIT: {symbol} | SL: {sl_price} | Price: {current_price}")
                log_exit(symbol, score)
                log_trade_result(symbol, tf_scores, "loss")
                log_trade_to_file(symbol, direction, entry_price, sl_price, None, None, "loss", score, trade_type, 0, indicator_scores, used_indicators)
                save_active_trades()
                continue

        # ✅ TP1 Hit
        if not trade.get("tp1_hit") and direction and entry_price:
            tp1_level = entry_price * (1.018 if direction == "Long" else 0.982)
            if (direction == "Long" and current_price >= tp1_level) or (direction == "Short" and current_price <= tp1_level):
                trade["tp1_hit"] = True
                new_sl = entry_price
                trade["trailing_sl"] = new_sl
                await send_telegram_message(
                    f"🎯 <b>TP1 Hit</b> on <b>{symbol}</b>\n<b>Break-even SL activated</b> at {new_sl:.4f}"
                )
                write_log(f"TP1 HIT: {symbol} | Break-even SL set at {new_sl}")

        # ✅ TP2 Hit
        if trade.get("tp2") and not trade.get("tp2_hit"):
            tp2 = trade["tp2"]
            if (direction == "Long" and current_price >= tp2) or (direction == "Short" and current_price <= tp2):
                trade["tp2_hit"] = True
                await send_telegram_message(
                    f"🏑 <b>TP2 Target Hit</b> on <b>{symbol}</b>\nTarget: {tp2:.4f} | Current: {current_price:.4f}"
                )
                write_log(f"TP2 HIT: {symbol} | Reached: {current_price}")
                log_trade_result(symbol, tf_scores, "win")
                log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, tp2, "win", score, trade_type, 0, indicator_scores, used_indicators)

        # ✅ Trailing SL
        if trade.get("tp1_hit") and trailing_pct:
            new_sl = should_trail_stop(
                symbol, entry_price, current_price, direction.lower(),
                candles=candles_by_tf['1'],
                trigger_pct=trailing_pct * 2,
                trail_pct=trailing_pct
            )
            if new_sl and new_sl != trade.get("trailing_sl"):
                trade["trailing_sl"] = new_sl
                await send_telegram_message(
                    f"🔐 <b>Trailing SL Updated</b> for {symbol} | New SL: {new_sl}"
                )
                log(f"🔐 Smart SL updated for {symbol} to {new_sl}")
                write_log(f"TRAILING SL UPDATED: {symbol} | New SL: {new_sl} | Price: {current_price}")

        # ✅ Score-based Exit
        if score < get_exit_threshold(trade_type):
            if trade["cycles"] >= get_exit_cycles(trade_type):
                trade["exited"] = True
                await send_telegram_message(
                    f"⚠️ <b>Exit Signal Triggered</b>\n<b>{symbol}</b> | Score: {score} after {trade['cycles']} cycles."
                )
                log(f"📉 Score drop exit triggered for {symbol}")
                write_log(f"EXIT: {symbol} | Score: {score} | Cycles: {trade['cycles']} | Reason: Score drop")
                log_exit(symbol, score)
                log_trade_result(symbol, tf_scores, "breakeven")
                log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, trade.get("tp2"), "breakeven", score, trade_type, 0, indicator_scores, used_indicators)
                save_active_trades()
                continue

        # ✅ Re-entry
        if should_reenter(symbol, score):
            await handle_reentry(symbol, score)

        # ✅ Score Recovery
        if len(trade["score_history"]) >= 3:
            if trade["score_history"][-3] < get_exit_threshold(trade_type) and score >= get_exit_threshold(trade_type) + 2:
                await send_telegram_message(
                    f"🔁 <b>Score Recovery Alert</b>\n<b>{symbol}</b> | Score rebound to {score}"
                )
                write_log(f"SCORE RECOVERY: {symbol} | Score rebounded to {score}")

        # ✅ Pattern Detection
        last_candles = candles_by_tf['1'][-2:]
        pattern = detect_pattern(last_candles)
        if pattern in ["bearish_engulfing", "inverted_hammer"]:
            await send_telegram_message(
                f"⚠️ <b>Bearish Reversal Pattern</b> on {symbol}\n<i>Pattern: {pattern}</i>"
            )
            write_log(f"BEARISH PATTERN: {symbol} | Pattern: {pattern}")

        # ✅ Volume Drop
        recent_vol = float(candles_by_tf['1'][-1]['volume'])
        avg_vol = get_average_volume(candles_by_tf['1'], window=20)
        if recent_vol < avg_vol * 0.5:
            await send_telegram_message(
                f"⚠️ <b>Volume Drop</b> on {symbol}\nLatest volume below 50% avg."
            )
            write_log(f"VOLUME DROP: {symbol} | Volume {recent_vol:.2f} < 50% avg {avg_vol:.2f}")

        # ✅ Flat Price Action
        closes = [float(c['close']) for c in candles_by_tf['1'][-5:]]
        if max(closes) - min(closes) < float(closes[-1]) * 0.002:
            await send_telegram_message(
                f"😭 <b>Flat Price Action</b> on {symbol}\n<i>Low volatility detected.</i>"
            )
            write_log(f"FLAT PRICE: {symbol} | Low volatility detected")

    save_active_trades()

# Init on startup
load_active_trades()
