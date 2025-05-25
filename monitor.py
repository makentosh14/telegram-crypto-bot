# monitor.py - Enhanced with improved TP1 and trailing stop functionality

import json
import os
import time
import asyncio
import traceback
from datetime import datetime, timedelta
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log, write_log
from exit_manager import should_trail_stop, adjust_profit_protection, should_exit_by_time, evaluate_score_exit, detect_momentum_surge, calculate_exit_tranches
from auto_reentry import log_exit, update_exit_cooldowns, should_reenter, handle_reentry
from ai_memory import log_trade_result
from activity_logger import log_trade_to_file
from bybit_api import signed_request, check_order_exists, place_stop_loss, place_stop_loss_with_retry, place_market_order
from error_handler import send_telegram_message
from strategy_performance import log_strategy_result
from exit_manager import should_trail_stop, adjust_profit_protection, should_exit_by_time, detect_momentum_surge, calculate_exit_tranches
from sl_tp_utils import evaluate_score_exit


# FIXED PERCENTAGES for SL/TP - Add this after the imports
FIXED_PERCENTAGES = {
    "Scalp": {
        "tp1_pct": 1.2,      # +1.2% take profit
        "sl_pct": 0.8,       # -0.8% stop loss
        "trailing_pct": 0.4  # 0.4% trailing stop
    },
    "Intraday": {
        "tp1_pct": 2.0,      # +2.0% take profit
        "sl_pct": 1.0,       # -1.0% stop loss
        "trailing_pct": 1.0  # 1.0% trailing stop
    },
    "Swing": {
        "tp1_pct": 5.0,      # Keep existing for swing
        "sl_pct": 2.0,       # Keep existing for swing
        "trailing_pct": 1.5  # Keep existing for swing
    }
}


# NEW IMPORTS for enhanced functionality
from enhanced_exit import (
    detect_tp1_hit,
    calculate_smart_trailing_stop,
    should_trail_stop_enhanced,
    execute_partial_exit_with_retry
)
from trade_verification import verify_position_and_orders

PERSIST_PATH = "monitor_active_trades.json"
active_trades = {}
startup_time = time.time()

log(f"🔍 monitor.py loaded - active_trades id: {id(active_trades)}")

POST_EXIT_CANDLE_COUNT = 5
TP1_PUMP_CANDLE_LOOKAHEAD = 8  # Increased from 4 to look further ahead for pumps
TP1_PUMP_THRESHOLD = 1.0  # Lower threshold to detect pumps earlier (from 1.2% to 1.0%)

MIN_SL_BUFFER = 0.0025  # 0.25% safety margin

# NEW LOGGING FUNCTIONS for enhanced tracking
def log_tp1_event(symbol, event_type, data):
    """Enhanced TP1 logging function"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] TP1_{event_type}: {symbol} | {json.dumps(data)}"
    log(msg, level="INFO")
    write_log(msg)

def log_trailing_event(symbol, event_type, data):
    """Enhanced trailing stop logging function"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] TRAILING_{event_type}: {symbol} | {json.dumps(data)}"
    log(msg, level="INFO")
    write_log(msg)

