# universal_trailing_stop_fix.py
# Complete fix for trailing stop issues - works for BOTH DCA and non-DCA trades

import asyncio
import traceback
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order, update_stop_loss_order
from enhanced_dca_protection import protection_manager
from config import ENABLE_FAST_DROP_PROTECTION, FAST_DROP_PROTECTION

# FIXED PERCENTAGES - Ensure consistency across all files
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
        "tp1_pct": 3.5,      # Keep existing for swing
        "sl_pct": 1.5,       # Keep existing for swing
        "trailing_pct": 1.5  # Keep existing for swing
    }
}

def get_effective_entry_price(trade):
    """
    Get the effective entry price for calculations - works for both DCA and non-DCA trades
    """
    try:
        # For DCA trades, entry_price should already be the averaged price
        # For non-DCA trades, entry_price is the original entry
        entry_price = trade.get("entry_price")
        
        # Double-check: if we have DCA history, verify the entry price is averaged
        dca_count = trade.get("dca_count", 0)
        if dca_count > 0:
            # DCA trade - entry_price should be the averaged entry
            log(f"📊 DCA Trade: Using averaged entry price {entry_price:.6f} (DCA count: {dca_count})")
        else:
            # Non-DCA trade - entry_price is original entry
            log(f"📊 Standard Trade: Using original entry price {entry_price:.6f}")
        
        return entry_price
        
    except Exception as e:
        log(f"❌ Error getting effective entry price: {e}", level="ERROR")
        return trade.get("entry_price", 0)

def get_remaining_position_size(trade):
    """
    Get remaining position size - works for both DCA and non-DCA trades
    """
    try:
        total_qty = trade.get("qty", 0)
        
        if trade.get("tp1_hit"):
            # After TP1, only 50% remains regardless of DCA or not
            remaining_qty = total_qty * 0.5
            position_context = "remaining 50% position (post-TP1)"
        else:
            # Before TP1, full position remains
            remaining_qty = total_qty
            position_context = "full position (pre-TP1)"
        
        dca_info = f" [DCA: {trade.get('dca_count', 0)} adds]" if trade.get('dca_count', 0) > 0 else " [No DCA]"
        log(f"📦 Position size: {remaining_qty} ({position_context}){dca_info}")
        
        return remaining_qty, position_context
        
    except Exception as e:
        log(f"❌ Error getting position size: {e}", level="ERROR")
        return trade.get("qty", 0), "unknown position"

