import json
import os
import time
from datetime import datetime, timedelta
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log, write_log
from exit_manager import should_trail_stop
from auto_reentry import log_exit, update_exit_cooldowns, should_reenter, handle_reentry
from ai_memory import log_trade_result
from activity_logger import log_trade_to_file
from bybit_api import signed_request

PERSIST_PATH = "monitor_active_trades.json"
active_trades = {}
startup_time = time.time()


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
            now = datetime.utcnow()
            with open(PERSIST_PATH, 'r') as f:
                loaded_trades = json.load(f)
            for symbol, trade in loaded_trades.items():
                trade_time = trade.get("timestamp")
                if trade.get("exited"):
                    continue
                if trade_time:
                    try:
                        trade_dt = datetime.strptime(trade_time, "%Y-%m-%d %H:%M:%S")
                        if now - trade_dt > timedelta(hours=24):
                            continue
                    except:
                        continue
                trade["exited"] = False
                active_trades[symbol] = trade
            log(f"🔁 Loaded {len(active_trades)} active trades from disk")
        except Exception as e:
            log(f"❌ Failed to load active trades: {e}", level="ERROR")


def track_active_trade(symbol, trade_type, initial_score, entry_price=None, direction=None, trailing_pct=None, tp2=None, sl=None, sl_order_id=None, qty=None):
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
        "tp2": tp2,
        "tp1_partial_exit": False,
        "sl_order_id": sl_order_id,
        "qty": qty,
        "break_even_triggered": False,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_active_trades()


def remove_trade(symbol):
    if symbol in active_trades:
        del active_trades[symbol]
        save_active_trades()


async def check_and_restore_sl(symbol, trade):
    from telegram_bot import send_telegram_message
    if not trade.get("sl_order_id"):
        return
    try:
        response = await signed_request("GET", "/v5/order/realtime", {
            "symbol": symbol,
            "category": "linear",
        })
        active_orders = response.get("result", {}).get("list", [])
        sl_order_id = trade.get("sl_order_id")
        sl_exists = any(order.get("orderId") == sl_order_id for order in active_orders)
        if not sl_exists:
            direction = trade.get("direction")
            qty = trade.get("qty")
            sl = trade.get("original_sl")
            side = "Sell" if direction == "Long" else "Buy"
            trigger_direction = 1 if direction == "Long" else 2
            sl_resp = await signed_request("POST", "/v5/order/create", {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "triggerPrice": str(sl),
                "triggerDirection": trigger_direction,
                "triggerBy": "MarkPrice",
                "qty": str(qty),
                "reduceOnly": True,
                "timeInForce": "GTC",
                "orderFilter": "Stop"
            })
            await send_telegram_message(f"⚠️ <b>SL Replaced</b> for {symbol} (was missing). New SL order: {sl_resp.get('result', {}).get('orderId')}")
            write_log(f"SL RESTORED: {symbol} | Order ID: {sl_resp.get('result', {}).get('orderId')}")
            log(f"✅ SL replaced for {symbol} (MarkPrice fallback)")
            trade["sl_order_id"] = sl_resp.get("result", {}).get("orderId")
            save_active_trades()
    except Exception as e:
        log(f"❌ Error checking SL for {symbol}: {e}", level="ERROR")


async def monitor_trades(live_candles):
    from telegram_bot import send_telegram_message
    update_exit_cooldowns()

    if time.time() - startup_time < 120:
        log("⏳ Grace period active, skipping trade exit checks...")
        return

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

        score, tf_scores, _, _, _ = score_symbol(symbol, candles_by_tf)
        trade["score_history"].append(score)
        trade["cycles"] += 1

        current_price = float(candles_by_tf['1'][-1]['close'])
        trailing_pct = trade.get("trailing_pct")

        await check_and_restore_sl(symbol, trade)

        # ✅ SL Hit
        if trade.get("original_sl") and not trade.get("tp1_hit"):
            sl_price = trade["original_sl"]
            if (direction == "Long" and current_price <= sl_price) or (direction == "Short" and current_price >= sl_price):
                trade["exited"] = True
                await send_telegram_message(
                    f"❌ <b>SL Hit</b> on <b>{symbol}</b>\nSL {sl_price:.4f} reached at price {current_price:.4f}"
                )
                write_log(f"SL HIT: {symbol} | SL: {sl_price} | Price: {current_price}")
                log_exit(symbol, score)
                log_trade_result(symbol, tf_scores, "loss")
                log_trade_to_file(symbol, direction, entry_price, sl_price, None, None, "loss", score, trade_type, 0)
                save_active_trades()
                continue

        # ✅ TP1 Hit (force run before TP2 check)
        if not trade.get("tp1_hit") and direction and entry_price:
            tp1_level = entry_price * (1.018 if direction == "Long" else 0.982)
            if (direction == "Long" and current_price >= tp1_level) or (direction == "Short" and current_price <= tp1_level):
                trade["tp1_hit"] = True
                trade["break_even_triggered"] = True
                new_sl = entry_price
                trade["trailing_sl"] = new_sl
                await send_telegram_message(
                    f"🌟 <b>TP1 Hit</b> on <b>{symbol}</b>\n<b>Break-even SL activated</b> at {new_sl:.4f}"
                )
                write_log(f"TP1 HIT: {symbol} | Break-even SL set at {new_sl}")

        # ✅ Partial Exit Log (only if TP1 was hit)
        if trade.get("tp1_hit") and not trade.get("tp1_partial_exit"):
            trade["tp1_partial_exit"] = True
            await send_telegram_message(
                f"📤 <b>Partial TP1 Exit</b> on {symbol} | Booked partial profits. Holding for TP2."
            )
            write_log(f"TP1 PARTIAL EXIT: {symbol} | Price: {current_price}")

        # ✅ TP2 Hit
        if trade.get("tp2") and not trade.get("tp2_hit"):
            tp2 = trade["tp2"]
            if (direction == "Long" and current_price >= tp2) or (direction == "Short" and current_price <= tp2):
                trade["tp2_hit"] = True
                trade["exited"] = True
                await send_telegram_message(
                    f"🏁 <b>TP2 Target Hit</b> on <b>{symbol}</b>\nTarget: {tp2:.4f} | Current: {current_price:.4f}"
                )
                write_log(f"TP2 HIT: {symbol} | Reached: {current_price}")
                log_trade_result(symbol, tf_scores, "win")
                log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, tp2, "win", score, trade_type, 0)
                save_active_trades()
                continue

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

        # ✅ Trailing SL Hit
        if trade.get("tp1_hit") and trade.get("trailing_sl"):
            trailing_sl = trade["trailing_sl"]
            if (direction == "Long" and current_price <= trailing_sl) or (direction == "Short" and current_price >= trailing_sl):
                trade["exited"] = True
                await send_telegram_message(
                    f"⛔ <b>Trailing SL Hit</b> on {symbol} at {current_price:.4f}"
                )
                write_log(f"TRAILING SL HIT: {symbol} | Hit at: {current_price:.4f}")
                log_trade_result(symbol, tf_scores, "breakeven")
                log_trade_to_file(symbol, direction, entry_price, trailing_sl, None, trade.get("tp2"), "breakeven", score, trade_type, 0)
                save_active_trades()
                continue

        if should_reenter(symbol, score):
            await handle_reentry(symbol, score)

    save_active_trades()


load_active_trades()