def save_active_trades():
    """Save active trades data with backup and atomic write protections"""
    try:
        log(f"💾 Saving {len(active_trades)} active trades to file...")
        
        # Create a copy of the trades dictionary to avoid modifying the original
        trades_to_save = {}
        
        for symbol, trade in active_trades.items():
            # Create a copy of the trade dictionary
            trade_copy = dict(trade)
            
            # Convert any datetime objects to string format
            for key, value in trade_copy.items():
                if isinstance(value, datetime):
                    trade_copy[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                    
            trades_to_save[symbol] = trade_copy

        log(f"📋 Trades to save: {list(trades_to_save.keys())}")
        
        # Use a temporary file for atomic writes
        temp_path = f"{PERSIST_PATH}.temp"
        
        # First write to a temporary file
        with open(temp_path, 'w') as f:
            json.dump(trades_to_save, f, indent=2)
            
        # Then rename the temp file to the actual file (atomic operation)
        import os
        if os.path.exists(PERSIST_PATH):
            os.replace(temp_path, PERSIST_PATH)
        else:
            os.rename(temp_path, PERSIST_PATH)

        log(f"✅ Successfully saved {len(trades_to_save)} trades")
            
    except Exception as e:
        log(f"❌ Failed to save trades: {e}", level="ERROR")

def load_active_trades():
    """Load active trades with fallback to backup file if main file is corrupted"""
    global active_trades
    
    backup_path = f"{PERSIST_PATH}.backup"
    
    def try_load_file(file_path):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    loaded_trades = json.load(f)
                return loaded_trades, True
            return {}, False
        except json.JSONDecodeError as je:
            log(f"⚠️ JSON error in {file_path}: {je}", level="ERROR")
            return {}, False
        except Exception as e:
            log(f"❌ Error loading {file_path}: {e}", level="ERROR")
            return {}, False
    
    # Try to load the main file
    loaded_trades, success = try_load_file(PERSIST_PATH)
    
    # If main file failed, try the backup
    if not success:
        log(f"⚠️ Primary trades file corrupted, trying backup...", level="WARN")
        loaded_trades, success = try_load_file(backup_path)
        
        if success:
            log(f"✅ Successfully loaded from backup file", level="INFO")
            # Save the recovered data back to the main file
            with open(PERSIST_PATH, 'w') as f:
                json.dump(loaded_trades, f, indent=2)
        else:
            log(f"❌ Both primary and backup files corrupted. Starting with empty trades.", level="ERROR")
            loaded_trades = {}
    
    # Process loaded trades, filtering out exited or old trades
    now = datetime.utcnow()
    active_trades = {}
    loaded_count = 0
    
    for symbol, trade in loaded_trades.items():
        # Skip exited trades
        if trade.get("exited"):
            continue
            
        # Check if trade is too old
        trade_time = trade.get("timestamp")
        if trade_time:
            try:
                trade_dt = datetime.strptime(trade_time, "%Y-%m-%d %H:%M:%S")
                if now - trade_dt > timedelta(hours=24):
                    continue
            except:
                continue
                
        # Mark as not exited (in case it was somehow set to true but still in file)
        trade["exited"] = False
        active_trades[symbol] = trade
        loaded_count += 1
    
    log(f"🔁 Loaded {loaded_count} active trades")
    
    # Create a backup of the successfully loaded file
    if loaded_count > 0:
        try:
            import shutil
            shutil.copy2(PERSIST_PATH, backup_path)
            log(f"✅ Created backup of active trades file")
        except Exception as e:
            log(f"⚠️ Failed to create backup: {e}", level="WARN")

def backup_trades_file():
    """Create a timestamped backup of the trades file"""
    if not os.path.exists(PERSIST_PATH):
        return
        
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{PERSIST_PATH}.{timestamp}"
        import shutil
        shutil.copy2(PERSIST_PATH, backup_path)
        
        # Keep only the 5 most recent backups
        import glob
        backups = glob.glob(f"{PERSIST_PATH}.*")
        backups.sort(reverse=True)
        
        for old_backup in backups[5:]:  # Delete all but the 5 newest
            os.remove(old_backup)
            
        log(f"✅ Created backup of trades file: {backup_path}")
    except Exception as e:
        log(f"⚠️ Failed to create backup: {e}", level="WARN")

async def periodic_backups():
    """Run backups every hour"""
    while True:
        try:
            backup_trades_file()
        except Exception as e:
            log(f"❌ Error in backup task: {e}", level="ERROR")
        
        # Wait for an hour
        await asyncio.sleep(3600)  # 1 hour

def track_active_trade(symbol, trade_type, initial_score, entry_price=None, direction=None, 
                      trailing_pct=None, tp1_target=None, tp1_pct=None, tp2=None, sl=None, 
                      sl_order_id=None, qty=None, exit_tranches=None, has_pump_potential=False):
    """
    Track a new active trade with enhanced exit strategy parameters
    """
    global active_trades  # Ensure we're using the global variable
    
    log(f"🔍 TRACK_ACTIVE_TRADE called for {symbol}")
    log(f"   Entry: {entry_price}, Direction: {direction}, Qty: {qty}")
    log(f"   SL Order ID: {sl_order_id}")
    
    # Validate required parameters
    if not entry_price or not direction or not qty:
        log(f"❌ TRACK_ACTIVE_TRADE: Missing required data for {symbol}", level="ERROR")
        log(f"   entry_price={entry_price}, direction={direction}, qty={qty}", level="ERROR")
        return
                          
    if not exit_tranches and qty:
        exit_tranches = calculate_exit_tranches(symbol, qty)

    # Get fixed percentages for this trade type
    fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
    if trade_type in ["Scalp", "Intraday"]:
        trailing_pct = fixed_params["trailing_pct"]
        if tp1_pct is None:
            tp1_pct = fixed_params["tp1_pct"]
                                                
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
        "tp1_target": tp1_target,      # Store the actual TP1 price target
        "tp1_pct": tp1_pct,           # Store the TP1 percentage used
        "tp1_partial_exit": False,
        "tp2_hit": False,
        "tp2_exit_executed": False,
        "sl_order_id": sl_order_id,
        "qty": qty,
        "break_even_triggered": False,
        "tp1_price": None,  # This will be set when TP1 is actually hit
        "tp2_price": tp2,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "exit_tranches": exit_tranches or [],
        "smart_pump_alerted": False,
        "in_momentum": False,
        "has_pump_potential": has_pump_potential,
        "let_winners_run": True,
        "exit_timed": False,
        "exit_score": False,
        "tp1_hit_cycle": 0,
        "max_score": initial_score,
        "entry_time": datetime.utcnow(),
        "last_score_update": datetime.utcnow()
    }

    log(f"✅ Trade added to active_trades for {symbol}")
    log(f"📊 Active trades count: {len(active_trades)}")
    log(f"📋 All active symbols: {list(active_trades.keys())}")

    if tp1_target:
        log(f"🎯 TP1 target stored for {symbol}: {tp1_target} ({tp1_pct:.2f}%)")
    
    # Log pump potential if detected
    if has_pump_potential:
        log(f"🚀 Trade for {symbol} flagged with pump potential - using optimized exit strategy")
        
    # If exit tranches are provided, log them
    if exit_tranches:
        log(f"📊 Exit tranches for {symbol}: {exit_tranches}")
        
    log(f"📝 Active trades count before save: {len(active_trades)}")
    save_active_trades()
    log(f"✅ Trade tracked and saved for {symbol}")