async def universal_handle_trailing_stop(symbol, trade, current_price, direction):
    """
    Universal trailing stop handler - works for BOTH DCA and non-DCA trades
    """
    try:
        # Get trade type and corresponding fixed percentages
        trade_type = trade.get("trade_type", "Intraday")
        fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
        trailing_pct = fixed_params["trailing_pct"]
        
        # Get effective entry price (works for both DCA and non-DCA)
        entry_price = get_effective_entry_price(trade)
        current_trailing_sl = trade.get("trailing_sl")
        
        # Determine if this is a DCA trade for logging
        is_dca_trade = trade.get("dca_count", 0) > 0
        trade_context = "DCA" if is_dca_trade else "Standard"
        
        log(f"🔄 TRAILING CHECK ({trade_context}): {symbol}")
        log(f"   Current Price: {current_price}")
        log(f"   Entry (Effective): {entry_price}")
        log(f"   Current Trailing SL: {current_trailing_sl}")
        log(f"   Trailing %: {trailing_pct}%")
        log(f"   Direction: {direction}")
        
        # Calculate new trailing stop based on current price
        if direction.lower() == "long":
            new_trailing_sl = current_price * (1 - trailing_pct / 100)
            # Only trail up, never down
            if current_trailing_sl and new_trailing_sl <= current_trailing_sl:
                log(f"🚫 No trailing update - new SL ({new_trailing_sl:.6f}) not better than current ({current_trailing_sl:.6f})")
                return False
        else:  # short
            new_trailing_sl = current_price * (1 + trailing_pct / 100)
            # Only trail down, never up
            if current_trailing_sl and new_trailing_sl >= current_trailing_sl:
                log(f"🚫 No trailing update - new SL ({new_trailing_sl:.6f}) not better than current ({current_trailing_sl:.6f})")
                return False
        
        # Round to 6 decimal places for precision
        new_trailing_sl = round(new_trailing_sl, 6)
        
        # Update the trade object
        old_trailing_sl = trade.get("trailing_sl")
        trade["trailing_sl"] = new_trailing_sl
        trade["modified"] = True
        
        log(f"✅ Trailing SL updated for {symbol} ({trade_context}): {old_trailing_sl} → {new_trailing_sl}")
        
        # Try to update the actual stop loss order on the exchange
        try:
            sl_updated = await update_stop_loss_order(symbol, trade, new_trailing_sl)
            if sl_updated:
                log(f"📈 Exchange SL order updated for {symbol}: {new_trailing_sl:.6f}")
                write_log(f"TRAILING_SL_UPDATED: {symbol} | Type: {trade_context} | New SL: {new_trailing_sl:.6f} | Direction: {direction}")
                return True
            else:
                log(f"⚠️ Failed to update SL order on exchange for {symbol}")
                # Still keep the local update for monitoring
                return True
        except Exception as e:
            log(f"⚠️ Error updating SL order for {symbol}: {e}")
            # Continue with local tracking even if exchange update fails
            return True
        
    except Exception as e:
        log(f"❌ Error in universal_handle_trailing_stop for {symbol}: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

async def universal_check_trailing_sl_hit(symbol, trade, current_price, direction):
    """
    Check if trailing stop loss has been hit - with enhanced protection
    """
    try:
        # First check fast drop protection
        if ENABLE_FAST_DROP_PROTECTION:
            # Detect fast drops
            await protection_manager.detect_fast_drop(symbol, current_price)
            
            # Check if we should pause SL
            should_pause = await protection_manager.should_pause_stop_loss(symbol, trade, current_price)
            
            if should_pause:
                log(f"🛡️ SL execution paused for {symbol} - Protection active")
                return False
        
        trailing_sl = trade.get("trailing_sl")
        if not trailing_sl:
            return False
        
        # Enhanced buffer during fast drops
        base_buffer = 0.002  # 0.2%
        enhanced_buffer = 0 if not ENABLE_FAST_DROP_PROTECTION else FAST_DROP_PROTECTION.get("enhanced_buffer", 0)
        total_buffer = base_buffer + enhanced_buffer
        
        hit = False
        if direction.lower() == "long":
            # For long positions, SL is hit when price drops below trailing SL
            if current_price <= trailing_sl * (1 - total_buffer):
                hit = True
        else:  # short
            # For short positions, SL is hit when price rises above trailing SL
            if current_price >= trailing_sl * (1 + total_buffer):
                hit = True
        
        if hit:
            # One final check before executing SL
            if ENABLE_FAST_DROP_PROTECTION:
                final_check = await protection_manager.should_pause_stop_loss(symbol, trade, current_price)
                if final_check:
                    log(f"🛡️ SL execution blocked at final check for {symbol}")
                    return False
            
            # Determine trade type for logging
            is_dca_trade = trade.get("dca_count", 0) > 0
            trade_type = "DCA" if is_dca_trade else "Standard"
            log(f"🔥 Trailing SL hit for {symbol} ({trade_type} trade) at ${current_price:.6f}")
            
        return hit
        
    except Exception as e:
        log(f"❌ Error in enhanced trailing SL check for {symbol}: {e}", level="ERROR")
        return False
        
    except Exception as e:
        log(f"❌ Error checking trailing SL hit for {symbol}: {e}", level="ERROR")
        return False

async def universal_execute_trailing_sl_exit(symbol, trade, current_price):
    """
    Execute the final exit when trailing SL is hit - works for both DCA and non-DCA trades
    """
    try:
        direction = trade.get("direction", "").lower()
        
        # Get effective entry price and position details
        entry_price = get_effective_entry_price(trade)
        remaining_qty, position_context = get_remaining_position_size(trade)
        
        # Determine if this is a DCA trade
        is_dca_trade = trade.get("dca_count", 0) > 0
        trade_context = "DCA" if is_dca_trade else "Standard"
        
        # Calculate final profit percentage
        if direction == "long":
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        
        log(f"💔 Executing trailing SL exit for {symbol} ({trade_context})")
        log(f"   Exit Price: {current_price}")
        log(f"   {position_context}: {remaining_qty}")
        log(f"   Final Profit: {profit_pct:.2f}%")
        
        # Execute market order to close remaining position
        try:
            exit_side = "Sell" if direction == "long" else "Buy"
            exit_order = await place_market_order(
                symbol=symbol,
                side=exit_side,
                qty=remaining_qty,
                reduce_only=True
            )
            
            if exit_order:
                log(f"✅ Trailing SL exit executed for {symbol} ({trade_context}): {remaining_qty} @ {current_price}")
            else:
                log(f"❌ Failed to execute trailing SL exit for {symbol}", level="ERROR")
                
        except Exception as e:
            log(f"❌ Error executing trailing SL exit order for {symbol}: {e}", level="ERROR")
        
        # Mark trade as exited
        trade["exited"] = True
        trade["exit_price"] = current_price
        trade["exit_reason"] = f"Trailing_SL_Hit_{trade_context}"
        trade["profit_pct"] = profit_pct
        trade["modified"] = True
        trade["exit_time"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        # Enhanced logging based on trade type
        dca_info = ""
        if is_dca_trade:
            original_entry = trade.get("dca_history", [{}])[0].get("original_entry", entry_price)
            dca_info = f"\n🔄 DCA Used: {trade['dca_count']} adds"
            dca_info += f"\n📊 Original Entry: {original_entry:.6f}"
            dca_info += f"\n📊 Final Avg Entry: {entry_price:.6f}"
        else:
            dca_info = f"\n📊 Single Entry: {entry_price:.6f}"
        
        # Send comprehensive notification
        from error_handler import send_telegram_message
        await send_telegram_message(
            f"💔 <b>Trailing SL Hit</b> - <b>{symbol}</b> ({trade_context})\n"
            f"💰 Exit Price: {current_price:.6f}\n"
            f"📈 Total Profit: {profit_pct:.2f}%\n"
            f"📦 Position: {position_context}\n"
            f"🎯 Strategy: {'50/50 TP1+Trail' if trade.get('tp1_hit') else 'Full Trail'}"
            f"{dca_info}"
        )
        
        # Log to activity file with appropriate result type
        from activity_logger import log_trade_to_file
        result_type = "trailing_sl_dca" if is_dca_trade else "trailing_sl_standard"
        
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=entry_price,
            sl=trade.get("trailing_sl"),
            tp1=trade.get("tp1_target"),
            tp2=None,
            result=result_type,
            score=trade.get("score_history", [0])[-1] if trade.get("score_history") else 0,
            trade_type=trade.get("trade_type", "Unknown"),
            confidence=0
        )
        
        write_log(f"TRAILING_SL_FINAL_EXIT: {symbol} | Type: {trade_context} | Price: {current_price} | Profit: {profit_pct:.2f}% | DCA_Count: {trade.get('dca_count', 0)}")
        
        return True
        
    except Exception as e:
        log(f"❌ Error executing trailing SL exit for {symbol}: {e}", level="ERROR")
        return False

# MAIN INTEGRATION FUNCTION - This is what you call from your monitor and scanner

async def universal_trade_monitoring(symbol, trade, current_price, direction, candles_by_tf=None):
    """
    Universal function to handle trailing stop monitoring for ALL trades (DCA and non-DCA)
    Call this from your monitor.py and active_trade_scanner.py
    """
    try:
        # Only handle trailing after TP1 is hit
        if not trade.get("tp1_hit"):
            return False
        
        # Skip if trade is already exited
        if trade.get("exited"):
            return False
        
        # Determine trade type for context
        is_dca_trade = trade.get("dca_count", 0) > 0
        
        # Check if trailing SL was hit first
        if await universal_check_trailing_sl_hit(symbol, trade, current_price, direction):
            # Execute the exit
            return await universal_execute_trailing_sl_exit(symbol, trade, current_price)
        
        # Update trailing stop if not hit
        return await universal_handle_trailing_stop(symbol, trade, current_price, direction)
        
    except Exception as e:
        trade_context = "DCA" if trade.get("dca_count", 0) > 0 else "Standard"
        log(f"❌ Error in universal trade monitoring for {symbol} ({trade_context}): {e}", level="ERROR")
        return False

# FUNCTIONS FOR UPDATING TRADES AFTER DCA (only used when DCA happens)

def update_trade_after_dca(trade, new_avg_entry, new_total_qty, new_sl, new_tp):
    """
    Update trade object after DCA - only called for DCA trades
    """
    try:
        # Update core trade data
        trade["entry_price"] = new_avg_entry  # This becomes the new effective entry
        trade["qty"] = new_total_qty
        
        # Reset trailing stop logic for DCA
        if trade.get("tp1_hit"):
            # If TP1 was already hit, maintain trailing from current level
            current_trailing = trade.get("trailing_sl")
            if not current_trailing:
                # Initialize trailing at breakeven with new average entry
                trade["trailing_sl"] = new_avg_entry
                log(f"🔄 DCA: Initialized trailing SL at new avg entry {new_avg_entry:.6f} for {trade.get('symbol', 'UNKNOWN')}")
        else:
            # Before TP1, update stop loss
            trade["original_sl"] = new_sl
        
        # Update TP levels with new average entry
        trade_type = trade.get("trade_type", "Intraday")
        fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
        
        if trade.get("direction", "").lower() == "long":
            new_tp1 = new_avg_entry * (1 + fixed_params["tp1_pct"] / 100)
        else:
            new_tp1 = new_avg_entry * (1 - fixed_params["tp1_pct"] / 100)
        
        trade["tp1_target"] = new_tp1
        
        log(f"✅ Trade updated after DCA:")
        log(f"   New Avg Entry: {new_avg_entry:.6f}")
        log(f"   New Total Qty: {new_total_qty}")
        log(f"   New TP1: {new_tp1:.6f}")
        log(f"   Trailing SL: {trade.get('trailing_sl', 'Not set')}")
        
        return True
        
    except Exception as e:
        log(f"❌ Error updating trade after DCA: {e}", level="ERROR")
        return False

# DEBUGGING AND VALIDATION FUNCTIONS

def debug_trade_state(symbol, trade, current_price):
    """
    Debug function to log trade state for troubleshooting - works for all trade types
    """
    try:
        is_dca_trade = trade.get("dca_count", 0) > 0
        trade_context = "DCA" if is_dca_trade else "Standard"
        
        log(f"🔍 DEBUG TRADE STATE for {symbol} ({trade_context}):")
        log(f"   Current Price: {current_price}")
        log(f"   Entry Price (Effective): {get_effective_entry_price(trade)}")
        log(f"   Direction: {trade.get('direction')}")
        log(f"   Trade Type: {trade.get('trade_type')}")
        log(f"   TP1 Hit: {trade.get('tp1_hit')}")
        log(f"   TP1 Target: {trade.get('tp1_target')}")
        log(f"   Trailing SL: {trade.get('trailing_sl')}")
        log(f"   Original SL: {trade.get('original_sl')}")
        log(f"   DCA Count: {trade.get('dca_count', 0)}")
        log(f"   Current Qty: {trade.get('qty')}")
        log(f"   Exited: {trade.get('exited')}")
        
        # Calculate profit status
        entry_price = get_effective_entry_price(trade)
        direction = trade.get('direction', '').lower()
        
        if entry_price and direction:
            if direction == 'long':
                profit_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                profit_pct = ((entry_price - current_price) / entry_price) * 100
            
            log(f"   Current P&L: {profit_pct:.2f}%")
            
            # Check trailing configuration
            trade_type = trade.get('trade_type', 'Intraday')
            trailing_pct = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES['Intraday'])['trailing_pct']
            log(f"   Expected Trailing %: {trailing_pct}%")
            
            # Position info
            remaining_qty, position_context = get_remaining_position_size(trade)
            log(f"   {position_context}: {remaining_qty}")
        
    except Exception as e:
        log(f"❌ Error in debug_trade_state: {e}")

