# auto_exit_handler.py
# Handler for automatically exiting trades when price moves past stop loss

import asyncio
from datetime import datetime
from logger import log
from bybit_api import signed_request
from error_handler import send_telegram_message

# Update your auto_exit_handler.py with these improvements

async def auto_exit_past_sl(symbol, trade, current_price, dca_fast_buffer=0.05):
    """
    Auto-exit trade when price moves past stop loss
    
    Args:
        symbol: Trading symbol
        trade: Trade object
        current_price: Current market price
        dca_fast_buffer: Buffer percentage (0.05 = 0.05%)
    
    Returns:
        bool: True if trade was exited, False otherwise
    """
    try:
        if trade.get("exited"):
            return False
            
        direction = trade.get("direction", "").lower()
        sl_price = trade.get("original_sl")
        
        if not sl_price:
            log(f"⚠️ {symbol}: No SL price found, cannot auto-exit")
            return False
        
        # Check if price crossed past SL with buffer
        crossed_sl = False
        
        if direction == "long":
            # Long position: price dropped below SL minus buffer
            threshold = sl_price * (1 - dca_fast_buffer / 100)
            crossed_sl = current_price <= threshold
        else:  # short
            # Short position: price rose above SL plus buffer
            threshold = sl_price * (1 + dca_fast_buffer / 100)
            crossed_sl = current_price >= threshold
        
        if crossed_sl:
            log(f"🚨 {symbol}: Price past SL - AUTO-EXITING")
            log(f"   Current: {current_price:.6f} | SL: {sl_price:.6f} | Threshold: {threshold:.6f}")
            
            # FIRST: Check if position still exists on exchange
            position_exists = await check_position_exists(symbol, trade)
            
            if not position_exists:
                log(f"✅ {symbol}: Position already closed on exchange, marking as exited")
                # Mark trade as exited in our system
                mark_trade_as_exited(symbol, trade, current_price, "position_already_closed")
                return True
            
            # Execute the exit if position still exists
            success = await execute_auto_exit(symbol, trade, current_price)
            
            if success:
                log(f"✅ {symbol}: Successfully auto-exited")
                return True
            else:
                log(f"❌ {symbol}: Auto-exit failed", level="ERROR")
                return False
        
        return False
        
    except Exception as e:
        log(f"❌ Error in auto_exit_past_sl for {symbol}: {e}", level="ERROR")
        return False

async def check_position_exists(symbol, trade):
    """
    Check if position still exists on the exchange
    """
    try:
        from bybit_api import signed_request
        
        position_resp = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "symbol": symbol,
            "settleCoin": "USDT"
        })
        
        if position_resp.get("retCode") == 0:
            positions = position_resp.get("result", {}).get("list", [])
            
            for pos in positions:
                if pos.get("symbol") == symbol:
                    size = float(pos.get("size", 0))
                    if abs(size) > 0:
                        return True
            
        return False
        
    except Exception as e:
        log(f"❌ Error checking position existence for {symbol}: {e}", level="ERROR")
        return False

