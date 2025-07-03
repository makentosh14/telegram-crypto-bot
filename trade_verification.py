#!/usr/bin/env python3
"""
Fixed Position Verification System for Trading Bot
Addresses the XEMUSDT disappearance issue by implementing safer verification logic
"""

import asyncio
import traceback
from datetime import datetime
from logger import log, write_log
from error_handler import send_telegram_message

async def verify_position_and_orders(symbol, trade, auto_repair=True):
    """
    FIXED: Safer position verification that won't accidentally mark valid trades as exited
    
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
        "direction_matches": False,
        "sl_order_exists": False,
        "sl_price_matches": False,
        "issues_detected": [],
        "repairs_attempted": [],
        "repairs_successful": [],
        "manual_review_required": []
    }
    
    if not trade or trade.get("exited"):
        result["position_exists"] = False
        result["issues_detected"].append("Trade marked as exited")
        return result
    
    # 1. Verify position exists and matches trade data
    try:
        from bybit_api import signed_request
        
        position_resp = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "symbol": symbol,
            "settleCoin": "USDT"
        })
        
        if position_resp.get("retCode") == 0:
            positions = position_resp.get("result", {}).get("list", [])
            
            # Check if position exists
            position_exists = False
            position_size = 0
            position_side = None
            position_data = None
            
            for pos in positions:
                if pos.get("symbol") == symbol:
                    size = float(pos.get("size", 0))
                    if abs(size) > 0:
                        position_exists = True
                        position_size = abs(size)
                        # Convert Bybit position side to our format
                        bybit_side = pos.get("side", "")
                        position_side = "long" if bybit_side == "Buy" else "short"
                        position_data = pos
                        break
            
            result["position_exists"] = position_exists
            
            # FIXED: Don't immediately mark as exited - be more careful
            if not position_exists:
                result["issues_detected"].append("Position not found on exchange")
                
                # SAFER APPROACH: Track consecutive failures instead of immediate exit
                if "verification_failures" not in trade:
                    trade["verification_failures"] = 0
                
                trade["verification_failures"] += 1
                trade["last_verification_fail"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if auto_repair:
                    if trade["verification_failures"] >= 3:
                        # Only after 3 consecutive failures, and with manual review flag
                        result["manual_review_required"].append(
                            f"Position not found for {trade['verification_failures']} consecutive checks"
                        )
                        result["repairs_attempted"].append("Flagged for manual review")
                        
                        # DON'T auto-exit, just flag
                        trade["needs_manual_review"] = True
                        
                        # Send alert but don't exit
                        await send_telegram_message(
                            f"🚨 <b>Manual Review Required</b>\n"
                            f"Symbol: {symbol}\n"
                            f"Issue: Position not found for {trade['verification_failures']} consecutive checks\n"
                            f"Action: Flagged for manual review (not auto-exited)"
                        )
                        
                        log(f"🚨 {symbol}: Flagged for manual review after {trade['verification_failures']} failures")
                    else:
                        result["repairs_attempted"].append(f"Tracking failure #{trade['verification_failures']}")
                        log(f"⚠️ {symbol}: Position not found (failure #{trade['verification_failures']}/3)")
                
                return result
            else:
                # Reset failure counter if position found
                if "verification_failures" in trade:
                    del trade["verification_failures"]
                if "last_verification_fail" in trade:
                    del trade["last_verification_fail"]
            
            # Check if position size matches (with tolerance)
            expected_size = trade.get("qty", 0)
            size_tolerance = max(0.01, expected_size * 0.001)  # 0.1% tolerance or 0.01 minimum
            size_matches = abs(position_size - expected_size) <= size_tolerance
            result["position_size_matches"] = size_matches
            
            # Check if direction matches (with better normalization)
            expected_direction = trade.get("direction", "").lower()
            direction_matches = position_side == expected_direction
            result["direction_matches"] = direction_matches
            
            # FIXED: More careful size mismatch handling
            if not size_matches:
                size_diff = abs(position_size - expected_size)
                size_diff_pct = (size_diff / expected_size) * 100 if expected_size > 0 else 0
                
                result["issues_detected"].append(
                    f"Position size mismatch: expected {expected_size}, found {position_size} "
                    f"(diff: {size_diff:.4f}, {size_diff_pct:.2f}%)"
                )
                
                if auto_repair:
                    # Only auto-fix if difference is small (< 5%)
                    if size_diff_pct < 5.0:
                        result["repairs_attempted"].append("Update trade position size to match exchange")
                        trade["qty"] = position_size
                        from monitor import save_active_trades
                        save_active_trades()
                        result["repairs_successful"].append(f"Updated position size to {position_size}")
                        log(f"🔧 {symbol}: Updated position size {expected_size} → {position_size}")
                    else:
                        # Large difference - flag for manual review
                        result["manual_review_required"].append(
                            f"Large position size difference ({size_diff_pct:.2f}%)"
                        )
                        trade["needs_manual_review"] = True
                        log(f"🚨 {symbol}: Large size difference - flagged for manual review")
            
            # FIXED: More careful direction mismatch handling
            if not direction_matches:
                result["issues_detected"].append(
                    f"Position direction mismatch: expected {expected_direction}, found {position_side}"
                )
                
                if auto_repair:
                    # DON'T auto-exit for direction mismatch - this is likely the XEMUSDT issue
                    # Instead, flag for manual review
                    result["manual_review_required"].append(
                        f"Direction mismatch: expected {expected_direction}, found {position_side}"
                    )
                    trade["needs_manual_review"] = True
                    trade["direction_mismatch_detected"] = True
                    
                    # Send alert for manual review
                    await send_telegram_message(
                        f"🚨 <b>Direction Mismatch Alert</b>\n"
                        f"Symbol: {symbol}\n"
                        f"Expected: {expected_direction}\n"
                        f"Found: {position_side}\n"
                        f"Action: Flagged for manual review (not auto-exited)"
                    )
                    
                    log(f"🚨 {symbol}: Direction mismatch - flagged for manual review")
                    
                    # Store actual position data for manual review
                    trade["actual_position_data"] = {
                        "size": position_size,
                        "side": position_side,
                        "avg_price": float(position_data.get("avgPrice", 0)),
                        "unrealized_pnl": float(position_data.get("unrealisedPnl", 0))
                    }
            
        else:
            result["issues_detected"].append(f"Failed to fetch position: {position_resp.get('retMsg')}")
    
    except Exception as e:
        result["issues_detected"].append(f"Error checking position: {str(e)}")
        log(f"❌ Position verification error for {symbol}: {str(e)}", level="ERROR")
    
    # 2. Verify stop-loss order (if applicable)
    sl_order_id = trade.get("sl_order_id")
    if sl_order_id:
        try:
            sl_resp = await signed_request("GET", "/v5/order/realtime", {
                "category": "linear",
                "symbol": symbol,
                "orderId": sl_order_id
            })
            
            if sl_resp.get("retCode") == 0:
                orders = sl_resp.get("result", {}).get("list", [])
                sl_order_exists = len(orders) > 0
                result["sl_order_exists"] = sl_order_exists
                
                if sl_order_exists:
                    sl_order = orders[0]
                    trigger_price = float(sl_order.get("triggerPrice", 0))
                    expected_sl = trade.get("sl", 0)
                    
                    if expected_sl > 0:
                        sl_tolerance = expected_sl * 0.005  # 0.5% tolerance
                        sl_matches = abs(trigger_price - expected_sl) <= sl_tolerance
                        result["sl_price_matches"] = sl_matches
                        
                        if not sl_matches:
                            result["issues_detected"].append(
                                f"SL price mismatch: expected {expected_sl}, found {trigger_price}"
                            )
                else:
                    result["issues_detected"].append("SL order not found")
            else:
                result["issues_detected"].append(f"Failed to fetch SL order: {sl_resp.get('retMsg')}")
        
        except Exception as e:
            result["issues_detected"].append(f"Error checking SL order: {str(e)}")
    
    # Log verification results with better categorization
    if result["manual_review_required"]:
        log(f"🚨 {symbol}: Manual review required - {len(result['manual_review_required'])} issues", level="WARN")
        for issue in result["manual_review_required"]:
            log(f"   - {issue}", level="WARN")
    
    if result["issues_detected"]:
        issue_count = len(result["issues_detected"])
        repair_count = len(result["repairs_successful"])
        manual_count = len(result["manual_review_required"])
        
        log(f"⚠️ Position verification for {symbol}: {issue_count} issues, {repair_count} repaired, {manual_count} flagged", level="WARN")
        
        # Only send Telegram for critical issues that couldn't be auto-fixed
        unresolved_issues = issue_count - repair_count
        if auto_repair and unresolved_issues > 0:
            await send_telegram_message(
                f"⚠️ <b>Trade Verification Report</b> for {symbol}\n"
                f"Issues: {issue_count}\n"
                f"Auto-fixed: {repair_count}\n"
                f"Manual review: {manual_count}\n"
                f"Unresolved: {unresolved_issues}"
            )
    else:
        log(f"✅ Position verification for {symbol}: All checks passed")
    
    return result

def recover_missing_trades():
    """
    Recovery function to restore trades that were incorrectly marked as exited
    """
    log("🔄 Starting trade recovery process...")
    
    try:
        # Load both active trades and the persisted file
        from monitor import active_trades, PERSIST_PATH
        import json
        import os
        
        if not os.path.exists(PERSIST_PATH):
            log("❌ No persisted trades file found")
            return
        
        with open(PERSIST_PATH, 'r') as f:
            all_trades = json.load(f)
        
        # Find trades marked as exited that might need recovery
        potentially_recoverable = []
        
        for symbol, trade in all_trades.items():
            if trade.get("exited") and trade.get("needs_manual_review"):
                potentially_recoverable.append((symbol, trade))
        
        log(f"🔍 Found {len(potentially_recoverable)} potentially recoverable trades")
        
        for symbol, trade in potentially_recoverable:
            log(f"🔄 Checking {symbol} for recovery...")
            
            # Check if position still exists on exchange
            from bybit_api import signed_request
            import asyncio
            
            async def check_position():
                try:
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
                                    # Position exists! Recover the trade
                                    log(f"✅ Recovering {symbol} - position found on exchange")
                                    
                                    # Restore to active trades
                                    trade["exited"] = False
                                    trade["recovered"] = True
                                    trade["recovery_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    
                                    # Update position data
                                    trade["qty"] = abs(size)
                                    bybit_side = pos.get("side", "")
                                    trade["direction"] = "long" if bybit_side == "Buy" else "short"
                                    
                                    active_trades[symbol] = trade
                                    
                                    # Send recovery notification
                                    await send_telegram_message(
                                        f"✅ <b>Trade Recovered</b>\n"
                                        f"Symbol: {symbol}\n"
                                        f"Direction: {trade['direction']}\n"
                                        f"Size: {trade['qty']}\n"
                                        f"Status: Restored to active monitoring"
                                    )
                                    
                                    return True
                    
                    log(f"❌ {symbol}: No position found on exchange")
                    return False
                    
                except Exception as e:
                    log(f"❌ Error checking {symbol}: {e}")
                    return False
            
            # Run the async check
            loop = asyncio.get_event_loop()
            recovered = loop.run_until_complete(check_position())
            
            if recovered:
                log(f"✅ Successfully recovered {symbol}")
            
        # Save updated active trades
        from monitor import save_active_trades
        save_active_trades()
        
        log("✅ Trade recovery process completed")
        
    except Exception as e:
        log(f"❌ Error in trade recovery: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")

def generate_manual_review_report():
    """
    Generate a report of all trades requiring manual review
    """
    try:
        from monitor import active_trades
        
        manual_review_trades = []
        
        for symbol, trade in active_trades.items():
            if trade.get("needs_manual_review"):
                manual_review_trades.append({
                    "symbol": symbol,
                    "direction": trade.get("direction"),
                    "qty": trade.get("qty"),
                    "entry_price": trade.get("entry_price"),
                    "issues": trade.get("manual_review_required", []),
                    "timestamp": trade.get("timestamp")
                })
        
        if manual_review_trades:
            log(f"📋 Manual Review Report - {len(manual_review_trades)} trades need attention:")
            for trade in manual_review_trades:
                log(f"   {trade['symbol']}: {trade['direction']} {trade['qty']} @ {trade['entry_price']}")
                for issue in trade.get("issues", []):
                    log(f"      - {issue}")
        else:
            log("✅ No trades requiring manual review")
            
        return manual_review_trades
        
    except Exception as e:
        log(f"❌ Error generating manual review report: {e}", level="ERROR")
        return []

# Example usage and testing
if __name__ == "__main__":
    # Test the recovery function
    print("Testing trade recovery...")
    recover_missing_trades()
    
    # Generate manual review report
    print("\nGenerating manual review report...")
    generate_manual_review_report()
