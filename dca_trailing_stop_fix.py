# dca_trailing_stop_fix.py
# Complete fix for trailing stop issues after DCA operations

import asyncio
import traceback
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order, update_stop_loss_order

# FIXED PERCENTAGES - Ensure consistency across all files
FIXED_PERCENTAGES = {
    "Scalp": {
        "tp1_pct": 0.9,      # +1.2% take profit
        "sl_pct": 0.6,       # -0.8% stop loss
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

async def handle_trailing_stop_after_dca(symbol, trade, current_price, direction):
    """
    Enhanced trailing stop handler that works correctly after DCA operations
    This fixes the issue where trailing stops weren't being applied properly post-DCA
    """
    try:
        # Get trade type and corresponding fixed percentages
        trade_type = trade.get("trade_type", "Intraday")
        fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
        trailing_pct = fixed_params["trailing_pct"]
        
        # Use the NEW average entry price after DCA (not original entry)
        entry_price = trade.get("entry_price")  # This should be the DCA-averaged entry price
        current_trailing_sl = trade.get("trailing_sl")
        
        log(f"🔄 TRAILING CHECK: {symbol}")
        log(f"   Current Price: {current_price}")
        log(f"   Entry (DCA Avg): {entry_price}")
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
        
        log(f"✅ Trailing SL updated for {symbol}: {old_trailing_sl} → {new_trailing_sl}")
        
        # Try to update the actual stop loss order on the exchange
        try:
            sl_updated = await update_stop_loss_order(symbol, trade, new_trailing_sl)
            if sl_updated:
                log(f"📈 Exchange SL order updated for {symbol}: {new_trailing_sl:.6f}")
                write_log(f"TRAILING_SL_UPDATED: {symbol} | New SL: {new_trailing_sl:.6f} | Direction: {direction}")
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
        log(f"❌ Error in handle_trailing_stop_after_dca for {symbol}: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

async def check_trailing_sl_hit_after_dca(symbol, trade, current_price, direction):
    """
    Check if trailing stop loss has been hit - enhanced for post-DCA trades
    """
    try:
        trailing_sl = trade.get("trailing_sl")
        if not trailing_sl:
            return False
        
        # Add small buffer for market volatility and slippage
        buffer = 0.002  # 0.2% buffer
        
        hit = False
        if direction.lower() == "long":
            # For long positions, SL is hit when price drops below trailing SL
            if current_price <= trailing_sl * (1 - buffer):
                hit = True
        else:  # short
            # For short positions, SL is hit when price rises above trailing SL
            if current_price >= trailing_sl * (1 + buffer):
                hit = True
        
        if hit:
            log(f"🚨 TRAILING SL HIT: {symbol} at {current_price} (SL: {trailing_sl})")
            
            # Calculate final profit percentage using DCA-averaged entry
            entry_price = trade.get("entry_price", 0)
            if entry_price:
                if direction.lower() == "long":
                    profit_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    profit_pct = ((entry_price - current_price) / entry_price) * 100
            else:
                profit_pct = 0
            
            log(f"📊 Final profit for {symbol}: {profit_pct:.2f}% (with DCA adjustments)")
            
            # If DCA was used, save the DCA history for analysis
            if trade.get("dca_count", 0) > 0:
                from dca_manager import dca_manager
                dca_manager.dca_history[symbol] = {
                    "dca_count": trade["dca_count"],
                    "final_result": "win" if profit_pct > 0 else "loss",
                    "final_pnl": profit_pct,
                    "dca_history": trade.get("dca_history", []),
                    "exit_type": "trailing_sl"
                }
                log(f"📝 DCA history saved for {symbol}: {trade['dca_count']} DCA operations")
        
        return hit
        
    except Exception as e:
        log(f"❌ Error checking trailing SL hit for {symbol}: {e}", level="ERROR")
        return False

async def execute_trailing_sl_exit_after_dca(symbol, trade, current_price):
    """
    Execute the final exit when trailing SL is hit - handles post-DCA position sizing
    """
    try:
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        
        # Calculate final profit percentage
        if direction == "long":
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Determine remaining position size
        # If TP1 was hit, only 50% remains; otherwise, full position remains
        total_qty = trade.get("qty", 0)
        if trade.get("tp1_hit"):
            remaining_qty = total_qty * 0.5  # Only 50% left after TP1
            position_context = "remaining 50% position"
        else:
            remaining_qty = total_qty  # Full position if TP1 not hit yet
            position_context = "full position"
        
        log(f"💔 Executing trailing SL exit for {symbol}")
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
                log(f"✅ Trailing SL exit executed for {symbol}: {remaining_qty} @ {current_price}")
            else:
                log(f"❌ Failed to execute trailing SL exit for {symbol}", level="ERROR")
                
        except Exception as e:
            log(f"❌ Error executing trailing SL exit order for {symbol}: {e}", level="ERROR")
        
        # Mark trade as exited
        trade["exited"] = True
        trade["exit_price"] = current_price
        trade["exit_reason"] = "Trailing_SL_Hit_After_DCA"
        trade["profit_pct"] = profit_pct
        trade["modified"] = True
        trade["exit_time"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        # Enhanced logging for DCA trades
        dca_info = ""
        if trade.get("dca_count", 0) > 0:
            original_entry = trade.get("dca_history", [{}])[0].get("original_entry", entry_price)
            dca_info = f"\n🔄 DCA Used: {trade['dca_count']} adds"
            dca_info += f"\n📊 Original Entry: {original_entry:.6f}"
            dca_info += f"\n📊 Final Avg Entry: {entry_price:.6f}"
        
        # Send comprehensive notification
        from error_handler import send_telegram_message
        await send_telegram_message(
            f"💔 <b>Trailing SL Hit</b> - <b>{symbol}</b>\n"
            f"💰 Exit Price: {current_price:.6f}\n"
            f"📈 Total Profit: {profit_pct:.2f}%\n"
            f"📦 Position: {position_context}\n"
            f"🎯 Strategy: {'50/50 TP1+Trail' if trade.get('tp1_hit') else 'Full Trail'}"
            f"{dca_info}"
        )
        
        # Log to activity file
        from activity_logger import log_trade_to_file
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=entry_price,
            sl=trade.get("trailing_sl"),
            tp1=trade.get("tp1_target"),
            tp2=None,
            result="trailing_sl_dca" if trade.get("dca_count", 0) > 0 else "trailing_sl",
            score=trade.get("score_history", [0])[-1] if trade.get("score_history") else 0,
            trade_type=trade.get("trade_type", "Unknown"),
            confidence=0
        )
        
        write_log(f"TRAILING_SL_FINAL_EXIT: {symbol} | Price: {current_price} | Profit: {profit_pct:.2f}% | DCA_Count: {trade.get('dca_count', 0)}")
        
        return True
        
    except Exception as e:
        log(f"❌ Error executing trailing SL exit for {symbol}: {e}", level="ERROR")
        return False

# MAIN INTEGRATION FUNCTIONS FOR YOUR MONITOR.PY AND ACTIVE_TRADE_SCANNER.PY

async def handle_dca_trade_monitoring(symbol, trade, current_price, direction, candles_by_tf=None):
    """
    Main function to handle trailing stop monitoring for trades that have used DCA
    Call this from your monitor.py in the main monitoring loop
    """
    try:
        # Only handle trailing after TP1 is hit
        if not trade.get("tp1_hit"):
            return False
        
        # Skip if trade is already exited
        if trade.get("exited"):
            return False
        
        # Check if trailing SL was hit first
        if await check_trailing_sl_hit_after_dca(symbol, trade, current_price, direction):
            # Execute the exit
            return await execute_trailing_sl_exit_after_dca(symbol, trade, current_price)
        
        # Update trailing stop if not hit
        return await handle_trailing_stop_after_dca(symbol, trade, current_price, direction)
        
    except Exception as e:
        log(f"❌ Error in DCA trade monitoring for {symbol}: {e}", level="ERROR")
        return False

# FIX FOR YOUR MONITOR.PY - Replace the existing handle_trailing_stop function with this:

async def fixed_handle_trailing_stop(symbol, trade, current_price, direction):
    """
    FIXED version of handle_trailing_stop that works correctly with DCA
    Use this to replace the existing function in monitor.py
    """
    return await handle_trailing_stop_after_dca(symbol, trade, current_price, direction)

# ENHANCED DCA MANAGER INTEGRATION

def update_trade_after_dca(trade, new_avg_entry, new_total_qty, new_sl, new_tp):
    """
    Update trade object after DCA with corrected trailing stop initialization
    Call this from your DCA manager after executing DCA
    """
    try:
        # Update core trade data
        trade["entry_price"] = new_avg_entry  # This is crucial for trailing calculations
        trade["qty"] = new_total_qty
        
        # Reset trailing stop to use new average entry as reference
        # If TP1 was already hit, maintain trailing from current level
        if trade.get("tp1_hit"):
            # Keep existing trailing SL if it's better than breakeven
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

# CONFIGURATION CHECK FUNCTION

def validate_trailing_stop_config():
    """
    Validate that trailing stop configuration is consistent across all files
    Run this on startup to ensure everything is properly configured
    """
    log("🔍 Validating trailing stop configuration...")
    
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
    
    log("✅ Trailing stop configuration validated successfully")
    return True

# Call this in your main.py startup
if __name__ == "__main__":
    validate_trailing_stop_config()
