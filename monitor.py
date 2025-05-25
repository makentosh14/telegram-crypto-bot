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

_last_monitor_save = 0
_monitor_save_cooldown = 5  # 5 seconds

# Add these new globals after the existing ones (around line 20-30)
_sl_check_timestamps = {}  # Track when we last checked SL for each symbol
_sl_creation_locks = {}    # Prevent concurrent SL operations
_active_sl_operations = set()  # Track ongoing SL operations
SL_CREATION_TRACKER = {}  # Track when SL was last created for each symbol

# Add these constants
SL_CHECK_COOLDOWN = 300  # 5 minutes between SL checks per symbol
SL_CREATION_COOLDOWN = 60  # 1 minute cooldown after creating SL
MONITOR_INTERVAL = 5  # Main monitor loop interval

# Add these constants
SL_CHECK_COOLDOWN = 300  # 5 minutes between SL checks per symbol
SL_CREATION_COOLDOWN = 60  # 1 minute cooldown after creating SL
MONITOR_INTERVAL = 5  # Main monitor loop interval


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

async def periodic_trade_sync():
    """Periodically reload trades from file to ensure sync"""
    while True:
        try:
            # Wait 30 seconds before first sync to let bot initialize
            if time.time() - startup_time < 30:
                await asyncio.sleep(10)
                continue
                
            # Reload trades from file
            load_active_trades()
            log(f"🔄 Periodic sync: {len(active_trades)} active trades")
            
        except Exception as e:
            log(f"❌ Error in periodic trade sync: {e}", level="ERROR")
        
        # Sync every 60 seconds
        await asyncio.sleep(60)

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
    global _last_monitor_save
    
    # Debounce saves
    current_time = time.time()
    if current_time - _last_monitor_save < _monitor_save_cooldown:
        log(f"🔄 Skipping save (cooldown active)")
        return
        
    try:
        log(f"💾 Saving {len(active_trades)} active trades to file...")
        
        # CRITICAL: Don't save if we have 0 trades but file has trades
        if len(active_trades) == 0 and os.path.exists(PERSIST_PATH):
            try:
                with open(PERSIST_PATH, 'r') as f:
                    existing_data = json.load(f)
                    existing_active = sum(1 for t in existing_data.values() if not t.get("exited", False))
                    
                    if existing_active > 0:
                        log(f"⚠️ SAFETY: Refusing to overwrite {existing_active} active trades with empty data!", level="WARN")
                        # Reload the trades instead
                        load_active_trades()
                        return
            except:
                pass
        
        # Create a backup before saving
        if os.path.exists(PERSIST_PATH) and len(active_trades) == 0:
            backup_path = f"{PERSIST_PATH}.backup_{int(time.time())}"
            import shutil
            shutil.copy2(PERSIST_PATH, backup_path)
            log(f"📁 Created safety backup: {backup_path}")
        
        # Rest of the save logic...
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

