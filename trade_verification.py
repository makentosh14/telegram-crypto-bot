import asyncio
import traceback
from datetime import datetime
from logger import log, write_log
from error_handler import send_telegram_message

async def verify_position_and_orders(symbol, trade, auto_repair=True):
    """
    Comprehensive verification of position and order status
    
    Args:
        symbol: Trading symbol
        trade: Trade object from active_trades
        auto_repair: Whether to automatically fix any issues
        
    Returns:
        dict: Verification results and actions taken
    """
    result = {
        "symbol": symbol,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "position_exists": False,
        "position_size_matches": False,
        "sl_order_exists": False,
        "sl_price_matches": False,
        "issues_detected": [],
        "repairs_attempted": [],
        "repairs_successful": []
    }
    
    if not trade or trade.get("exited"):
        result["position_exists"] = False
        result["issues_detected"].append("Trade marked as exited")
        return result
    
    # 1. Verify position exists and size matches
    try:
        from bybit_api import signed_request
        
        position_resp = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "symbol": symbol
        })
        
        if position_resp.get("retCode") == 0:
            positions = position_resp.get("result", {}).get("list", [])
            
            # Check if position exists
            position_exists = False
            position_size = 0
            position_side = None
            
            for pos in positions:
                if pos.get("symbol") == symbol:
                    size = float(pos.get("size", 0))
                    if abs(size) > 0:
                        position_exists = True
                        position_size = abs(size)
                        position_side = "long" if size > 0 else "short"
                        break
            
            result["position_exists"] = position_exists
            
            # If position doesn't exist but should
            if not position_exists:
                result["issues_detected"].append("Position doesn't exist on exchange but trade is active")
                
                if auto_repair:
                    result["repairs_attempted"].append("Mark trade as exited - position not found")
                    trade["exited"] = True
                    from monitor import save_active_trades
                    save_active_trades()
                    result["repairs_successful"].append("Marked trade as exited")
                
                return result
            
            # Check if position size matches
            expected_size = trade.get("qty", 0)
            size_matches = abs(position_size - expected_size) < 0.000001
            result["position_size_matches"] = size_matches
            
            # Check if direction matches
            expected_direction = trade.get("direction", "").lower()
            direction_matches = position_side == expected_direction
            result["direction_matches"] = direction_matches
            
            if not size_matches:
                result["issues_detected"].append(f"Position size mismatch: expected {expected_size}, found {position_size}")
                
                if auto_repair:
                    result["repairs_attempted"].append("Update trade position size to match exchange")
                    trade["qty"] = position_size
                    from monitor import save_active_trades
                    save_active_trades()
                    result["repairs_successful"].append(f"Updated position size to {position_size}")
            
            if not direction_matches:
                result["issues_detected"].append(f"Position direction mismatch: expected {expected_direction}, found {position_side}")
                
                if auto_repair:
                    result["repairs_attempted"].append("Mark trade as exited - direction mismatch")
                    trade["exited"] = True
                    from monitor import save_active_trades
                    save_active_trades()
                    result["repairs_successful"].append("Marked trade as exited due to direction mismatch")
            
        else:
            result["issues_detected"].append(f"Failed to fetch position: {position_resp.get('retMsg')}")
    
    except Exception as e:
        result["issues_detected"].append(f"Error checking position: {str(e)}")
    
    # 2. Verify stop loss order status
    try:
        from bybit_api import signed_request, check_order_exists
        
        sl_order_id = trade.get("sl_order_id")
        
        if not sl_order_id:
            result["issues_detected"].append("No SL order ID in trade object")
            
            if auto_repair and result["position_exists"]:
                result["repairs_attempted"].append("Recreate SL order")
                
                # Recreate SL order
                from bybit_api import place_stop_loss
                
                # Determine SL price
                sl_price = trade.get("trailing_sl")
                if not sl_price:
                    sl_price = trade.get("original_sl")
                if not sl_price:
                    sl_price = trade.get("entry_price")  # Fallback to breakeven
                
                if sl_price:
                    direction = trade.get("direction", "").lower()
                    qty = trade.get("qty", 0)
                    
                    sl_result = await place_stop_loss(
                        symbol=symbol,
                        direction=direction,
                        qty=qty,
                        sl_price=sl_price
                    )
                    
                    if sl_result.get("retCode") == 0:
                        new_sl_order_id = sl_result.get("result", {}).get("orderId")
                        trade["sl_order_id"] = new_sl_order_id
                        from monitor import save_active_trades
                        save_active_trades()
                        result["repairs_successful"].append(f"Created new SL order: {new_sl_order_id} at {sl_price}")
                    else:
                        result["issues_detected"].append(f"Failed to create SL order: {sl_result.get('retMsg')}")
        
        else:
            # Check if SL order exists
            sl_exists = await check_order_exists(sl_order_id, symbol)
            result["sl_order_exists"] = sl_exists
            
            if not sl_exists:
                result["issues_detected"].append(f"SL order {sl_order_id} not found on exchange")
                
                if auto_repair and result["position_exists"]:
                    result["repairs_attempted"].append("Recreate missing SL order")
                    
                    # Recreate SL order
                    from bybit_api import place_stop_loss
                    
                    # Determine SL price
                    sl_price = trade.get("trailing_sl")
                    if not sl_price:
                        sl_price = trade.get("original_sl")
                    if not sl_price:
                        sl_price = trade.get("entry_price")  # Fallback to breakeven
                    
                    if sl_price:
                        direction = trade.get("direction", "").lower()
                        qty = trade.get("qty", 0)
                        
                        sl_result = await place_stop_loss(
                            symbol=symbol,
                            direction=direction,
                            qty=qty,
                            sl_price=sl_price
                        )
                        
                        if sl_result.get("retCode") == 0:
                            new_sl_order_id = sl_result.get("result", {}).get("orderId")
                            trade["sl_order_id"] = new_sl_order_id
                            from monitor import save_active_trades
                            save_active_trades()
                            result["repairs_successful"].append(f"Created new SL order: {new_sl_order_id} at {sl_price}")
                        else:
                            result["issues_detected"].append(f"Failed to create SL order: {sl_result.get('retMsg')}")
            
    except Exception as e:
        result["issues_detected"].append(f"Error checking SL order: {str(e)}")
    
    # Log verification results
    if result["issues_detected"]:
        issue_count = len(result["issues_detected"])
        repair_count = len(result["repairs_successful"])
        log(f"⚠️ Position verification for {symbol}: {issue_count} issues found, {repair_count} repaired", level="WARN")
        
        # Send Telegram alert for critical issues
        if auto_repair and len(result["issues_detected"]) > len(result["repairs_successful"]):
            await send_telegram_message(
                f"⚠️ <b>Trade Verification Alert</b> for {symbol}\n"
                f"Issues: {issue_count}, Repaired: {repair_count}\n"
                f"Remaining issues: {', '.join(set(result['issues_detected']) - set(result['repairs_successful']))}"
            )
    else:
        log(f"✅ Position verification for {symbol}: All checks passed")
    
    return result

async def verify_all_positions(frequency_minutes=15):
    """
    Periodic verification of all active positions
    """
    from monitor import active_trades
    
    while True:
        try:
            log("🔍 Starting comprehensive position verification")
            
            for symbol, trade in active_trades.items():
                if trade.get("exited"):
                    continue
                
                # Verify this position and orders
                await verify_position_and_orders(symbol, trade, auto_repair=True)
                
                # Brief pause to avoid rate limits
                await asyncio.sleep(0.5)
            
            log("✅ Position verification cycle complete")
            
        except Exception as e:
            log(f"❌ Error in position verification: {e}", level="ERROR")
            log(traceback.format_exc(), level="ERROR")
        
        # Wait for next cycle
        await asyncio.sleep(frequency_minutes * 60)
