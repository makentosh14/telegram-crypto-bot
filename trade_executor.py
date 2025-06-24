"""
Enhanced Trade Executor - Fixed Position Sizing and Balance Issues
Handles position sizing, execution and risk management with advanced features
"""
import asyncio
import json
import traceback
import time
from datetime import datetime

# Core imports
from bybit_api import signed_request, get_futures_available_balance, place_stop_loss, place_stop_loss_with_retry
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log, write_log
from error_handler import send_telegram_message, send_error_to_telegram
from activity_logger import log_trade_to_file
from symbol_info import round_qty, symbol_precisions, get_precision
from pre_trade_validator import pre_trade_validator
from stealth_detector import detect_stealth_accumulation_advanced
from range_break_detector import range_break_detector
from exit_manager import calculate_range_based_exit_levels

# Enhanced imports from position_manager.py
from risk_manager import (
    calculate_position_size,
    update_strategy_performance,
    check_trading_allowed,
    reset_daily_risk,
    load_risk_state,
    register_trade_risk
)

# Enhanced SL/TP utilities
from sl_tp_utils import (
    calculate_dynamic_sl_tp as enhanced_calculate_dynamic_sl_tp,
    calculate_exit_tranches,
    validate_sl_placement
)

# Other utilities
from atr import calculate_atr
from volume import get_average_volume
from exit_manager import detect_momentum_surge

# Cache for account balance to avoid excessive API calls
_cached_balance = None
_balance_timestamp = 0
_balance_cache_ttl = 30  # 30 seconds TTL for balance cache

# Execution states for retry logic
EXECUTION_STATES = {}

def calculate_quantity(symbol, raw_qty):
    """Calculate and validate position quantity with minimum requirements"""
    if raw_qty <= 0:
        return 0
    min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
    rounded_qty = round_qty(symbol, raw_qty)
    if rounded_qty < min_qty:
        return 0
    return rounded_qty