async def recover_active_trades_from_exchange():
    """Recover active trades from exchange positions"""
    try:
        from bybit_api import signed_request
        
        log("🔄 Attempting to recover trades from exchange positions...")
        
        # Get all positions
        positions_resp = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "settleCoin": "USDT"
        })
        
        if positions_resp.get("retCode") != 0:
            log(f"❌ Failed to fetch positions: {positions_resp.get('retMsg')}", level="ERROR")
            return
        
        positions = positions_resp.get("result", {}).get("list", [])
        recovered_count = 0
        
        for pos in positions:
            symbol = pos.get("symbol")
            size_str = pos.get("size", "0")
            size = float(size_str) if size_str else 0
            side = pos.get("side")  # "Buy" or "Sell"
            
            if size > 0 and symbol not in active_trades:
                # Reconstruct basic trade info
                direction = "long" if side == "Buy" else "short"
                
                # Safely get entry price
                avg_price_str = pos.get("avgPrice", "0")
                entry_price = float(avg_price_str) if avg_price_str else 0
                
                # Safely get stop loss if exists
                sl_price_str = pos.get("stopLoss", "0")
                sl_price = float(sl_price_str) if sl_price_str and sl_price_str != "" else 0
                
                # Create basic trade entry
                active_trades[symbol] = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "qty": size,
                    "original_sl": sl_price if sl_price > 0 else None,
                    "exited": False,
                    "trade_type": "Intraday",  # Default
                    "score_history": [7.0],     # Default
                    "cycles": 0,
                    "tp1_hit": False,
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "recovered": True  # Mark as recovered
                }
                
                recovered_count += 1
                log(f"✅ Recovered {symbol} position: {direction} {size} @ {entry_price}")
        
        if recovered_count > 0:
            save_active_trades()
            await send_telegram_message(f"🔄 Recovered {recovered_count} active positions from exchange")
            log(f"✅ Recovery complete: {recovered_count} trades recovered")
        else:
            log("ℹ️ No positions to recover")
            
    except Exception as e:
        log(f"❌ Error recovering trades: {e}", level="ERROR")
        import traceback
        log(traceback.format_exc(), level="ERROR")

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

    # Validate and normalize trade type
    valid_trade_types = ["Scalp", "Intraday", "Swing"]
    if trade_type not in valid_trade_types:
        log(f"⚠️ Invalid trade type '{trade_type}' for {symbol}, defaulting to Intraday", level="WARN")
        trade_type = "Intraday"                      
    
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

     log(f"📊 HF SCANNER: {symbol} using {trade_type} percentages - TP1: {tp1_pct}%, Trailing: {trailing_pct}%")
     log(f"   Original trade_type from data: '{trade.get('trade_type')}'")                     
                                                
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

    # ADD THIS: Check if SL update is meaningful (at least 0.1% difference)
    current_sl = trade.get("trailing_sl") or trade.get("original_sl")
    if current_sl:
        sl_diff_pct = abs((new_sl_price - current_sl) / current_sl) * 100
        if sl_diff_pct < 0.1:
            log(f"🔍 Skipping minor SL update for {symbol}: {sl_diff_pct:.3f}% difference")
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
            
            # IMPORTANT: Mark that we've set trailing SL after TP1
            if trade.get("tp1_hit") and not trade.get("breakeven_set"):
                trade["breakeven_set"] = True
            
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
    """Enhanced SL check with proper cooldowns and deduplication"""
    # Skip if trade is exited or missing critical data
    if not trade or trade.get("exited") or not trade.get("qty"):
        return False

    # CRITICAL: Skip if we already have a valid SL
    if trade.get("sl_verified_at"):
        # Check if verification is recent (within 30 minutes)
        verified_time = datetime.strptime(trade["sl_verified_at"], "%Y-%m-%d %H:%M:%S")
        if (datetime.utcnow() - verified_time).total_seconds() < 1800:  # 30 minutes
            return True  # SL is recently verified, skip
    
    # Skip if we're already processing SL for this symbol
    if symbol in _active_sl_operations:
        log(f"🔄 SL operation already in progress for {symbol}, skipping")
        return False
    
    # Check cooldown
    current_time = time.time()
    last_check = _sl_check_timestamps.get(symbol, 0)
    
    if current_time - last_check < 1800:
        return False  # Too soon to check again

    # Check if we created SL recently
    last_creation = SL_CREATION_TRACKER.get(symbol, 0)
    if current_time - last_creation < 3600:  # 1 hour cooldown after creation
        log(f"⏳ {symbol}: SL created recently, skipping check")
        return False
    
    # Update check timestamp
    _sl_check_timestamps[symbol] = current_time
    
    # Add to active operations
    _active_sl_operations.add(symbol)
    
    try:
        # Skip if TP1 has been hit - we manage SL differently after TP1
        if trade.get("tp1_hit"):
            log(f"📌 {symbol}: TP1 hit, using trailing stop management")
            return False
        
        sl_order_id = trade.get("sl_order_id")
        
        # First, check if we already have active SL orders on exchange
        existing_sl = await check_existing_sl_orders(symbol)
        if existing_sl:
            log(f"✅ {symbol}: Active SL order found on exchange")
            # Update our records if we don't have the order ID
            trade["sl_verified_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if not sl_order_id:
                trade["sl_order_id"] = "external_sl"  # Mark that SL exists
                save_active_trades()
            return True
        
        # If we have an order ID, verify it still exists
        if sl_order_id and sl_order_id != "external_sl":
            try:
                sl_exists = await check_order_exists(sl_order_id, symbol)
                if sl_exists:
                    log(f"✅ {symbol}: SL order {sl_order_id} verified")
                    trade["sl_verified_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    save_active_trades()
                    return True
            except Exception as e:
                log(f"⚠️ Error checking SL order existence: {e}", level="WARN")
        
        # If we get here, we need to create/restore the SL
        log(f"🛡️ {symbol}: Creating stop loss order (first time or recovery)")
        
        direction = trade.get("direction", "").lower()
        qty = trade.get("qty")
        entry_price = trade.get("entry_price")
        
        if not direction or not qty or not entry_price:
            log(f"❌ {symbol}: Missing trade data for SL creation", level="ERROR")
            return False
        
        # Determine SL price
        sl_price = trade.get("original_sl")
        if not sl_price:
            # Calculate safety SL (2% from entry)
            if direction == "long":
                sl_price = round(entry_price * 0.98, 6)
            else:
                sl_price = round(entry_price * 1.02, 6)
            log(f"⚠️ {symbol}: No SL price found, using safety SL: {sl_price}")
        
        # Validate SL placement
        sl_price = await validate_sl_placement(symbol, direction, sl_price)
        
        # Place the SL order
        sl_resp = await place_stop_loss_with_retry(symbol, direction, qty, sl_price)
        
        if sl_resp.get("retCode") == 0:
            new_sl_order_id = sl_resp.get("result", {}).get("orderId")
            trade["sl_order_id"] = new_sl_order_id
            
            # Only send telegram for initial SL creation
            if not sl_order_id:
                await send_telegram_message(f"🛡️ <b>SL Created</b> for {symbol} at {sl_price}")
            
            log(f"✅ {symbol}: SL created successfully at {sl_price}")
            save_active_trades()
            return True
        else:
            log(f"❌ {symbol}: Failed to create SL: {sl_resp.get('retMsg')}", level="ERROR")
            return False
            
    except Exception as e:
        log(f"❌ Error in SL check for {symbol}: {e}", level="ERROR")
        return False

        # After successful creation, update tracker
        SL_CREATION_TRACKER[symbol] = current_time

    finally:
        # Remove from active operations
        _active_sl_operations.discard(symbol)
        
async def check_existing_sl_orders(symbol):
    """Check if stop-loss orders already exist for this symbol"""
    try:
        orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear",
            "symbol": symbol,
            "orderFilter": "StopOrder"
        })
        
        if orders_resp.get("retCode") == 0:
            orders = orders_resp.get("result", {}).get("list", [])
            active_sl_orders = [
                o for o in orders 
                if o.get("orderStatus") in ["New", "Untriggered"] 
                and o.get("stopOrderType") in ["StopLoss", "Stop"]  # Added "Stop"
                and o.get("reduceOnly") == True  # Must be reduce-only
            ]
            
            if active_sl_orders:
                log(f"✅ Found {len(active_sl_orders)} active SL orders for {symbol}")
                return True
                
    except Exception as e:
        log(f"Error checking existing SL orders: {e}")
    return False

