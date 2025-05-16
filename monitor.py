import json
import os
import time
import asyncio
from datetime import datetime, timedelta
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log, write_log
from exit_manager import should_trail_stop
from auto_reentry import log_exit, update_exit_cooldowns, should_reenter, handle_reentry
from ai_memory import log_trade_result
from activity_logger import log_trade_to_file
from bybit_api import signed_request, check_order_exists, place_stop_loss, place_stop_loss_with_retry
from error_handler import send_telegram_message
from strategy_performance import log_strategy_result

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

async def update_stop_loss_order(symbol, trade, new_sl_price):
    """Centralized function to update a stop loss order"""
    direction = trade.get("direction", "").lower()
    qty = trade.get("qty")
    old_sl_order_id = trade.get("sl_order_id")
    
    if not direction or not qty:
        log(f"❌ Cannot update SL for {symbol}: Missing trade data", level="ERROR")
        return False
    
    # Cancel existing SL if present
    if old_sl_order_id:
        try:
            cancel_result = await signed_request("POST", "/v5/order/cancel", {
                "category": "linear",
                "symbol": symbol,
                "orderId": old_sl_order_id
            })
            
            if cancel_result.get("retCode") != 0:
                log(f"⚠️ Failed to cancel old SL for {symbol}: {cancel_result.get('retMsg')}", level="WARN")
        except Exception as e:
            log(f"❌ Error cancelling SL order: {e}", level="ERROR")
    
    # Place new SL order with retry
    try:
        sl_resp = await place_stop_loss_with_retry(
            symbol=symbol,
            direction=direction,
            qty=qty,
            sl_price=new_sl_price
        )
        
        if sl_resp.get("retCode") == 0:
            # Update trade record
            trade["sl_order_id"] = sl_resp.get("result", {}).get("orderId")
            trade["trailing_sl"] = new_sl_price
            
            await send_telegram_message(f"🔐 <b>SL Updated</b> for {symbol} | New SL: {new_sl_price}")
            log(f"🔐 SL updated for {symbol} to {new_sl_price}")
            write_log(f"SL UPDATED: {symbol} | New SL: {new_sl_price}")
            save_active_trades()
            return True
        else:
            log(f"❌ Failed to place new SL: {sl_resp.get('retMsg')}", level="ERROR")
            return False
            
    except Exception as e:
        log(f"❌ Error placing new SL order: {e}", level="ERROR")
        return False

async def check_and_restore_sl(symbol, trade):
    """Enhanced function to check for and restore missing stop-loss orders"""
    # Don't try to restore SL if we don't have the necessary information
    if not trade or trade.get("exited") or not trade.get("qty"):
        return
        
    sl_order_id = trade.get("sl_order_id")
    
    # Check if SL exists - First verify we have an ID to check
    sl_exists = False
    if sl_order_id:
        try:
            # Use the check_order_exists function to verify SL is still active
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
                
            # Get current price to ensure SL is placed on the correct side
            try:
                ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
                mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
                
                # Determine SL price with safety check
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
                        sl_price = round(mark_price * (1 - MIN_SL_BUFFER * 2), 6)
                    else:
                        sl_price = round(mark_price * (1 + MIN_SL_BUFFER * 2), 6)
                    log(f"⚠️ No SL price found, using fallback from mark price: {sl_price}")
                
                # Validate the SL price is on the correct side of market price
                if direction == "long" and sl_price >= mark_price:
                    old_sl = sl_price
                    sl_price = round(mark_price * 0.995, 6)  # 0.5% below mark price
                    log(f"⚠️ Adjusted long SL from {old_sl} to {sl_price} (below mark price {mark_price})", level="WARN")
                elif direction == "short" and sl_price <= mark_price:
                    old_sl = sl_price
                    sl_price = round(mark_price * 1.005, 6)  # 0.5% above mark price
                    log(f"⚠️ Adjusted short SL from {old_sl} to {sl_price} (above mark price {mark_price})", level="WARN")
            except Exception as e:
                log(f"❌ Failed to get mark price for SL validation: {e}", level="ERROR")
                # Use a conservative fallback if mark price check fails
                if direction == "long":
                    sl_price = entry_price * 0.95  # 5% below entry as last resort
                else:
                    sl_price = entry_price * 1.05  # 5% above entry as last resort
            
            # Place the new SL order with retry mechanism
            sl_resp = await place_stop_loss_with_retry(symbol, direction, qty, sl_price)
            
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