def remove_trade(symbol):
    if symbol in active_trades:
        del active_trades[symbol]
        save_active_trades()

async def execute_partial_exit(symbol, trade, exit_percentage):
    """Execute a partial exit for the given percentage of position"""
    try:
        direction = trade.get("direction", "").lower()
        total_qty = trade.get("qty")
        
        if not direction or not total_qty or total_qty <= 0:
            log(f"❌ Cannot execute partial exit for {symbol}: Invalid trade data", level="ERROR")
            return False
        
        # Calculate exit quantity
        exit_qty = total_qty * (exit_percentage / 100)
        
        # Ensure exit quantity meets minimum requirements
        from symbol_info import round_qty, symbol_precisions
        min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
        
        # Add debug logging for minimum qty
        log(f"🔍 Partial exit for {symbol}: Min qty={min_qty}, Calculated qty={exit_qty}")
        
        exit_qty = max(round_qty(symbol, exit_qty), min_qty)
        
        # Don't exit more than we have
        exit_qty = min(exit_qty, total_qty)
        
        # IMPORTANT: Check if exit quantity is below minimum
        if exit_qty < min_qty:
            log(f"⚠️ Exit quantity {exit_qty} below minimum {min_qty} for {symbol}. Aborting partial exit.", level="WARN")
            return False
        
        # Execute market order
        side = "Sell" if direction == "long" else "Buy"
        
        log(f"🔍 Executing partial exit for {symbol}: {exit_qty} {side} (min_qty={min_qty})")
        
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=str(exit_qty),
            market_type="linear",
            reduce_only=True
        )
        
        if result.get("retCode") == 0:
            # Update trade record with remaining quantity
            trade["qty"] = round_qty(symbol, total_qty - exit_qty)
            
            # Log the partial exit
            log(f"🔹 Partial exit ({exit_percentage}%) executed for {symbol}: {exit_qty} out of {total_qty}")
            write_log(f"PARTIAL EXIT: {symbol} | {exit_percentage}% | Qty: {exit_qty}/{total_qty}")
            
            # Add to exit tranches history
            if "exit_tranches_history" not in trade:
                trade["exit_tranches_history"] = []
            
            trade["exit_tranches_history"].append({
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "percentage": exit_percentage,
                "qty": exit_qty
            })
            
            save_active_trades()
            return True
        else:
            error_msg = result.get("retMsg", "Unknown error")
            log(f"❌ Failed to execute partial exit for {symbol}: {error_msg}", level="ERROR")
            
            # Check if error is about minimum quantity
            if "minimum limit" in error_msg.lower():
                # Try with minimum quantity instead
                log(f"🔄 Retrying with minimum quantity {min_qty}")
                retry_result = await place_market_order(
                    symbol=symbol,
                    side=side,
                    qty=str(min_qty),
                    market_type="linear",
                    reduce_only=True
                )
                
                if retry_result.get("retCode") == 0:
                    log(f"✅ Partial exit with minimum qty for {symbol} executed")
                    trade["qty"] = round_qty(symbol, total_qty - min_qty)
                    save_active_trades()
                    return True
            
            return False
    except Exception as e:
        log(f"❌ Error during partial exit for {symbol}: {e}", level="ERROR")
        return False

async def update_stop_loss_order(symbol, trade, new_sl_price):
    """Updated function with enhanced error handling and cleanup"""
    direction = trade.get("direction", "").lower()
    qty = trade.get("qty")
    old_sl_order_id = trade.get("sl_order_id")
    
    if not direction or not qty:
        log(f"❌ Cannot update SL for {symbol}: Missing trade data", level="ERROR")
        return False
    
    # Step 1: Clean up existing orders for this symbol
    try:
        await cleanup_orphaned_stop_orders(symbol)
        await asyncio.sleep(0.5)  # Brief pause after cleanup
    except Exception as e:
        log(f"⚠️ Cleanup error for {symbol}: {e}", level="WARN")
    
    # Step 2: Place new SL order using the enhanced function
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
                "symbol": symbol,
                "settleCoin": "USDT"
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

async def check_for_momentum_surge(symbol, candles_by_tf):
    """
    Check if symbol is experiencing a strong momentum move
    Returns True if momentum surge is detected
    """
    try:
        # For best detection, use 1m and 5m timeframes
        candles_1m = candles_by_tf.get('1', [])
        candles_5m = candles_by_tf.get('5', [])
        
        # Check both timeframes for strength confirmation
        surge_1m = detect_momentum_surge(candles_1m) if candles_1m else False
        surge_5m = detect_momentum_surge(candles_5m) if candles_5m else False
        
        # If either timeframe shows momentum surge, consider it valid
        has_momentum = surge_1m or surge_5m
        
        if has_momentum:
            log(f"🚀 Momentum surge detected on {symbol} - Trade management adjusting for potential pump")
            
        return has_momentum
    except Exception as e:
        log(f"❌ Error checking momentum: {e}", level="ERROR")
        return False