async def validate_sl_placement(symbol, direction, sl_price):
    """Validate SL price is on correct side of market"""
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {
            "category": "linear", 
            "symbol": symbol
        })
        
        mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
        
        if mark_price <= 0:
            return sl_price
        
        # Ensure proper SL placement with 0.5% buffer
        buffer = 0.005
        
        if direction == "long" and sl_price >= mark_price * (1 - buffer):
            new_sl = round(mark_price * (1 - buffer), 6)
            log(f"⚠️ Adjusted long SL from {sl_price} to {new_sl}")
            return new_sl
        elif direction == "short" and sl_price <= mark_price * (1 + buffer):
            new_sl = round(mark_price * (1 + buffer), 6)
            log(f"⚠️ Adjusted short SL from {sl_price} to {new_sl}")
            return new_sl
            
        return sl_price
        
    except Exception as e:
        log(f"Error validating SL placement: {e}")
        return sl_price

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
    """Main monitoring loop - cleaned up and optimized"""
    
    # Skip during startup grace period
    if time.time() - startup_time < 120:
        log("⏳ Grace period active, skipping trade monitoring...")
        return
    
    # Clean up exited trades first
    cleanup_exited_trades()
    
    # Process each active trade
    for symbol, trade in list(active_trades.items()):
        try:
            # Skip exited trades
            if trade.get("exited"):
                continue
            
            # Validate trade data
            if not trade.get("entry_price") or not trade.get("direction"):
                log(f"⚠️ {symbol}: Invalid trade data, skipping")
                continue
            
            # Skip if symbol not in live candles
            if symbol not in live_candles:
                continue
            
            # Get candles
            candles_by_tf = {}
            try:
                for tf in ['1', '3', '5', '15', '30', '60', '240']:
                    if str(tf) in live_candles[symbol]:
                        candles_by_tf[tf] = list(live_candles[symbol][str(tf)])
                
                if not candles_by_tf.get('1'):
                    continue
                    
                current_price = float(candles_by_tf['1'][-1]['close'])
            except Exception as e:
                log(f"⚠️ Error getting candles for {symbol}: {e}")
                continue
            
            # Core trade variables
            trade_type = trade.get("trade_type", "Intraday")
            direction = trade.get("direction", "").lower()
            entry_price = trade.get("entry_price")
            
            # Update cycle count
            trade["cycles"] = trade.get("cycles", 0) + 1
            
            # 1. SL Check (only if needed and not too frequent)
            if not trade.get("sl_order_id") and not trade.get("tp1_hit"):
                # Only check SL periodically, not every cycle
                if trade["cycles"] % 360 == 0:  # Every 60 seconds (5s * 12)
                    await check_and_restore_sl(symbol, trade)
            
            # 2. Calculate score for monitoring
            try:
                score, tf_scores, _, indicator_scores, used_list = score_symbol(symbol, candles_by_tf)
                if score is not None and score >= 0:
                    trade["score_history"].append(score)
                    trade["last_score_update"] = datetime.utcnow()
            except Exception as e:
                log(f"Error scoring {symbol}: {e}")
                score = trade.get("score_history", [7.0])[-1]
            
            # 3. Check for TP1 hit
            if not trade.get("tp1_hit"):
                tp1_hit = check_tp1_hit(trade, current_price, candles_by_tf.get('1', []))
                if tp1_hit:
                    await handle_tp1_hit(symbol, trade, current_price)
            
            # 4. Handle trailing stop after TP1
            elif trade.get("tp1_hit") and trade.get("trailing_pct"):
                await handle_trailing_stop(symbol, trade, current_price, direction)
            
            # 5. Check for SL hit (before TP1)
            if not trade.get("tp1_hit") and trade.get("original_sl"):
                if check_sl_hit(trade, current_price, direction):
                    await handle_sl_hit(symbol, trade, current_price, score, tf_scores, used_list)
                    continue
            
            # 6. Check for trailing SL hit (after TP1)
            if trade.get("tp1_hit") and trade.get("trailing_sl"):
                if check_trailing_sl_hit(trade, current_price, direction):
                    await handle_trailing_sl_hit(symbol, trade, current_price, score, tf_scores, used_list)
                    continue
            
            # 7. Time-based exit check (every 60 cycles = 5 minutes)
            if trade["cycles"] % 60 == 0:
                if should_exit_by_time(trade, datetime.utcnow(), candles_by_tf.get('1'), current_price):
                    await handle_time_exit(symbol, trade, current_price, score, tf_scores, used_list)
                    continue
                    
        except Exception as e:
            log(f"❌ Error monitoring {symbol}: {e}", level="ERROR")
            log(traceback.format_exc(), level="ERROR")
    
    # Save only if there were changes
    if any(t.get("cycles", 0) > 0 for t in active_trades.values()):
        save_active_trades()