async def verify_trade_integrity():
    """Verify all trades against exchange data"""
    log("🔍 Starting trade integrity verification...")
    for symbol, trade in list(active_trades.items()):
        if trade.get("exited"):
            continue
            
        try:
            # Get actual position from exchange
            position_resp = await signed_request("GET", "/v5/position/list", {
                "category": "linear",
                "symbol": symbol
            })
            
            if position_resp.get("retCode") != 0:
                log(f"❌ Failed to fetch position for {symbol}: {position_resp.get('retMsg')}", level="ERROR")
                continue
                
            positions = position_resp.get("result", {}).get("list", [])
            
            # Check if position exists
            position_exists = False
            for pos in positions:
                if pos.get("symbol") == symbol and abs(float(pos.get("size", 0))) > 0:
                    position_exists = True
                    break
                    
            if not position_exists:
                log(f"⚠️ Trade {symbol} exists in bot but not on exchange", level="WARN")
                await send_telegram_message(f"⚠️ <b>Integrity Check Failed</b>: {symbol} not found on exchange")
                trade["exited"] = True
                save_active_trades()
                
        except Exception as e:
            log(f"❌ Error in trade integrity check for {symbol}: {e}", level="ERROR")
    
    log("✅ Trade integrity verification complete")

async def debug_stop_loss(symbol):
    """Debugging function to report detailed SL information for a trade"""
    if symbol not in active_trades:
        log(f"⚠️ No active trade found for {symbol}")
        return
        
    trade = active_trades[symbol]
    
    debug_info = {
        "symbol": symbol,
        "direction": trade.get("direction"),
        "entry_price": trade.get("entry_price"),
        "original_sl": trade.get("original_sl"),
        "trailing_sl": trade.get("trailing_sl"),
        "sl_order_id": trade.get("sl_order_id"),
        "tp1_hit": trade.get("tp1_hit"),
        "current_price": None
    }
    
    # Get current price
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
        debug_info["current_price"] = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
    except Exception as e:
        log(f"❌ Error getting current price: {e}")
        
    # Check SL order status
    if trade.get("sl_order_id"):
        try:
            order_resp = await signed_request("GET", "/v5/order/realtime", {
                "category": "linear",
                "symbol": symbol,
                "orderId": trade.get("sl_order_id")
            })
            
            if order_resp.get("retCode") == 0:
                orders = order_resp.get("result", {}).get("list", [])
                if orders:
                    debug_info["sl_order_status"] = orders[0].get("orderStatus")
                    debug_info["sl_order_price"] = orders[0].get("triggerPrice")
                else:
                    debug_info["sl_order_status"] = "Not found"
            else:
                debug_info["sl_order_status"] = f"Error: {order_resp.get('retMsg')}"
                
        except Exception as e:
            debug_info["sl_order_status"] = f"Exception: {str(e)}"
    
    # Log and send detailed report
    log(f"🔍 SL Debug for {symbol}: {debug_info}")
    
    # Format for Telegram
    report = (
        f"🔍 <b>Stop Loss Debug for {symbol}</b>\n"
        f"Direction: {debug_info['direction']}\n"
        f"Entry: {debug_info['entry_price']}\n"
        f"Current: {debug_info['current_price']}\n"
        f"Original SL: {debug_info['original_sl']}\n"
        f"Trailing SL: {debug_info['trailing_sl']}\n"
        f"TP1 Hit: {debug_info['tp1_hit']}\n"
        f"SL Order ID: {debug_info['sl_order_id']}\n"
        f"SL Status: {debug_info.get('sl_order_status', 'Unknown')}\n"
        f"SL Price: {debug_info.get('sl_order_price', 'Unknown')}"
    )
    
    await send_telegram_message(report)
    return debug_info

