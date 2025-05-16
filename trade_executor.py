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
from bybit_api import signed_request, check_order_exists, place_stop_loss

PERSIST_PATH = "monitor_active_trades.json"
active_trades = {}
startup_time = time.time()

POST_EXIT_CANDLE_COUNT = 5
TP1_PUMP_CANDLE_LOOKAHEAD = 4
TP1_PUMP_THRESHOLD = 1.2

MIN_SL_BUFFER = 0.0025  # 0.25% safety margin

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
        "tp1_partial_exit": False,
        "sl_order_id": sl_order_id,
        "qty": qty,
        "break_even_triggered": False,
        "tp1_price": None,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_active_trades()

def remove_trade(symbol):
    if symbol in active_trades:
        del active_trades[symbol]
        save_active_trades()

async def check_and_restore_sl(symbol, trade):
    """Enhanced function to check for and restore missing stop-loss orders"""
    from telegram_bot import send_telegram_message
    
    # Don't try to restore SL if we don't have the necessary information
    if not trade or trade.get("exited") or not trade.get("qty"):
        return
        
    sl_order_id = trade.get("sl_order_id")
    
    # Check if SL exists - First verify we have an ID to check
    sl_exists = False
    if sl_order_id:
        try:
            # Use the new check_order_exists function from bybit_api
            sl_exists = await check_order_exists(sl_order_id, symbol)
            log(f"🔍 SL order check for {symbol}: {'Exists' if sl_exists else 'Missing'}")
        except Exception as e:
            log(f"❌ Error checking SL order: {e}", level="ERROR")
    
    # If SL doesn't exist or we don't have an SL order ID, recreate it
    if not sl_exists:
        try:
            direction = trade.get("direction", "").lower()
            qty = trade.get("qty")
            
            # Try to use the trailing SL if available, otherwise use original SL or fallback to entry price with buffer
            entry_price = trade.get("entry_price")
            if not entry_price:
                log(f"❌ Cannot restore SL for {symbol}: No entry price available", level="ERROR")
                return
                
            sl_price = None
            if trade.get("trailing_sl"):
                sl_price = trade.get("trailing_sl")
                log(f"🔄 Using trailing SL price: {sl_price}")
            elif trade.get("original_sl"):
                sl_price = trade.get("original_sl") 
                log(f"🔄 Using original SL price: {sl_price}")
            else:
                # Fallback: Calculate a safety SL from entry price
                if direction == "long":
                    sl_price = round(entry_price * (1 - MIN_SL_BUFFER * 2), 6)
                else:
                    sl_price = round(entry_price * (1 + MIN_SL_BUFFER * 2), 6)
                log(f"⚠️ No SL price found, using fallback from entry: {sl_price}")
            
            # Place the new SL order using our improved function
            sl_resp = await place_stop_loss(symbol, direction, qty, sl_price)
            
            if sl_resp.get("retCode") == 0:
                new_sl_order_id = sl_resp.get("result", {}).get("orderId")
                trade["sl_order_id"] = new_sl_order_id
                await send_telegram_message(f"🛡️ <b>SL Restored</b> for {symbol} at {sl_price}")
                write_log(f"SL RESTORED: {symbol} | Price: {sl_price} | Order ID: {new_sl_order_id}")
                log(f"✅ SL restored for {symbol} at {sl_price}")
                save_active_trades()
            else:
                log(f"❌ Failed to restore SL for {symbol}: {sl_resp.get('retMsg')}", level="ERROR")
                await send_telegram_message(f"⚠️ <b>SL Restoration Failed</b> for {symbol}: {sl_resp.get('retMsg')}")
        except Exception as e:
            log(f"❌ Error restoring SL for {symbol}: {e}", level="ERROR")
            write_log(f"ERROR RESTORING SL: {symbol} | {str(e)}")

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

        score, tf_scores, _, _, used_list = score_symbol(symbol, candles_by_tf)
        trade["score_history"].append(score)
        trade["cycles"] += 1

        current_price = float(candles_by_tf['1'][-1]['close'])
        trailing_pct = trade.get("trailing_pct")

        # Check and restore SL first - ALWAYS do this before any other logic
        await check_and_restore_sl(symbol, trade)

        if trade.get("tp1_hit") and trailing_pct:
           current_trailing_sl = trade.get("trailing_sl")
           new_sl = should_trail_stop(
               symbol=symbol,
               entry_price=entry_price,
               current_price=current_price,
               direction=direction.lower(),
               candles=candles_by_tf['1'],
               trigger_pct=trailing_pct * 2,
               trail_pct=trailing_pct,
               current_trailing_sl=current_trailing_sl
           )
           if new_sl and (current_trailing_sl is None or
                          (direction.lower() == "long" and new_sl > current_trailing_sl) or
                          (direction.lower() == "short" and new_sl < current_trailing_sl)):
               trade["trailing_sl"] = new_sl
               
               # Update the actual SL order in Bybit when we move the trailing SL
               try:
                   # Cancel existing SL
                   if trade.get("sl_order_id"):
                       await signed_request("POST", "/v5/order/cancel", {
                           "category": "linear",
                           "symbol": symbol,
                           "orderId": trade["sl_order_id"]
                       })
                   
                   # Place new SL
                   sl_resp = await place_stop_loss(
                       symbol=symbol,
                       direction=direction.lower(),
                       qty=trade.get("qty"),
                       sl_price=new_sl
                   )
                   
                   if sl_resp.get("retCode") == 0:
                       trade["sl_order_id"] = sl_resp.get("result", {}).get("orderId")
                       await send_telegram_message(f"🔐 <b>Trailing SL Updated</b> for {symbol} | New SL: {new_sl}")
                       log(f"🔐 Smart SL updated for {symbol} to {new_sl}")
                       write_log(f"TRAILING SL UPDATED: {symbol} | New SL: {new_sl} | Price: {current_price}")
                       save_active_trades()
                   else:
                       log(f"❌ Failed to update trailing SL: {sl_resp.get('retMsg')}", level="ERROR")
               except Exception as e:
                   log(f"❌ Error updating trailing SL: {e}", level="ERROR")

        # Trail SL hit check
        if trade.get("tp1_hit") and trade.get("trailing_sl"):
            trailing_sl = trade["trailing_sl"]
            if (direction.lower() == "long" and current_price <= trailing_sl) or (direction.lower() == "short" and current_price >= trailing_sl):
                trade["exited"] = True
                await send_telegram_message(f"⛔ <b>Trailing SL Hit</b> on {symbol} at {current_price:.4f}")
                write_log(f"TRAILING SL HIT: {symbol} | Hit at: {current_price:.4f}")
                log_trade_result(symbol, tf_scores, "breakeven")
                log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, current_price, "breakeven", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                save_active_trades()
                continue

        # TP1 hit check
        if not trade.get("tp1_hit") and direction and entry_price:
            tp1_level = entry_price * (1.018 if direction.lower() == "long" else 0.982)
            if (direction.lower() == "long" and current_price >= tp1_level) or (direction.lower() == "short" and current_price <= tp1_level):
                trade["tp1_hit"] = True
                trade["break_even_triggered"] = True
                trade["tp1_price"] = current_price
                trade["trailing_sl"] = entry_price
                
                # Update the actual SL order when TP1 is hit
                try:
                    # Cancel existing SL
                    if trade.get("sl_order_id"):
                        await signed_request("POST", "/v5/order/cancel", {
                            "category": "linear",
                            "symbol": symbol,
                            "orderId": trade["sl_order_id"]
                        })
                    
                    # Place new break-even SL
                    sl_resp = await place_stop_loss(
                        symbol=symbol,
                        direction=direction.lower(),
                        qty=trade.get("qty"),
                        sl_price=entry_price
                    )
                    
                    if sl_resp.get("retCode") == 0:
                        trade["sl_order_id"] = sl_resp.get("result", {}).get("orderId")
                    else:
                        log(f"❌ Failed to set break-even SL: {sl_resp.get('retMsg')}", level="ERROR")
                except Exception as e:
                    log(f"❌ Error setting break-even SL: {e}", level="ERROR")
                
                await send_telegram_message(f"🌟 <b>TP1 Hit</b> on <b>{symbol}</b> — Smart Trailing SL Activated at Break-even")
                write_log(f"TP1 HIT: {symbol} | SL moved to break-even: {entry_price}")
                log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), entry_price, None, "tp1", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                save_active_trades()

        # Original SL hit check
        if not trade.get("tp1_hit") and trade.get("original_sl"):
            sl_price = trade["original_sl"]
            if (direction.lower() == "long" and current_price <= sl_price) or (direction.lower() == "short" and current_price >= sl_price):
                trade["exited"] = True
                await send_telegram_message(f"❌ <b>SL Hit</b> on <b>{symbol}</b>")
                write_log(f"SL HIT: {symbol} | SL: {sl_price} | Price: {current_price}")
                log_exit(symbol, score)
                log_trade_result(symbol, tf_scores, "loss")
                log_trade_to_file(symbol, direction, entry_price, sl_price, None, current_price, "loss", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                save_active_trades()
                continue

        # Post-TP1 pump detection
        if trade.get("tp1_hit") and trade.get("tp1_price") and not trade.get("smart_pump_alerted"):
            recent_high = max(float(candle["high"]) for candle in candles_by_tf['1'][-TP1_PUMP_CANDLE_LOOKAHEAD:])
            pump_move = ((recent_high - trade["tp1_price"]) / trade["tp1_price"]) * 100
            if pump_move >= TP1_PUMP_THRESHOLD:
                trade["smart_pump_alerted"] = True
                await send_telegram_message(f"🚀 <b>Smart Pump After TP1</b> on {symbol}: +{pump_move:.2f}% detected after TP1")
                write_log(f"SMART PUMP AFTER TP1: {symbol} | +{pump_move:.2f}% beyond TP1")
                save_active_trades()

    save_active_trades()