def check_tp1_hit(trade, current_price, candles):
    """Check if TP1 has been hit"""
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    trade_type = trade.get("trade_type", "Intraday")
    
    # Get fixed TP1 percentage
    fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
    tp1_pct = fixed_params["tp1_pct"]
    
    # Calculate TP1 level
    tp1_level = trade.get("tp1_target")
    if not tp1_level:
        if direction == "long":
            tp1_level = entry_price * (1 + tp1_pct/100)
        else:
            tp1_level = entry_price * (1 - tp1_pct/100)
    
    # Check current price
    if direction == "long" and current_price >= tp1_level:
        return True
    elif direction == "short" and current_price <= tp1_level:
        return True
    
    # Check candle wicks
    if candles and len(candles) >= 2:
        last_candle = candles[-1]
        if direction == "long" and float(last_candle["high"]) >= tp1_level:
            return True
        elif direction == "short" and float(last_candle["low"]) <= tp1_level:
            return True
    
    return False

def check_sl_hit(trade, current_price, direction):
    """Check if SL has been hit"""
    sl_price = trade.get("original_sl")
    if not sl_price:
        return False
        
    if direction == "long" and current_price <= sl_price:
        return True
    elif direction == "short" and current_price >= sl_price:
        return True
        
    return False

def check_trailing_sl_hit(trade, current_price, direction):
    """Check if trailing SL has been hit"""
    trailing_sl = trade.get("trailing_sl")
    if not trailing_sl:
        return False
        
    # Add small buffer for wicks
    buffer = 0.002  # 0.2%
    
    if direction == "long" and current_price <= trailing_sl * (1 - buffer):
        return True
    elif direction == "short" and current_price >= trailing_sl * (1 + buffer):
        return True
        
    return False