async def monitor_trades(live_candles):
    update_exit_cooldowns()

    if time.time() - startup_time < 120:
        log("⏳ Grace period active, skipping trade exit checks...")
        return

    for symbol, trade in list(active_trades.items()):
        try:
            if trade.get("exited"):
                continue

            if not trade.get("entry_price") or not trade.get("direction"):
                write_log(f"🚫 Skipping ghost trade: {symbol} — Missing entry data")
                continue

            if symbol not in live_candles:
                continue

            # Get candles for all timeframes
            try:
                candles_by_tf = {
                    tf: list(live_candles[symbol][str(tf)]) for tf in ['1', '3', '5', '15', '30', '60', '240']
                    if str(tf) in live_candles[symbol]
                }
                
                if not candles_by_tf or not candles_by_tf.get('1'):
                    continue
                    
                # Current price from most recent 1m candle
                current_price = float(candles_by_tf['1'][-1]['close'])
                
            except Exception as e:
                log(f"⚠️ Error fetching candles for {symbol}: {e}", level="WARN")
                continue
                
            # Core trade variables
            trade_type = trade.get("trade_type")
            direction = trade.get("direction")
            entry_price = trade.get("entry_price")
            trailing_pct = trade.get("trailing_pct")
            
            # 1. Always check and restore SL first
            await check_and_restore_sl(symbol, trade)
            
            # 2. Calculate score for exit decisions
            try:
                score, tf_scores, _, indicator_scores, used_list = score_symbol(symbol, candles_by_tf)
                trade["score_history"].append(score)
                trade["cycles"] += 1
            except Exception as e:
                log(f"❌ Error scoring {symbol}: {e}", level="ERROR")
                continue
            
            # 3. Handle trailing stop if TP1 hit
            if trade.get("tp1_hit") and trailing_pct:
                try:
                    current_trailing_sl = trade.get("trailing_sl")
                    new_sl = should_trail_stop(
                        symbol=symbol,
                        entry_price=entry_price,
                        current_price=current_price,
                        direction=direction.lower(),
                        candles=candles_by_tf.get('1', []),
                        trigger_pct=trailing_pct * 2,
                        trail_pct=trailing_pct,
                        current_trailing_sl=current_trailing_sl
                    )
                    
                    if new_sl and (current_trailing_sl is None or
                                  (direction.lower() == "long" and new_sl > current_trailing_sl) or
                                  (direction.lower() == "short" and new_sl < current_trailing_sl)):
                        
                        # Update the trailing stop using the centralized function
                        await update_stop_loss_order(symbol, trade, new_sl)
                        
                except Exception as e:
                    log(f"❌ Error updating trailing SL for {symbol}: {e}", level="ERROR")

            # 4. Trail SL hit check
            if trade.get("tp1_hit") and trade.get("trailing_sl"):
                trailing_sl = trade["trailing_sl"]
                if (direction.lower() == "long" and current_price <= trailing_sl) or (direction.lower() == "short" and current_price >= trailing_sl):
                    trade["exited"] = True
                    await send_telegram_message(f"⛔ <b>Trailing SL Hit</b> on {symbol} at {current_price:.4f}")
                    write_log(f"TRAILING SL HIT: {symbol} | Hit at: {current_price:.4f}")
                    log_trade_result(symbol, tf_scores, "breakeven")
                    log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, current_price, "breakeven", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                    strategy = "core_strategy"
                    if tf_scores.get("mean_reversion"):
                        strategy = "mean_reversion"
                    elif tf_scores.get("breakout_sniper"):
                        strategy = "breakout_sniper"

                    profit_pct = ((current_price - entry_price) / entry_price) * 100 if direction == "long" else ((entry_price - current_price) / entry_price) * 100
                    log_strategy_result(strategy, "win", round(profit_pct, 2))
                    save_active_trades()
                    continue

            # 5. TP1 hit check
            if not trade.get("tp1_hit") and direction and entry_price:
                tp1_level = entry_price * (1.018 if direction.lower() == "long" else 0.982)
                if (direction.lower() == "long" and current_price >= tp1_level) or (direction.lower() == "short" and current_price <= tp1_level):
                    trade["tp1_hit"] = True
                    trade["break_even_triggered"] = True
                    trade["tp1_price"] = current_price
                    
                    # Set trailing SL to entry price initially (break-even)
                    new_sl = entry_price
                    
                    # Update SL order to break-even using centralized function
                    await update_stop_loss_order(symbol, trade, new_sl)
                    
                    await send_telegram_message(f"🌟 <b>TP1 Hit</b> on <b>{symbol}</b> — Smart Trailing SL Activated at Break-even")
                    write_log(f"TP1 HIT: {symbol} | SL moved to break-even: {entry_price}")
                    log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), entry_price, None, "tp1", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                    strategy = "core_strategy"
                    if tf_scores.get("mean_reversion"):
                        strategy = "mean_reversion"
                    elif tf_scores.get("breakout_sniper"):
                        strategy = "breakout_sniper"
                    log_strategy_result(strategy, "breakeven", 0)
                    save_active_trades()

            # 6. Original SL hit check
            if not trade.get("tp1_hit") and trade.get("original_sl"):
                sl_price = trade["original_sl"]
                if (direction.lower() == "long" and current_price <= sl_price) or (direction.lower() == "short" and current_price >= sl_price):
                    trade["exited"] = True
                    await send_telegram_message(f"❌ <b>SL Hit</b> on <b>{symbol}</b>")
                    write_log(f"SL HIT: {symbol} | SL: {sl_price} | Price: {current_price}")
                    log_exit(symbol, score)
                    log_trade_result(symbol, tf_scores, "loss")
                    log_trade_to_file(symbol, direction, entry_price, sl_price, None, current_price, "loss", score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                    strategy = "core_strategy"
                    if tf_scores.get("mean_reversion"):
                        strategy = "mean_reversion"
                    elif tf_scores.get("breakout_sniper"):
                         strategy = "breakout_sniper"
                    log_strategy_result(strategy, "loss", -100)
                    save_active_trades()
                    continue

            # 7. Post-TP1 pump detection
            if trade.get("tp1_hit") and trade.get("tp1_price") and not trade.get("smart_pump_alerted"):
                recent_high = max(float(candle["high"]) for candle in candles_by_tf['1'][-TP1_PUMP_CANDLE_LOOKAHEAD:])
                pump_move = ((recent_high - trade["tp1_price"]) / trade["tp1_price"]) * 100
                if pump_move >= TP1_PUMP_THRESHOLD:
                    trade["smart_pump_alerted"] = True
                    await send_telegram_message(f"🚀 <b>Smart Pump After TP1</b> on {symbol}: +{pump_move:.2f}% detected after TP1")
                    write_log(f"SMART PUMP AFTER TP1: {symbol} | +{pump_move:.2f}% beyond TP1")
                    save_active_trades()
                    
        except Exception as e:
            log(f"❌ Unhandled error monitoring {symbol}: {e}", level="ERROR")
            write_log(f"MONITOR ERROR: {symbol} | {str(e)}", level="ERROR")

    save_active_trades()

# Periodic SL verification task
async def verify_all_stop_losses(frequency_minutes=15):
    """Periodically verify all stop losses are still active"""
    while True:
        try:
            log("🔍 Starting periodic SL verification cycle")
            trades_verified = 0
            
            for symbol, trade in active_trades.items():
                if trade.get("exited"):
                    continue
                
                # Check if SL order still exists
                if trade.get("sl_order_id"):
                    sl_exists = await check_order_exists(trade["sl_order_id"], symbol)
                    if not sl_exists:
                        log(f"⚠️ SL order missing for {symbol} - restoring", level="WARN")
                        await check_and_restore_sl(symbol, trade)
                else:
                    log(f"⚠️ No SL order ID for {symbol} - setting new SL", level="WARN")
                    await check_and_restore_sl(symbol, trade)
                
                trades_verified += 1
                
                # Sleep briefly between symbols to avoid rate limits
                await asyncio.sleep(1)
                
            log(f"✅ Completed SL verification cycle: verified {trades_verified} trades")
            
            # Also verify trade integrity while we're at it
            await verify_trade_integrity()
            
        except Exception as e:
            log(f"❌ Error in periodic SL verification: {e}", level="ERROR")
            
        # Wait for next cycle
        await asyncio.sleep(frequency_minutes * 60)

# Emergency exit monitoring for extreme market conditions
async def emergency_exit_monitor():
    """Monitor for extreme market conditions and exit if necessary"""
    while True:
        try:
            for symbol, trade in active_trades.items():
                if trade.get("exited"):
                    continue
                
                entry_price = trade.get("entry_price")
                direction = trade.get("direction", "").lower()
                
                if not entry_price or not direction:
                    continue
                    
                try:
                    # Get current price
                    ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
                    current_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
                    
                    # Calculate move percentage
                    move_pct = ((current_price - entry_price) / entry_price) * 100
                    move_pct = move_pct if direction == "long" else -move_pct
                    
                    # Exit position if extremely adverse move (over 15% against position)
                    if move_pct < -15:  # 15% adverse move
                        await send_telegram_message(f"🚨 <b>EMERGENCY EXIT</b> for {symbol} (move: {move_pct:.2f}%)")
                        
                        # Execute emergency market exit
                        from bybit_api import place_market_order
                        side = "Sell" if direction == "long" else "Buy"
                        await place_market_order(
                            symbol=symbol,
                            side=side,
                            qty=trade.get("qty"),
                            market_type="linear",
                            reduce_only=True
                        )
                        
                        trade["exited"] = True
                        save_active_trades()
                        log(f"🚨 Emergency exit executed for {symbol} at {current_price}", level="ALERT")
                        
                except Exception as e:
                    log(f"❌ Error in emergency monitor for {symbol}: {e}", level="ERROR")
                
        except Exception as e:
            log(f"❌ Error in emergency exit monitor: {e}", level="ERROR")
            
        # Check every 30 seconds
        await asyncio.sleep(30)