def mark_trade_as_exited(symbol, trade, current_price, reason):
    """
    Mark trade as exited in our system without trying to place orders
    """
    try:
        # Calculate P&L
        entry_price = trade.get("entry_price")
        direction = trade.get("direction", "").lower()
        
        if direction == "long":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Update trade data
        trade["exited"] = True
        trade["exit_reason"] = reason
        trade["exit_price"] = current_price
        trade["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade["final_pnl_pct"] = pnl_pct
        trade["auto_exit"] = True
        
        # Remove manual review flags
        trade.pop("needs_manual_review", None)
        trade.pop("manual_review_required", None)
        
        # Save trade data
        from monitor import save_active_trades
        save_active_trades()
        
        log(f"✅ {symbol}: Marked as exited - {reason}")
        
        # Send notification
        asyncio.create_task(send_telegram_message(
            f"✅ <b>Trade Auto-Closed</b>\n"
            f"Symbol: {symbol}\n"
            f"Reason: {reason}\n"
            f"Price: {current_price:.6f}\n"
            f"P&L: {pnl_pct:.2f}%"
        ))
        
    except Exception as e:
        log(f"❌ Error marking trade as exited for {symbol}: {e}", level="ERROR")

async def execute_auto_exit(symbol, trade, current_price):
    """
    Execute the actual exit order (only if position exists)
    """
    try:
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        qty = trade.get("qty", 0)
        
        if qty <= 0:
            log(f"⚠️ {symbol}: No quantity to exit")
            return False
        
        # Calculate loss percentage
        if direction == "long":
            loss_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            loss_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Determine order side (opposite of position)
        order_side = "Sell" if direction == "long" else "Buy"
        
        # Place market order to exit
        exit_params = {
            "category": "linear",
            "symbol": symbol,
            "side": order_side,
            "orderType": "Market",
            "qty": str(qty),
            "reduceOnly": True,
            "timeInForce": "IOC"
        }
        
        log(f"🔄 {symbol}: Placing auto-exit order - {order_side} {qty} units")
        
        from bybit_api import signed_request
        exit_resp = await signed_request("POST", "/v5/order/create", exit_params)
        
        if exit_resp.get("retCode") == 0:
            order_id = exit_resp.get("result", {}).get("orderId")
            
            # Update trade data
            trade["exited"] = True
            trade["exit_reason"] = "auto_exit_past_sl"
            trade["exit_price"] = current_price
            trade["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trade["exit_order_id"] = order_id
            trade["final_pnl_pct"] = loss_pct
            trade["auto_exit"] = True
            
            # Remove manual review flags
            trade.pop("needs_manual_review", None)
            trade.pop("manual_review_required", None)
            
            # Cancel any existing orders
            await cancel_existing_orders(symbol, trade)
            
            # Save trade data
            from monitor import save_active_trades
            save_active_trades()
            
            # Send notification
            await send_telegram_message(
                f"🚨 <b>Auto-Exit Executed</b>\n"
                f"Symbol: {symbol}\n"
                f"Reason: Price moved past SL\n"
                f"Exit Price: {current_price:.6f}\n"
                f"P&L: {loss_pct:.2f}%\n"
                f"Order ID: {order_id}"
            )
            
            log(f"✅ {symbol}: Auto-exit completed - Order ID: {order_id}")
            return True
            
        else:
            error_msg = exit_resp.get("retMsg", "Unknown error")
            log(f"❌ {symbol}: Auto-exit failed - {error_msg}", level="ERROR")
            
            # If the error is about position not existing, mark as closed
            if "position" in error_msg.lower() and "zero" in error_msg.lower():
                mark_trade_as_exited(symbol, trade, current_price, "position_already_closed")
                return True
            
            return False
            
    except Exception as e:
        log(f"❌ Error executing auto-exit for {symbol}: {e}", level="ERROR")
        return False

async def cancel_existing_orders(symbol, trade):
    """Cancel existing stop loss and take profit orders"""
    try:
        from bybit_api import signed_request
        
        # Cancel stop loss order
        sl_order_id = trade.get("sl_order_id")
        if sl_order_id:
            cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                "category": "linear",
                "symbol": symbol,
                "orderId": sl_order_id
            })
            
            if cancel_resp.get("retCode") == 0:
                log(f"✅ {symbol}: Cancelled SL order {sl_order_id}")
            else:
                log(f"⚠️ {symbol}: Could not cancel SL order - {cancel_resp.get('retMsg')}")
        
        # Cancel take profit orders
        tp_order_id = trade.get("tp1_order_id")
        if tp_order_id:
            cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                "category": "linear",
                "symbol": symbol,
                "orderId": tp_order_id
            })
            
            if cancel_resp.get("retCode") == 0:
                log(f"✅ {symbol}: Cancelled TP order {tp_order_id}")
        
        # Cancel all remaining orders for this symbol as backup
        await signed_request("POST", "/v5/order/cancel-all", {
            "category": "linear",
            "symbol": symbol
        })
        
    except Exception as e:
        log(f"❌ Error cancelling orders for {symbol}: {e}", level="ERROR")