async def get_account_balance():
    """
    Get account balance with caching to reduce API calls
    Enhanced version from position_manager.py
    """
    global _cached_balance, _balance_timestamp
    
    # Use cached balance if it's recent enough
    current_time = time.time()
    if _cached_balance is not None and current_time - _balance_timestamp < _balance_cache_ttl:
        log(f"💰 Using cached balance: {_cached_balance} USDT (cached {int(current_time - _balance_timestamp)}s ago)")
        return _cached_balance
    
    # Fetch fresh balance
    try:
        usdt_balance = await get_futures_available_balance()
        
        if usdt_balance > 0:
            _cached_balance = usdt_balance
            _balance_timestamp = current_time
            log(f"💰 Fetched fresh balance: {usdt_balance} USDT")
            return usdt_balance
        else:
            log(f"⚠️ Invalid balance returned: {usdt_balance}", level="WARN")
            if _cached_balance is not None:
                log(f"💰 Using last known balance: {_cached_balance} USDT")
                return _cached_balance
            return 0
            
    except Exception as e:
        log(f"❌ Failed to get wallet balance: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        
        # Use cached balance as fallback if available
        if _cached_balance is not None:
            log(f"💰 Using last known balance due to error: {_cached_balance} USDT")
            return _cached_balance
        
        return 0

async def get_symbol_price(symbol, category="linear"):
    try:
        resp = await signed_request("GET", "/v5/market/tickers", {
            "category": category,
            "symbol": symbol
        })
        if resp.get("retCode") == 0:
            return float(resp["result"]["list"][0]["lastPrice"])
    except:
        pass
    return 0

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending", trend_context=None):
    """
    Use only enhanced SL/TP logic from sl_tp_utils. Fail if unavailable.
    """
    try:
        return enhanced_calculate_dynamic_sl_tp(
            candles_by_tf=candles_by_tf,
            entry_price=price,
            trade_type=trade_type,
            direction=direction,
            score=score,
            confidence=confidence,
            regime=regime
        )
    except Exception as e:
        log(f"❌ Error in dynamic SL/TP calculation: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        
        # Fallback to basic calculation
        price = float(price)
        sl_pct = 0.008 if trade_type == "Scalp" else 0.015 if trade_type == "Intraday" else 0.02
        tp_pct = sl_pct * 1.5
        
        if direction.lower() == "long":
            sl_price = price * (1 - sl_pct)
            tp_price = price * (1 + tp_pct)
        else:
            sl_price = price * (1 + sl_pct)
            tp_price = price * (1 - tp_pct)
        
        return sl_price, tp_price, sl_pct, 0.005, tp_pct

async def calculate_enhanced_quantity(symbol, price, sl_price, account_balance, 
                                    candles_by_tf, trade_type, strategy, confidence,
                                    risk_pct=None, market_type="linear"):
    """
    FIXED - Calculate position size with proper balance validation and margin requirements
    
    Args:
        symbol: Trading symbol 
        price: Entry price
        sl_price: Stop loss price
        account_balance: Available account balance in USDT
        candles_by_tf: Candles by timeframe for volatility calculation
        trade_type: Trade type (Scalp, Intraday, Swing)
        strategy: Strategy name
        confidence: Confidence percentage (0-100)
        risk_pct: Risk percentage override (if None, calculated dynamically)
        market_type: Market type (linear/spot)
        
    Returns:
        float: Calculated and validated position size
    """
    try:
        # Validate inputs
        if price <= 0 or sl_price <= 0 or account_balance <= 0:
            log(f"❌ Invalid inputs: price={price}, sl_price={sl_price}, balance={account_balance}", level="ERROR")
            return 0
            
        if price == sl_price:
            log(f"❌ Entry price equals SL price: {price}", level="ERROR")
            return 0
        
        # Use fixed risk percentages based on trade type if not provided
        if risk_pct is None:
            risk_map = {
                "Scalp": 0.03,    # 3%
                "Intraday": 0.06, # 6% 
                "Swing": 0.04     # 4%
            }
            risk_pct = risk_map.get(trade_type, 0.06)
        
        # Calculate SL distance percentage
        sl_distance_pct = abs((price - sl_price) / price)
        
        # Set leverage based on market type
        leverage = DEFAULT_LEVERAGE if market_type == "linear" else 1
        
        log(f"📊 FIXED Position sizing for {symbol}:")
        log(f"   Trade Type: {trade_type}")
        log(f"   Account Balance: ${account_balance:.2f}")
        log(f"   FIXED Risk %: {risk_pct*100:.2f}%")
        log(f"   Entry: {price:.8f}, SL: {sl_price:.8f}")
        log(f"   SL Distance: {sl_distance_pct*100:.2f}%")
        log(f"   Leverage: {leverage}x")
        
        # FIXED: Calculate risk amount with safety buffer for fees and margin
        safety_buffer = 0.85  # Use only 85% of available balance to account for fees/margin
        usable_balance = account_balance * safety_buffer
        risk_amount = usable_balance * risk_pct
        
        log(f"   Usable Balance (85%): ${usable_balance:.2f}")
        log(f"   Risk Amount: ${risk_amount:.2f}")
        
        # Calculate risk per unit (absolute dollar amount per unit)
        risk_per_unit = abs(price - sl_price)
        log(f"   Risk per Unit: {risk_per_unit:.8f}")
        
        # Calculate position size: Risk Amount / Risk per Unit
        position_size = risk_amount / risk_per_unit
        log(f"   Calculated Position Size: {position_size:.8f} units")
        
        # FIXED: For futures, check required margin instead of applying leverage to position size
        if market_type == "linear":
            # Calculate required margin for this position
            position_value = position_size * price
            required_margin = position_value / leverage
            
            log(f"   Position Value: ${position_value:.2f}")
            log(f"   Required Margin: ${required_margin:.2f}")
            
            # Ensure we have enough margin available
            if required_margin > usable_balance:
                # Reduce position size to fit available margin
                max_position_value = usable_balance * leverage
                position_size = max_position_value / price
                log(f"   ⚠️ Reduced position size to fit margin: {position_size:.8f} units")
                
                # Recalculate final values
                position_value = position_size * price
                required_margin = position_value / leverage
                actual_risk = position_size * risk_per_unit
                
                log(f"   Final Position Value: ${position_value:.2f}")
                log(f"   Final Required Margin: ${required_margin:.2f}")
                log(f"   Final Risk Amount: ${actual_risk:.2f}")
                log(f"   Final Risk %: {(actual_risk/account_balance)*100:.2f}%")
        
        # Round to symbol precision
        rounded_qty = round_qty(symbol, position_size)
        
        # Final validation - check minimum quantity
        min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
        if rounded_qty < min_qty:
            log(f"⚠️ Position size {rounded_qty} below minimum {min_qty}", level="WARN")
            return 0
        
        # Final validation - ensure we're not risking too much
        final_risk_amount = rounded_qty * risk_per_unit
        final_risk_pct = final_risk_amount / account_balance
        
        if final_risk_pct > 0.15:  # Never risk more than 15% of account
            log(f"⚠️ Final risk too high: {final_risk_pct*100:.1f}%, capping at 15%", level="WARN")
            max_risk_amount = account_balance * 0.15
            rounded_qty = round_qty(symbol, max_risk_amount / risk_per_unit)
        
        log(f"   Final Position Size: {rounded_qty:.8f} units")
        
        return rounded_qty
        
    except Exception as e:
        log(f"❌ Error calculating enhanced position size: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return 0

async def execute_market_entry(symbol, direction, qty, category="linear"):
    """Execute market entry order with enhanced error handling"""
    try:
        side = "Buy" if direction.lower() == "long" else "Sell"
        
        log(f"📤 Sending market order: {side} {qty} {symbol}")
        
        # Get current price for validation
        current_price = await get_symbol_price(symbol, category)
        if current_price <= 0:
            log(f"❌ Could not get current price for {symbol}", level="ERROR")
            return None
        
        # Calculate required margin/value for validation
        if category == "linear":
            position_value = qty * current_price
            required_margin = position_value / DEFAULT_LEVERAGE
            
            # Get fresh balance for final check
            balance = await get_account_balance()
            if required_margin > balance * 0.9:  # 90% safety margin
                log(f"❌ Insufficient margin: Required ${required_margin:.2f}, Available ${balance:.2f}", level="ERROR")
                return None
        
        result = await signed_request("POST", "/v5/order/create", {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC"
        })
        
        if result.get("retCode") == 0:
            order_data = result.get("result", {})
            order_id = order_data.get("orderId")
            avg_price = float(order_data.get("avgPrice") or current_price)
            
            log(f"✅ Market entry executed: OrderID {order_id}, Avg Price: {avg_price}")
            return {
                "order_id": order_id,
                "avg_price": avg_price,
                "executed_qty": qty,
                "side": side
            }
        else:
            error_msg = result.get("retMsg", "Unknown error")
            log(f"❌ Market order failed: {error_msg}", level="ERROR")
            
            # Enhanced error handling for common issues
            if "ab not enough" in error_msg.lower():
                balance = await get_account_balance()
                log(f"💰 Current balance: ${balance:.2f} USDT", level="ERROR")
                log(f"📊 Required for trade: ~${(qty * current_price / DEFAULT_LEVERAGE):.2f} USDT", level="ERROR")
                await send_telegram_message(
                    f"❌ <b>Insufficient Balance</b>\n"
                    f"Symbol: <b>{symbol}</b>\n"
                    f"Required: ~${(qty * current_price / DEFAULT_LEVERAGE):.2f}\n"
                    f"Available: ${balance:.2f}"
                )
            
            return None
            
    except Exception as e:
        log(f"❌ Exception in market entry: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def execute_twap_entry(symbol, direction, qty, category="linear", slices=3, delay_sec=2):
    """
    Enhanced TWAP execution with better error handling from position_manager.py
    """
    try:
        # Calculate slice size
        slice_qty = round_qty(symbol, qty / slices)
        
        # Minimum quantity check
        if slice_qty <= 0:
            log(f"⚠️ TWAP slice quantity too small ({slice_qty}), executing as market order", level="WARN")
            return await execute_market_entry(symbol, direction, qty, category)
        
        side = "Buy" if direction.lower() == "long" else "Sell"
        entries = []
        
        log(f"🔄 Starting TWAP execution for {symbol} {side} {qty} in {slices} slices...")
        
        # Execute slices with delay
        for i in range(slices):
            # For the last slice, use remaining quantity
            if i == slices - 1:
                remaining_qty = qty - sum(entries[j]["qty"] for j in range(i) if j < len(entries))
                current_qty = round_qty(symbol, remaining_qty)
            else:
                current_qty = slice_qty
            
            if current_qty <= 0:
                continue
                
            log(f"📤 TWAP Slice {i+1}/{slices}: {current_qty} {side}")
            
            try:
                result = await signed_request("POST", "/v5/order/create", {
                    "category": category,
                    "symbol": symbol,
                    "side": side,
                    "orderType": "Market",
                    "qty": str(current_qty),
                    "timeInForce": "IOC"
                })
                
                if result.get("retCode") == 0:
                    order_data = result.get("result", {})
                    price = float(order_data.get("avgPrice") or order_data.get("price") or 0)
                    
                    if price > 0:
                        entries.append({"price": price, "qty": current_qty})
                        log(f"✅ TWAP Slice {i+1} executed at {price}")
                    else:
                        log(f"⚠️ TWAP Slice {i+1} executed but no price returned", level="WARN")
                        # Use market price as fallback
                        market_price = await get_symbol_price(symbol, category)
                        entries.append({"price": market_price, "qty": current_qty})
                else:
                    log(f"❌ TWAP Slice {i+1} failed: {result.get('retMsg')}", level="ERROR")
                    
            except Exception as slice_error:
                log(f"❌ TWAP Slice {i+1} exception: {slice_error}", level="ERROR")
            
            # Delay between slices (except for the last one)
            if i < slices - 1:
                await asyncio.sleep(delay_sec)
        
        # Calculate weighted average entry price
        if entries:
            total_qty = sum(entry["qty"] for entry in entries)
            total_value = sum(entry["price"] * entry["qty"] for entry in entries)
            avg_price = total_value / total_qty if total_qty > 0 else 0
            
            log(f"✅ TWAP completed: {total_qty} units at avg price {avg_price}")
            
            return {
                "order_id": f"TWAP_{int(time.time())}",
                "avg_price": avg_price,
                "executed_qty": total_qty,
                "side": side,
                "slices": len(entries)
            }
        else:
            log(f"❌ TWAP failed - no slices executed", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ TWAP execution error: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def set_leverage(symbol, leverage, market_type="linear"):
    """Set leverage for symbol with validation"""
    try:
        result = await signed_request("POST", "/v5/position/set-leverage", {
            "category": market_type,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })
        
        if result.get("retCode") == 0:
            log(f"✅ Leverage set to {leverage}x for {symbol}")
            return True
        elif result.get("retCode") == 110043:  # Leverage not modified
            log(f"ℹ️ Leverage already set to {leverage}x for {symbol}")
            return True
        else:
            log(f"⚠️ Failed to set leverage: {result.get('retMsg')}", level="WARN")
            return False
            
    except Exception as e:
        log(f"❌ Error setting leverage: {e}", level="ERROR")
        return False

async def cancel_all_orders(symbol, market_type="linear"):
    """Cancel all orders for a symbol"""
    try:
        result = await signed_request("POST", "/v5/order/cancel-all", {
            "category": market_type,
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            cancelled_count = len(result.get("result", {}).get("list", []))
            log(f"✅ Cancelled {cancelled_count} orders for {symbol}")
            return True
        else:
            log(f"⚠️ Error cancelling orders: {result.get('retMsg')}", level="WARN")
            return False
            
    except Exception as e:
        log(f"❌ Error cancelling orders: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

async def place_stop_loss_order(symbol, direction, qty, sl_price, market_type="linear"):
    """Enhanced stop loss order placement"""
    try:
        # Validate SL price
        current_price = await get_symbol_price(symbol, market_type)
        if current_price > 0:
            if direction.lower() == "long":
                if sl_price >= current_price:
                    log(f"⚠️ Invalid long SL {sl_price} >= current {current_price}, adjusting...")
                    sl_price = current_price * 0.99  # 1% below current
                elif (current_price - sl_price) / current_price > 0.10:  # More than 10% away
                    log(f"⚠️ SL too far for long ({((current_price - sl_price) / current_price) * 100:.1f}%), adjusting...")
                    sl_price = current_price * 0.95  # Cap at 5% away
            else:  # short
                if sl_price <= current_price:
                    log(f"⚠️ Invalid short SL {sl_price} <= current {current_price}, adjusting...")
                    sl_price = current_price * 1.01  # 1% above current
                elif (sl_price - current_price) / current_price > 0.10:  # More than 10% away
                    log(f"⚠️ SL too far for short ({((sl_price - current_price) / current_price) * 100:.1f}%), adjusting...")
                    sl_price = current_price * 1.05  # Cap at 5% away
        
        # Continue with validated SL price
        log(f"🛡️ Placing SL order for {symbol}: {direction} at {sl_price}")
        
        result = await place_stop_loss_with_retry(
            symbol=symbol,
            direction=direction,
            qty=qty,
            sl_price=sl_price,
            market_type=market_type
        )
        
        if result.get("retCode") == 0:
            order_id = result.get("result", {}).get("orderId")
            log(f"✅ SL order placed: {order_id}")
            return order_id
        else:
            log(f"❌ Failed to place SL order: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing SL order: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def place_take_profit_order(symbol, direction, qty, tp_price, market_type="linear"):
    """Enhanced take profit order placement"""
    try:
        side = "Sell" if direction.lower() == "long" else "Buy"
        
        log(f"💰 Placing TP order for {symbol}: {side} at {tp_price}")
        
        result = await signed_request("POST", "/v5/order/create", {
            "category": market_type,
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(tp_price),
            "timeInForce": "GTC",
            "reduceOnly": True
        })
        
        if result.get("retCode") == 0:
            order_id = result.get("result", {}).get("orderId")
            log(f"✅ TP order placed: {order_id}")
            return order_id
        else:
            log(f"❌ Failed to place TP order: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing TP order: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

def calculate_actual_risk_percentage(entry_price, sl_price, position_size, account_balance):
    """
    Calculate the actual risk percentage based on position size and SL distance
    
    Args:
        entry_price: Entry price per unit
        sl_price: Stop loss price per unit
        position_size: Position size in units
        account_balance: Total account balance
        
    Returns:
        float: Actual risk as percentage of account balance
    """
    # Calculate risk per unit
    risk_per_unit = abs(entry_price - sl_price)
    
    # Calculate total risk
    total_risk = risk_per_unit * position_size
    
    # Calculate as percentage of balance
    risk_percentage = (total_risk / account_balance) * 100
    
    return risk_percentage

async def process_trade_result(trade_data, result_type, pnl_value=None):
    """
    Process trade result for tracking and performance updates
    Enhanced version from position_manager.py
    """
    try:
        strategy = trade_data.get("strategy", "core_strategy")
        
        # Log to strategy performance tracking
        if result_type in ["win", "loss"]:
            update_strategy_performance(strategy, result_type, pnl_value or 0)
        
        return True
        
    except Exception as e:
        log(f"❌ Error processing trade result: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

# Compatibility functions for existing code
async def twap_execute_trade(symbol, qty, direction, category, slices=3, delay_sec=2):
    """Backward compatibility wrapper"""
    return await execute_twap_entry(symbol, direction, qty, category, slices, delay_sec)

async def execute_twap_slice(symbol, category, side, slice_qty, entries):
    """Helper function for TWAP execution"""
    try:
        result = await signed_request("POST", "/v5/order/create", {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(slice_qty),
            "timeInForce": "IOC"
        })
        if result.get("retCode") == 0:
            price = float(result["result"].get("avgPrice") or 0)
            if price > 0:
                entries.append(price)
    except Exception as e:
        log(f"❌ TWAP Slice Error: {e}", level="ERROR")

# Additional utility functions
async def validate_trade_preconditions(symbol, direction, qty, account_balance, market_type="linear"):
    """
    Validate all preconditions before executing a trade
    
    Args:
        symbol: Trading symbol
        direction: Trade direction (long/short)
        qty: Position quantity
        account_balance: Available balance
        market_type: Market type (linear/spot)
        
    Returns:
        bool: True if all preconditions are met
    """
    try:
        # Check minimum balance
        if account_balance < 10:  # Minimum $10 balance
            log(f"❌ Insufficient account balance: ${account_balance:.2f}", level="ERROR")
            return False
        
        # Check minimum quantity
        min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
        if qty < min_qty:
            log(f"❌ Quantity {qty} below minimum {min_qty} for {symbol}", level="ERROR")
            return False
        
        # Check market status
        current_price = await get_symbol_price(symbol, market_type)
        if current_price <= 0:
            log(f"❌ Invalid market price for {symbol}: {current_price}", level="ERROR")
            return False
        
        # For futures, check if we have enough margin
        if market_type == "linear":
            position_value = qty * current_price
            required_margin = position_value / DEFAULT_LEVERAGE
            
            if required_margin > account_balance * 0.9:  # 90% safety margin
                log(f"❌ Insufficient margin: Required ${required_margin:.2f}, Available ${account_balance:.2f}", level="ERROR")
                return False
        
        return True
        
    except Exception as e:
        log(f"❌ Error validating trade preconditions: {e}", level="ERROR")
        return False

async def get_position_info(symbol, market_type="linear"):
    """
    Get current position information for a symbol
    
    Args:
        symbol: Trading symbol
        market_type: Market type (linear/spot)
        
    Returns:
        dict: Position information or None if no position
    """
    try:
        result = await signed_request("GET", "/v5/position/list", {
            "category": market_type,
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            positions = result.get("result", {}).get("list", [])
            for pos in positions:
                if float(pos.get("size", 0)) > 0:
                    return {
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),
                        "size": float(pos.get("size", 0)),
                        "entry_price": float(pos.get("avgPrice", 0)),
                        "mark_price": float(pos.get("markPrice", 0)),
                        "unrealized_pnl": float(pos.get("unrealisedPnl", 0)),
                        "percentage": float(pos.get("percentage", 0))
                    }
        
        return None
        
    except Exception as e:
        log(f"❌ Error getting position info: {e}", level="ERROR")
        return None

async def emergency_close_position(symbol, market_type="linear"):
    """
    Emergency close position for a symbol
    
    Args:
        symbol: Trading symbol
        market_type: Market type (linear/spot)
        
    Returns:
        bool: True if position closed successfully
    """
    try:
        # Get current position
        position = await get_position_info(symbol, market_type)
        if not position:
            log(f"ℹ️ No position found for {symbol}")
            return True
        
        # Close position with market order
        side = "Sell" if position["side"].lower() == "buy" else "Buy"
        qty = position["size"]
        
        log(f"🚨 Emergency closing position: {symbol} {side} {qty}")
        
        result = await signed_request("POST", "/v5/order/create", {
            "category": market_type,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC",
            "reduceOnly": True
        })
        
        if result.get("retCode") == 0:
            log(f"✅ Emergency close executed for {symbol}")
            return True
        else:
            log(f"❌ Emergency close failed: {result.get('retMsg')}", level="ERROR")
            return False
            
    except Exception as e:
        log(f"❌ Error in emergency close: {e}", level="ERROR")
        return False

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    """
    Enhanced trade execution combining the best of both systems
    Main function that orchestrates the complete trade setup
    
    Args:
        signal_data: Dictionary containing trade setup details
        max_risk: Maximum risk percentage (default 6%)
        
    Returns:
        dict or None: Trade details if executed successfully, None otherwise
    """
    # Load risk state and check trading permissions
    load_risk_state()
    reset_daily_risk()
    
    # Check if trading is allowed based on drawdown limits
    if not check_trading_allowed():
        log(f"🛑 Trading paused due to drawdown limits - trade blocked", level="WARN")
        await send_telegram_message("🛑 <b>Trade Blocked</b>: Trading paused due to drawdown limits")
        return None
    
    # Extract trade details
    symbol = signal_data["symbol"]
    category = signal_data.get("market_type", "linear")
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long").strip().lower()
    regime = signal_data.get("regime", "trending")
    score = signal_data.get("score", 0)
    confidence = signal_data.get("confidence", 60)
    entry_price = float(signal_data.get("price", 1.0))
    candles_by_tf = signal_data.get("candles", {})
    
    # Handle override SL/TP if provided
    override_sl = signal_data.get("override_sl")
    override_tp1 = signal_data.get("override_tp1")
    override_sl_pct = signal_data.get("override_sl_pct")
    override_tp1_pct = signal_data.get("override_tp1_pct")
    override_trailing_pct = signal_data.get("override_trailing_pct")
    
    # Use provided max_risk or get from signal_data
    if "max_risk" in signal_data:
        max_risk = signal_data["max_risk"]
    
    # Determine strategy type
    strategy = "core_strategy"
    if "mean_reversion" in signal_data.get("tf_scores", {}):
        strategy = "mean_reversion"
    elif "breakout_sniper" in signal_data.get("tf_scores", {}):
        strategy = "breakout_sniper"
    elif "range_break" in signal_data.get("tf_scores", {}):
        strategy = "range_break"
    elif "pump_" in str(signal_data.get("indicator_scores", {})):
        strategy = "pump_detector"
    
    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type} ({strategy})")
    
    # Execution state tracking
    exec_id = f"{symbol}_{int(time.time())}"
    EXECUTION_STATES[exec_id] = {"stage": "started", "success": False}
    
    try:
        # Step 1: Get account balance with retry
        account_balance = await get_account_balance()
        if account_balance <= 0:
            log(f"❌ Invalid account balance: {account_balance} USDT", level="ERROR")
            await send_telegram_message(f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: Invalid account balance.")
            return None
        
        # Step 2: Calculate SL/TP levels (with potential overrides)
        if override_sl and override_tp1:
            # Use provided override values
            sl_price = override_sl
            tp1_price = override_tp1
            sl_pct = override_sl_pct or abs((sl_price - entry_price) / entry_price)
            tp1_pct = override_tp1_pct or abs((tp1_price - entry_price) / entry_price)
            trailing_pct = override_trailing_pct or 0.005
            
            log(f"📊 Using override SL/TP:")
            log(f"   Entry: {entry_price} | SL: {sl_price} | TP1: {tp1_price}")
            log(f"   SL%: {sl_pct*100:.2f}% | TP1%: {tp1_pct*100:.2f}% | Trailing: {trailing_pct*100:.2f}%")
            
            sl_tp_result = [sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct]
        else:
            # Calculate dynamic SL/TP
            sl_tp_result = calculate_dynamic_sl_tp(
                candles_by_tf=candles_by_tf,
                price=entry_price,
                trade_type=trade_type,
                direction=direction,
                score=score,
                confidence=confidence,
                regime=regime
            )
        
        if len(sl_tp_result) < 5:
            log(f"❌ Invalid SL/TP calculation result", level="ERROR")
            return None
            
        sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = sl_tp_result[:5]
        
        EXECUTION_STATES[exec_id]["stage"] = "sl_tp_calculated"
        
        # Step 3: Calculate position size using FIXED method
        qty = await calculate_enhanced_quantity(
            symbol=symbol,
            price=entry_price,
            sl_price=sl_price,
            account_balance=account_balance,
            candles_by_tf=candles_by_tf,
            trade_type=trade_type,
            strategy=strategy,
            confidence=confidence,
            risk_pct=max_risk,
            market_type=category
        )
        
        if qty <= 0:
            log(f"⚠️ Skipped {symbol}: Quantity too small or risk limit reached.")
            return None
        
        EXECUTION_STATES[exec_id]["stage"] = "quantity_calculated"
        
        # Step 4: Validate trade preconditions
        if not await validate_trade_preconditions(symbol, direction, qty, account_balance, category):
            log(f"❌ Trade validation failed for {symbol}", level="ERROR")
            return None
        
        # Step 5: Set leverage and cancel existing orders
        if category == "linear":
            await set_leverage(symbol, DEFAULT_LEVERAGE, category)
            await cancel_all_orders(symbol, category)
        
        # Step 6: Execute entry (prefer TWAP for larger positions)
        if qty >= 3:  # Use TWAP for larger positions
            entry_result = await execute_twap_entry(symbol, direction, qty, category)
        else:
            entry_result = await execute_market_entry(symbol, direction, qty, category)
        
        if not entry_result:
            log(f"❌ Entry execution failed for {symbol}", level="ERROR")
            return None
        
        avg_entry_price = entry_result["avg_price"]
        executed_qty = entry_result["executed_qty"]
        
        EXECUTION_STATES[exec_id]["stage"] = "entry_executed"
        EXECUTION_STATES[exec_id]["success"] = True
        
        log(f"✅ {symbol} entry executed: {executed_qty} at {avg_entry_price}")
        
        # Step 7: Place protective orders (SL/TP)
        sl_order_id = None
        tp1_order_id = None
        
        # Place stop loss
        if sl_price > 0:
            sl_order_id = await place_stop_loss_order(symbol, direction, executed_qty, sl_price, category)
        
        # Place take profit
        if tp1_price > 0:
            tp1_order_id = await place_take_profit_order(symbol, direction, executed_qty, tp1_price, category)
        
        # Calculate actual risk
        actual_risk = calculate_actual_risk_percentage(avg_entry_price, sl_price, executed_qty, account_balance)
        
        # Log successful execution
        log(f"🎯 Trade setup complete for {symbol}")
        log(f"   Entry: {avg_entry_price} | SL: {sl_price} | TP: {tp1_price}")
        log(f"   Quantity: {executed_qty} | Risk: {actual_risk:.2f}%")
        
        # Return comprehensive trade details
        trade_details = {
            "symbol": symbol,
            "direction": direction,
            "trade_type": trade_type,
            "entry_price": avg_entry_price,
            "qty": executed_qty,
            "original_qty": executed_qty,  # For DCA tracking
            "sl_price": sl_price,
            "tp1_price": tp1_price,
            "sl_pct": sl_pct,
            "tp1_pct": tp1_pct,
            "trailing_pct": trailing_pct,
            "sl_order_id": sl_order_id,
            "tp1_order_id": tp1_order_id,
            "strategy": strategy,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "leverage": DEFAULT_LEVERAGE if category == "linear" else 1,
            "execution_type": "TWAP" if qty >= 3 else "Market",
            "actual_risk_pct": actual_risk,
            "confidence": confidence,
            "score": score,
            "regime": regime,
            "indicator_scores": signal_data.get("indicator_scores", {}),
            "used_indicators": signal_data.get("used_indicators", []),
            "market_type": category,
            "range_break_details": signal_data.get("range_break_details"),
            "exit_strategy": signal_data.get("exit_strategy", "standard"),
            "trailing_multiplier": signal_data.get("trailing_multiplier", 1.0),
            "exit_tranches": signal_data.get("exit_tranches", [0.4, 0.3, 0.3])
        }
        
        # Log trade execution
        write_log(f"TRADE_EXECUTED: {json.dumps(trade_details, default=str)}")
        
        # Send telegram notification
        await send_telegram_message(
            f"✅ <b>Trade Executed</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"Strategy: <b>{strategy}</b>\n"
            f"Entry: <b>{avg_entry_price}</b>\n"
            f"Quantity: <b>{executed_qty}</b>\n"
            f"SL: <b>{sl_price}</b> | TP: <b>{tp1_price}</b>\n"
            f"Risk: <b>{actual_risk:.2f}%</b>"
        )
        
        return trade_details
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        log(f"Stack trace: {error_trace}", level="ERROR")
        
        EXECUTION_STATES[exec_id]["stage"] = "error"
        EXECUTION_STATES[exec_id]["error"] = str(e)
        
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: {str(e)}"
        )
        
        return None

# Export main functions
__all__ = [
    'execute_trade_if_valid',  # Added missing function
    'get_account_balance',
    'calculate_enhanced_quantity',
    'calculate_dynamic_sl_tp',  # Added for compatibility
    'execute_market_entry',
    'execute_twap_entry',
    'place_stop_loss_order',
    'place_take_profit_order',
    'validate_trade_preconditions',
    'get_position_info',
    'emergency_close_position'
]