def validate_trailing_stop_config():
    """
    Validate that trailing stop configuration is consistent across all files
    """
    log("🔍 Validating universal trailing stop configuration...")
    
    # Check that FIXED_PERCENTAGES are properly defined
    for trade_type, params in FIXED_PERCENTAGES.items():
        required_keys = ["tp1_pct", "sl_pct", "trailing_pct"]
        for key in required_keys:
            if key not in params:
                log(f"❌ Missing {key} in {trade_type} configuration", level="ERROR")
                return False
            if params[key] <= 0:
                log(f"❌ Invalid {key} value in {trade_type}: {params[key]}", level="ERROR")
                return False
    
    log("✅ Universal trailing stop configuration validated successfully")
    log("✅ System supports both DCA and non-DCA trades")
    return True

# TESTING FUNCTION

async def test_universal_trailing_functionality():
    """
    Test function to verify trailing stop fixes work for both DCA and non-DCA trades
    """
    try:
        log("🧪 Testing universal trailing stop functionality...")
        
        # Test 1: Standard (non-DCA) trade
        standard_trade = {
            "symbol": "BTCUSDT",
            "entry_price": 50000.0,
            "direction": "long",
            "trade_type": "Intraday",
            "tp1_hit": True,
            "tp1_target": 51000.0,
            "trailing_sl": 50000.0,
            "qty": 0.01,
            "dca_count": 0,  # No DCA
            "exited": False
        }
        
        # Test 2: DCA trade
        dca_trade = {
            "symbol": "ETHUSDT",
            "entry_price": 3500.0,  # This would be the averaged entry after DCA
            "direction": "long",
            "trade_type": "Intraday",
            "tp1_hit": True,
            "tp1_target": 3570.0,
            "trailing_sl": 3500.0,
            "qty": 0.02,
            "dca_count": 2,  # Has DCA
            "dca_history": [
                {"original_entry": 3600.0, "price": 3400.0},
                {"original_entry": 3600.0, "price": 3300.0}
            ],
            "exited": False
        }
        
        test_trades = [
            ("Standard Trade", standard_trade, 51500.0),
            ("DCA Trade", dca_trade, 3650.0)
        ]
        
        for test_name, test_trade, test_price in test_trades:
            log(f"📊 Testing {test_name} at price: {test_price}")
            
            result = await universal_trade_monitoring(
                test_trade["symbol"], test_trade, test_price, "long"
            )
            
            log(f"   Result: {result}")
            log(f"   New Trailing SL: {test_trade.get('trailing_sl')}")
            log("---")
        
        log("✅ Universal trailing stop test completed")
        return True
        
    except Exception as e:
        log(f"❌ Error in universal trailing stop test: {e}", level="ERROR")
        return False

# Main export - this is what your other files should import and use
__all__ = [
    'universal_trade_monitoring',           # Main function for monitor.py and active_trade_scanner.py
    'universal_handle_trailing_stop',       # Core trailing logic
    'universal_check_trailing_sl_hit',      # Check if SL hit
    'universal_execute_trailing_sl_exit',   # Execute exit
    'update_trade_after_dca',              # For DCA manager integration
    'debug_trade_state',                   # For debugging
    'validate_trailing_stop_config',       # For startup validation
    'test_universal_trailing_functionality' # For testing
]