async def handle_tp1_hit(symbol, trade, current_price):
    """Handle TP1 hit event"""
    # Mark TP1 as hit
    trade["tp1_hit"] = True
    trade["tp1_hit_cycle"] = trade.get("cycles", 0)
    trade["tp1_price"] = current_price
    trade["break_even_triggered"] = True
    
    # Get fixed trailing percentage
    trade_type = trade.get("trade_type", "Intraday")
    fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
    trade["trailing_pct"] = fixed_params["trailing_pct"]
    
    log(f"🎯 TP1 Hit for {symbol} - Trailing will activate immediately with {trade['trailing_pct']}%")
    
    # Execute partial exit (20% for "let winners run")
    if not trade.get("tp1_partial_exit"):
        exit_success = await execute_partial_exit_with_retry(symbol, trade, 20)
        if exit_success:
            trade["tp1_partial_exit"] = True
    
    # Move SL to breakeven
    entry_price = trade.get("entry_price")
    sl_updated = await update_stop_loss_order(symbol, trade, entry_price)
    
    # Send notification
    await send_telegram_message(
        f"🎯 <b>TP1 Hit</b> on <b>{symbol}</b> @ {current_price}\n"
        f"💰 20% Partial Exit Executed (80% riding)\n"
        f"🛡️ SL Moved to Breakeven\n"
        f"📍 Trailing {trade['trailing_pct']}% activates immediately"
    )
    
    save_active_trades()

async def handle_trailing_stop(symbol, trade, current_price, direction):
    """Handle trailing stop updates"""
    trailing_pct = trade.get("trailing_pct")
    current_trailing_sl = trade.get("trailing_sl")
    
    # Calculate new trailing stop
    if direction == "long":
        new_sl = current_price * (1 - trailing_pct/100)
    else:
        new_sl = current_price * (1 + trailing_pct/100)
    
    new_sl = round(new_sl, 6)
    
    # Only update if improvement is meaningful (0.1%)
    should_update = False
    
    if current_trailing_sl is None:
        should_update = True
    elif direction == "long" and new_sl > current_trailing_sl:
        improvement = ((new_sl - current_trailing_sl) / current_trailing_sl) * 100
        if improvement >= 0.1:
            should_update = True
    elif direction == "short" and new_sl < current_trailing_sl:
        improvement = ((current_trailing_sl - new_sl) / current_trailing_sl) * 100
        if improvement >= 0.1:
            should_update = True
    
    if should_update:
        sl_updated = await update_stop_loss_order(symbol, trade, new_sl)
        if sl_updated:
            save_active_trades()