async def monitor_trades(live_candles):
    update_exit_cooldowns()

    # Clean up any exited trades that might have been missed
    cleanup_exited_trades()

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
                
                # Store candles in trade object for reference by other functions
                trade["candles_1m"] = candles_by_tf.get('1')
                
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
                
                # Only add to score history if it's a valid score
                if score is not None and score >= 0:
                    trade["score_history"].append(score)
                    trade["last_score_update"] = datetime.utcnow()
                
                # Update max score if current score is higher
                if score > trade.get("max_score", 0):
                    trade["max_score"] = score
                
                trade["cycles"] += 1
            except Exception as e:
                log(f"❌ Error scoring {symbol}: {e}", level="ERROR")
                continue
            
            # 3. Check for momentum surge - important for managing big pumps
            has_momentum = await check_for_momentum_surge(symbol, candles_by_tf)
            trade["in_momentum"] = has_momentum
            
            # 4. ENHANCED TP1 DETECTION using improved detection method
            if not trade.get("tp1_hit"):
                # Get candles for TP1 detection
                candles = candles_by_tf.get('1', [])
    
                # Get fixed percentages for this trade type
                fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
                tp1_pct = fixed_params["tp1_pct"]
    
                # Calculate TP1 level using FIXED percentage
                tp1_level = trade.get("tp1_target")
                if not tp1_level:
                    tp1_level = entry_price * (1 + tp1_pct/100) if direction.lower() == "long" else entry_price * (1 - tp1_pct/100)
                    log(f"📊 Calculated TP1 for {symbol} using fixed {tp1_pct}% = {tp1_level}")
    
                # Enhanced TP1 detection
                tp1_hit = False
    
                # Check current price
                if direction.lower() == "long" and current_price >= tp1_level:
                    tp1_hit = True
                elif direction.lower() == "short" and current_price <= tp1_level:
                    tp1_hit = True
    
                # Also check recent candle wicks for more robust detection
                if not tp1_hit and candles and len(candles) >= 2:
                    last_candle = candles[-1]
        
                    # For long positions, check if high price reached TP1
                    if direction.lower() == "long" and float(last_candle["high"]) >= tp1_level:
                        log(f"🔍 TP1 hit detected for {symbol} via high price: {last_candle['high']} >= {tp1_level}")
                        tp1_hit = True
                    # For short positions, check if low price reached TP1
                    elif direction.lower() == "short" and float(last_candle["low"]) <= tp1_level:
                        log(f"🔍 TP1 hit detected for {symbol} via low price: {last_candle['low']} <= {tp1_level}")
                        tp1_hit = True
    
                if tp1_hit:
                    # Log TP1 detection with details
                    log_tp1_event(symbol, "DETECTED", {
                        "price": float(current_price),
                        "entry_price": float(entry_price),
                        "tp1_target": float(tp1_level),
                        "direction": direction
                    })
        
                    # Mark TP1 as hit in trade object
                    trade["tp1_hit"] = True
                    trade["tp1_hit_cycle"] = trade.get("cycles", 0)
                    trade["break_even_triggered"] = True
                    trade["tp1_price"] = tp1_level  # Store the actual TP1 level that was hit

                    # IMPORTANT: Update trailing percentage to fixed value for immediate activation
                    fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
                    trade["trailing_pct"] = fixed_params["trailing_pct"]
    
                    log(f"🎯 TP1 Hit - Trailing will activate immediately with {trade['trailing_pct']}%")
                    
                    # Execute partial exit with improved retry logic
                    if not trade.get("tp1_partial_exit"):
                        # Use enhanced partial exit function with retry
                        exit_success = await execute_partial_exit_with_retry(symbol, trade, 20)  # 33% of position
                        
                        if exit_success:
                            trade["tp1_partial_exit"] = True
                            write_log(f"TP1 PARTIAL EXIT (20% - LET WINNERS RUN): {symbol} | Price: {current_price} | Success")
                        else:
                            write_log(f"TP1 PARTIAL EXIT FAILED: {symbol} | Price: {current_price}")
                    
                    # Move SL to breakeven with enhanced error handling
                    new_sl = entry_price  # Breakeven
                    
                    # Update SL to breakeven using centralized function with retry
                    sl_updated = await update_stop_loss_order(symbol, trade, new_sl)
                    
                    if sl_updated:
                        write_log(f"TP1 SL UPDATE: {symbol} | New SL: {new_sl} (breakeven)")
                    else:
                        write_log(f"TP1 SL UPDATE FAILED: {symbol}")
                    
                    # Send Telegram notification
                    await send_telegram_message(f"🎯 <b>TP1 Hit</b> on <b>{symbol}</b> @ {current_price}")
                    
                    # Log for analysis
                    log_trade_to_file(
                        symbol=symbol, 
                        direction=direction, 
                        entry=entry_price, 
                        sl=new_sl,  # Now at breakeven
                        tp1=current_price, 
                        tp2=None, 
                        result="tp1", 
                        score=score, 
                        trade_type=trade_type, 
                        confidence=0,
                        tf_scores=tf_scores,
                        indicator_scores=indicator_scores,
                        used_indicators=used_list
                    )
                    
                    # Save updated trade state
                    save_active_trades()

                    msg = f"🎯 <b>TP1 Hit</b> on <b>{symbol}</b> @ {current_price}\n"
                    msg += f"Entry: {entry_price} | Target: {tp1_level} ({tp1_pct}%)\n"
                    msg += f"💰 20% Partial Exit Executed (80% riding)\n"
                    msg += f"🛡️ SL Moved to Breakeven: {entry_price}\n"
                    msg += f"📍 Trailing {trade['trailing_pct']}% activates immediately"

                    await send_telegram_message(msg)
            
            # 5. Check for profit protection milestones (before TP1)(DISABLED)
            # 6. ENHANCED TRAILING STOP LOGIC after TP1
            if trade.get("tp1_hit") and trailing_pct:
                try:
                    # Get 1m candles for trailing calculation
                    candles = candles_by_tf.get('1', [])
        
                    # IMMEDIATE TRAILING - No activation threshold
                    # Calculate new trailing stop position using fixed percentage
                    current_trailing_sl = trade.get("trailing_sl")
        
                    # Calculate new SL price with fixed trailing percentage
                    if direction.lower() == "long":
                        new_sl = current_price * (1 - trailing_pct/100)
                    else:
                        new_sl = current_price * (1 + trailing_pct/100)
        
                    # Round to appropriate precision
                    new_sl = round(new_sl, 6)
        
                    # Only update if new SL is better than current
                    should_update = False
                    if current_trailing_sl is None:
                        should_update = True
                        log(f"🔐 Initial trailing stop for {symbol} at {new_sl} ({trailing_pct}% from {current_price})")
                    elif direction.lower() == "long" and new_sl > current_trailing_sl:
                        improvement = ((new_sl - current_trailing_sl) / current_trailing_sl) * 100
                        should_update = True
                        log(f"🔐 Trailing stop improved for {symbol}: {current_trailing_sl} → {new_sl} (+{improvement:.2f}%)")
                    elif direction.lower() == "short" and new_sl < current_trailing_sl:
                        improvement = ((current_trailing_sl - new_sl) / current_trailing_sl) * 100
                        should_update = True
                        log(f"🔐 Trailing stop improved for {symbol}: {current_trailing_sl} → {new_sl} (+{improvement:.2f}%)")
        
                    if should_update:
                        # Update the stop loss order
                        await update_stop_loss_order(symbol, trade, new_sl)
            
                except Exception as e:
                    log(f"❌ Error updating trailing SL for {symbol}: {e}", level="ERROR")
                    log(traceback.format_exc(), level="ERROR")

            # 7. Handle post-TP1 pump detection
            if trade.get("tp1_hit") and trade.get("tp1_price") and not trade.get("tp2_exit_executed"):
                recent_high = max(float(candle["high"]) for candle in candles_by_tf['1'][-TP1_PUMP_CANDLE_LOOKAHEAD:])
                pump_move = ((recent_high - trade["tp1_price"]) / trade["tp1_price"]) * 100
                
                # If price pumps significantly after TP1, alert and consider second exit
                if pump_move >= 2.0:
                    if not trade.get("smart_pump_alerted"):
                        trade["smart_pump_alerted"] = True
                        await send_telegram_message(f"🚀 <b>Smart Pump After TP1</b> on {symbol}: +{pump_move:.2f}% detected after TP1")
                        write_log(f"SMART PUMP AFTER TP1: {symbol} | +{pump_move:.2f}% beyond TP1")
                    
                    # Execute second exit tranche if we're in a big move and have momentum
                    if has_momentum and pump_move >= 3.0 and not trade.get("tp2_exit_executed"):
                        # Take 33% more off during pump (leaving ~33% to ride momentum)
                        if await execute_partial_exit_with_retry(symbol, trade, 25):  # 50% of REMAINING position
                            trade["tp2_exit_executed"] = True
                            await send_telegram_message(f"💰 <b>Second Partial Exit (25%)</b> on <b>{symbol}</b> — Conservative exit during +{pump_move:.2f}% pump")
                            write_log(f"PUMP EXIT (25% - LET WINNERS RUN): {symbol} | Second tranche exited during +{pump_move:.2f}% pump")
                            save_active_trades()
            
            # 8. Trail SL hit check
            if trade.get("tp1_hit") and trade.get("trailing_sl"):
                trailing_sl = trade["trailing_sl"]
                if (direction.lower() == "long" and current_price <= trailing_sl) or (direction.lower() == "short" and current_price >= trailing_sl):
                    # If we have remaining exit tranches, execute the rest of position
                    remaining_qty = trade.get("qty", 0)
        
                    if remaining_qty > 0:
                        # Exit the remainder of the position
                        side = "Sell" if direction.lower() == "long" else "Buy"
            
                        try:
                            exit_result = await place_market_order(
                                symbol=symbol,
                                side=side,
                                qty=str(remaining_qty),
                                market_type="linear",
                                reduce_only=True
                            )
                
                            if exit_result.get("retCode") == 0:
                                log(f"✅ Final position exit executed for {symbol} - {remaining_qty} units")
                            else:
                                log(f"❌ Final exit failed: {exit_result.get('retMsg')}", level="ERROR")
                        except Exception as e:
                            log(f"❌ Error in final exit: {e}", level="ERROR")
        
                    # Mark trade as exited
                    trade["exited"] = True
                    trade["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    trade["exit_reason"] = "trailing_sl_hit_after_tp1"
                    trade["exit_price"] = current_price
        
                    # Calculate final profit
                    profit_pct = ((current_price - entry_price) / entry_price) * 100 if direction.lower() == "long" else ((entry_price - current_price) / entry_price) * 100
        
                    # Send notification
                    await send_telegram_message(
                        f"⛔ <b>Trailing SL Hit</b> on {symbol} at {current_price:.4f}\n"
                        f"Final Profit: {profit_pct:.2f}%\n"
                        f"Strategy: 20% exit at TP1, 80% exited at trailing SL"
                    )
        
                    write_log(f"TRAILING SL HIT: {symbol} | Hit at: {current_price:.4f} | Profit: {profit_pct:.2f}%")
        
                    # Log trade result
                    log_trade_result(symbol, tf_scores, "win" if profit_pct > 0 else "breakeven")
                    log_trade_to_file(
                        symbol, direction, entry_price, trade.get("original_sl"), 
                        trade.get("tp1_price"), current_price, 
                        "win" if profit_pct > 0 else "breakeven", 
                        score, trade_type, 0, 
                        indicator_scores=tf_scores, 
                        used_indicators=used_list
                    )
        
                    # Log strategy performance
                    strategy = "core_strategy"
                    if tf_scores.get("mean_reversion"):
                        strategy = "mean_reversion"
                    elif tf_scores.get("breakout_sniper"):
                        strategy = "breakout_sniper"
        
                    log_strategy_result(strategy, "win" if profit_pct > 0 else "loss", round(profit_pct, 2))
        
                    # IMPORTANT: Remove from active_trades dictionary
                    log(f"🗑️ Removing {symbol} from active trades due to trailing SL hit after TP1")
                    del active_trades[symbol]
                    recent_exits[symbol] = EXIT_COOLDOWN
        
                    # Save the updated trades
                    save_active_trades()
                    continue

            # 9. Original SL hit check (before TP1)
            if not trade.get("tp1_hit") and trade.get("original_sl"):
                sl_price = trade["original_sl"]
                if (direction.lower() == "long" and current_price <= sl_price) or (direction.lower() == "short" and current_price >= sl_price):
                    # Mark as exited
                    trade["exited"] = True
                    trade["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    trade["exit_reason"] = "sl_hit"
                    trade["exit_price"] = current_price
        
                    # Send notifications and log
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
        
                    # IMPORTANT: Remove from active_trades
                    log(f"🗑️ Removing {symbol} from active trades due to SL hit")
                    del active_trades[symbol]
                    recent_exits[symbol] = EXIT_COOLDOWN
        
                    save_active_trades()
                    continue

            # 10. Time-based exit check with momentum override
            # Don't exit on time during a strong momentum move
            if not has_momentum and not trade.get("exit_timed"):
                if should_exit_by_time(trade, datetime.utcnow(), candles_by_tf.get('1', []), current_price):
                    # Mark the trade for exit
                    trade["exit_timed"] = True
                    
                    # Execute market exit
                    side = "Sell" if direction.lower() == "long" else "Buy"
                    try:
                        exit_result = await place_market_order(
                            symbol=symbol,
                            side=side, 
                            qty=str(trade.get("qty")),
                            market_type="linear",
                            reduce_only=True
                        )
                        
                        if exit_result.get("retCode") == 0:
                            trade["exited"] = True
                            
                            # Get trade age in hours for logging
                            entry_time = datetime.strptime(trade.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
                            current_time = datetime.utcnow()
                            trade_age_hours = (current_time - entry_time).total_seconds() / 3600
                            
                            await send_telegram_message(f"⏱ <b>Time-Based Exit</b> on <b>{symbol}</b> after {trade_age_hours:.1f} hours")
                            write_log(f"TIME EXIT: {symbol} | {trade_age_hours:.1f} hours in trade")
                            
                            # Calculate P&L
                            profit_pct = ((current_price - entry_price) / entry_price * 100) if direction.lower() == "long" else ((entry_price - current_price) / entry_price * 100)
                            result_type = "win" if profit_pct > 0 else "loss"
                            
                            log_trade_result(symbol, tf_scores, result_type)
                            log_trade_to_file(symbol, direction, entry_price, trade.get("original_sl"), None, current_price, result_type, score, trade_type, 0, indicator_scores=tf_scores, used_indicators=used_list)
                            
                            strategy = "core_strategy"
                            if tf_scores.get("mean_reversion"):
                                strategy = "mean_reversion"
                            elif tf_scores.get("breakout_sniper"):
                                strategy = "breakout_sniper"
                                
                            log_strategy_result(strategy, result_type, round(profit_pct, 2))
                            save_active_trades()
                            continue
                    except Exception as e:
                        log(f"❌ Error executing time-based exit: {e}", level="ERROR")
            
            # 12. Periodically verify position and orders (every 10 cycles, to avoid API rate limits)
            if trade.get("cycles") % 10 == 0:
                await verify_position_and_orders(symbol, trade, auto_repair=True)
                    
        except Exception as e:
            log(f"❌ Unhandled error monitoring {symbol}: {e}", level="ERROR")
            write_log(f"MONITOR ERROR: {symbol} | {str(e)}", level="ERROR")

    save_active_trades()

def cleanup_exited_trades():
    """Remove any trades marked as exited from active_trades"""
    global active_trades
    
    exited_symbols = []
    for symbol, trade in list(active_trades.items()):
        if trade.get("exited", False):
            exited_symbols.append(symbol)
    
    for symbol in exited_symbols:
        log(f"🧹 Cleaning up exited trade: {symbol}")
        del active_trades[symbol]
    
    if exited_symbols:
        log(f"🧹 Cleaned up {len(exited_symbols)} exited trades")
        save_active_trades()

async def log_trade_result(symbol, result: str, profit: float):
    """Called when a trade closes (for win/loss tracking)"""
    if symbol in active_trades:
        trade = active_trades[symbol]
        
        # Process the trade result with the new system
        from position_manager import process_trade_result
        await process_trade_result(trade, result, profit)
        
        # Remove from active trades
        active_trades.pop(symbol)

    if result == "win":
        daily_stats["wins"] += 1
    elif result == "loss":
        daily_stats["losses"] += 1

    daily_stats["profit"] += profit

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
                    
                    # Check if we're in momentum - don't emergency exit during a strong momentum move
                    is_momentum = trade.get("in_momentum", False)
                    
                    # Calculate move percentage
                    move_pct = ((current_price - entry_price) / entry_price) * 100
                    move_pct = move_pct if direction == "long" else -move_pct
                    
                    # Exit position if extremely adverse move (over 20% against position)
                    # Increased from 15% to 20% to be more tolerant of volatility
                    if move_pct < -20 and not is_momentum:  # Don't exit on drawdowns during momentum
                        await send_telegram_message(f"🚨 <b>EMERGENCY EXIT</b> for {symbol} (move: {move_pct:.2f}%)")
                        
                        # Execute emergency market exit
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

# Check for missed TP1 hits on startup
async def check_missed_tp1_hits():
    """
    Scan active trades to detect if any TP1 targets have been hit but not processed
    This is especially useful after bot restarts
    """
    log("🔍 Checking for missed TP1 hits...")
    
    for symbol, trade in active_trades.items():
        if trade.get("exited") or trade.get("tp1_hit"):
            continue
            
        try:
            # Skip if necessary data is missing
            if not trade.get("entry_price") or not trade.get("direction"):
                continue
            
            entry_price = trade.get("entry_price")
            direction = trade.get("direction", "").lower()
                
            # Get current price
            ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
            current_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
            
            if current_price <= 0:
                continue
                
            # Get candles if available
            candles = None
            if symbol in live_candles and '1' in live_candles[symbol]:
                candles = list(live_candles[symbol]['1'])
                
            # Calculate TP1 level - using the standard 1.8% for both directions
            tp1_level = entry_price * 1.018 if direction == "long" else entry_price * 0.982
            
            # Check if TP1 has been hit based on current price
            tp1_hit = (direction == "long" and current_price >= tp1_level) or \
                    (direction == "short" and current_price <= tp1_level)
                     
            # Also check candle wicks for a more robust detection
            if not tp1_hit and candles and len(candles) >= 3:
                for i in range(min(3, len(candles))):
                    candle = candles[-(i+1)]
                    if direction == "long" and float(candle["high"]) >= tp1_level:
                        tp1_hit = True
                        break
                    elif direction == "short" and float(candle["low"]) <= tp1_level:
                        tp1_hit = True
                        break
            
            if tp1_hit:
                log(f"🎯 Missed TP1 hit detected for {symbol}")
                
                # Mark TP1 as hit
                trade["tp1_hit"] = True
                trade["tp1_hit_cycle"] = trade.get("cycles", 0)
                trade["tp1_price"] = current_price
                trade["break_even_triggered"] = True
                
                # Update SL to breakeven
                await update_stop_loss_order(symbol, trade, entry_price)
                
                # Send notification
                await send_telegram_message(
                    f"🎯 <b>Missed TP1 Hit Detected</b> for {symbol}\n"
                    f"<b>Current Price:</b> {current_price}\n"
                    f"<b>TP1 Level:</b> {tp1_level}\n"
                    f"🛡️ SL moved to breakeven"
                )
                
                log(f"✅ Recovered missed TP1 hit for {symbol}")
                write_log(f"MISSED TP1 RECOVERY: {symbol} | Current price: {current_price} | TP1 level: {tp1_level}")
                
                # Execute partial TP1 exit if possible
                try:
                    await execute_partial_exit(symbol, trade, 33)
                    trade["tp1_partial_exit"] = True
                    log(f"💰 Executed partial exit for missed TP1 on {symbol}")
                except Exception as exit_error:
                    log(f"❌ Failed to execute partial exit for missed TP1: {exit_error}", level="ERROR")
                
                save_active_trades()
                
        except Exception as e:
            log(f"❌ Error checking missed TP1 for {symbol}: {e}", level="ERROR")
    
    log("✅ Missed TP1 check complete")

async def execute_partial_exit_with_retry(symbol, trade, exit_percentage, max_attempts=3):
    """
    Execute a partial exit with retry logic
    
    Args:
        symbol: Trading symbol
        trade: Trade object from active_trades
        exit_percentage: Percentage of position to exit (e.g., 33 for 33%)
        max_attempts: Maximum retry attempts
        
    Returns:
        bool: True if partial exit was successful
    """
    direction = trade.get("direction", "").lower()
    total_qty = trade.get("qty", 0)
    
    if not direction or not total_qty or total_qty <= 0:
        log(f"❌ Cannot execute partial exit for {symbol}: Invalid trade data", level="ERROR")
        return False
    
    # Calculate exit quantity
    exit_qty = total_qty * (exit_percentage / 100)
    
    # Ensure exit quantity meets minimum requirements
    from symbol_info import round_qty
    min_qty = 0.001  # Default minimum quantity
    
    exit_qty = max(round_qty(symbol, exit_qty), min_qty)
    
    # Don't exit more than we have
    exit_qty = min(exit_qty, total_qty)
    
    log(f"🔍 Attempting partial exit for {symbol}: {exit_qty} units ({exit_percentage}% of {total_qty})")
    
    # Try to execute the exit with retries
    for attempt in range(max_attempts):
        try:
            # Execute market order
            side = "Sell" if direction == "long" else "Buy"
            
            result = await place_market_order(
                symbol=symbol,
                side=side,
                qty=str(exit_qty),
                market_type="linear",
                reduce_only=True
            )
            
            if result.get("retCode") == 0:
                # Update trade record with remaining quantity
                trade["qty"] = round_qty(symbol, total_qty - exit_qty)
                
                # Log the partial exit
                log(f"💰 Partial exit ({exit_percentage}%) executed for {symbol}: {exit_qty} out of {total_qty}")
                write_log(f"PARTIAL EXIT: {symbol} | {exit_percentage}% | Qty: {exit_qty}/{total_qty}")
                
                # Record in exit tranches history
                if "exit_tranches_history" not in trade:
                    trade["exit_tranches_history"] = []
                
                trade["exit_tranches_history"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "percentage": exit_percentage,
                    "qty": exit_qty
                })
                
                save_active_trades()
                return True
            else:
                log(f"❌ Partial exit attempt {attempt+1}/{max_attempts} failed: {result.get('retMsg')}", level="ERROR")
                
                # Brief pause before retry
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        except Exception as e:
            log(f"❌ Error in partial exit attempt {attempt+1}/{max_attempts}: {e}", level="ERROR")
            
            # Brief pause before retry
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    
    # If we get here, all attempts failed
    log(f"❌ All partial exit attempts failed for {symbol}", level="ERROR")
    return False

async def cleanup_orphaned_stop_orders(symbol):
    """Clean up any orphaned stop orders for a symbol"""
    try:
        # Get all active stop orders for the symbol
        orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear",
            "symbol": symbol,
            "orderFilter": "StopOrder"
        })
        
        if orders_resp.get("retCode") == 0:
            orders = orders_resp.get("result", {}).get("list", [])
            
            for order in orders:
                if order.get("orderStatus") in ["New", "PartiallyFilled", "Untriggered"]:
                    # Cancel this orphaned order
                    cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                        "category": "linear",
                        "symbol": symbol,
                        "orderId": order.get("orderId")
                    })
                    
                    if cancel_resp.get("retCode") == 0:
                        log(f"🧹 Cleaned up orphaned stop order for {symbol}: {order.get('orderId')}")
                    
                    await asyncio.sleep(0.1)  # Rate limit protection
                    
    except Exception as e:
        log(f"❌ Error cleaning up orphaned orders: {e}", level="ERROR")
    return False

async def verify_trade_cleanup():
    """Verify that exited trades are properly removed"""
    global active_trades
    
    issues_found = []
    
    # Check for trades that should be removed
    for symbol, trade in list(active_trades.items()):
        if trade.get("exited", False):
            issues_found.append(f"{symbol} is marked as exited but still in active_trades")
            # Remove it
            del active_trades[symbol]
    
    if issues_found:
        log(f"⚠️ Found {len(issues_found)} trades that needed cleanup:", level="WARN")
        for issue in issues_found:
            log(f"  - {issue}")
        save_active_trades()
        await send_telegram_message(f"🧹 Cleaned up {len(issues_found)} exited trades that were still in active_trades")
    else:
        log("✅ All exited trades properly removed from active_trades")