def cleanup_exited_trades():
    """Remove exited trades from active_trades"""
    exited_symbols = [
        symbol for symbol, trade in active_trades.items() 
        if trade.get("exited", False)
    ]
    
    for symbol in exited_symbols:
        del active_trades[symbol]
        log(f"🧹 Removed exited trade: {symbol}")
    
    if exited_symbols:
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
async def verify_all_stop_losses(frequency_minutes=60):  # Changed from 15 to 60 minutes
    """Emergency verification only - not routine"""
    while True:
        try:
            # Only run after bot has been running for 30 minutes
            if time.time() - startup_time < 1800:  # 30 minutes
                await asyncio.sleep(300)
                continue
            
            log("🔍 Running emergency SL verification")
            
            for symbol, trade in active_trades.items():
                if trade.get("exited"):
                    continue
                
                # Only check if we suspect an issue
                if not trade.get("sl_order_id"):
                    log(f"⚠️ Missing SL order ID for {symbol}")
                    await check_and_restore_sl(symbol, trade)
                
                await asyncio.sleep(2)  # Longer delay between checks
        
        except Exception as e:
            log(f"❌ Error in SL verification: {e}", level="ERROR")
        
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

async def verify_and_sync_positions():
    """Verify that active_trades matches actual Bybit positions"""
    try:
        from bybit_api import signed_request
        
        # Get all positions from Bybit
        positions_resp = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "settleCoin": "USDT"
        })
        
        if positions_resp.get("retCode") != 0:
            log(f"❌ Failed to fetch positions: {positions_resp.get('retMsg')}", level="ERROR")
            return
        
        bybit_positions = {}
        positions = positions_resp.get("result", {}).get("list", [])
        
        # Build dict of actual positions
        for pos in positions:
            symbol = pos.get("symbol")
            size = float(pos.get("size", 0))
            if size > 0:
                bybit_positions[symbol] = pos
        
        # Check for mismatches
        issues_found = []
        
        # 1. Trades marked as exited but still have positions
        for symbol, trade in list(active_trades.items()):
            if trade.get("exited") and symbol in bybit_positions:
                issues_found.append(f"{symbol}: Marked as exited but position still open on Bybit")
                # Fix: Unmark as exited
                trade["exited"] = False
                log(f"🔧 Fixed: {symbol} unmarked as exited (position still open)")
        
        # 2. Positions on Bybit but not in active_trades
        for symbol, pos in bybit_positions.items():
            if symbol not in active_trades:
                issues_found.append(f"{symbol}: Position on Bybit but not in active_trades")
                # Add it back
                direction = "long" if pos.get("side") == "Buy" else "short"
                active_trades[symbol] = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": float(pos.get("avgPrice", 0)),
                    "qty": float(pos.get("size", 0)),
                    "exited": False,
                    "trade_type": "Intraday",
                    "score_history": [7.0],
                    "cycles": 0,
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "recovered": True
                }
                log(f"🔧 Recovered missing trade: {symbol}")
        
        # 3. Trades in active_trades but no position on Bybit
        for symbol in list(active_trades.keys()):
            if symbol not in bybit_positions and not active_trades[symbol].get("exited"):
                issues_found.append(f"{symbol}: In active_trades but no position on Bybit")
                # Mark as exited
                active_trades[symbol]["exited"] = True
                log(f"🔧 Fixed: {symbol} marked as exited (no position on Bybit)")
        
        if issues_found:
            log(f"⚠️ Found {len(issues_found)} sync issues:", level="WARN")
            for issue in issues_found:
                log(f"  - {issue}")
            save_active_trades()
            
            # Send summary to Telegram
            await send_telegram_message(
                f"🔧 <b>Position Sync Issues Fixed</b>\n"
                f"Found and fixed {len(issues_found)} mismatches between bot and exchange"
            )
        else:
            log("✅ All positions properly synced")
            
    except Exception as e:
        log(f"❌ Error in position sync: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
