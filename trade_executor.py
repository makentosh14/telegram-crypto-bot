"""
Enhanced Trade Executor - Combines the best of trade_executor.py and position_manager.py
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

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending"):
    """
    Calculate optimal SL/TP levels - Enhanced version that combines both implementations
    """
    # First try the enhanced version from sl_tp_utils
    try:
        result = enhanced_calculate_dynamic_sl_tp(
            candles_by_tf=candles_by_tf,
            entry_price=price,
            trade_type=trade_type,
            direction=direction,
            score=score,
            confidence=confidence,
            regime=regime
        )
        
        # Enhanced version returns more values, extract what we need
        if len(result) >= 5:
            sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = result[:5]
            return sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct
    except Exception as e:
        log(f"⚠️ Enhanced SL/TP calculation failed, using fallback: {e}", level="WARN")
    
    # Fallback to original implementation with FIXED PERCENTAGES
    atr_tf_map = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    atr = calculate_atr(candles) if candles else None

    # FIXED: More reasonable base SL percentages for crypto
    base_sl_percentages = {
        "Scalp": 0.8,      # 1.8% for scalps (was too low)
        "Intraday": 1.2,   # 2.2% for intraday (was too low) 
        "Swing": 2.8       # 2.8% for swing trades (was too low)
    }
    
    # Start with base percentage
    sl_pct = base_sl_percentages.get(trade_type, 2.2)
    
    # Adjust based on confidence - LESS aggressive adjustments
    if confidence >= 85 and score >= 8.0:
        sl_pct *= 0.9   # Only 10% tighter for very high confidence (was 0.8)
    elif confidence < 60 or score < 6:
        sl_pct *= 1.3   # 30% wider for low confidence (was 1.5)
    
    # Adjust SL based on market regime - MORE conservative
    if regime == "volatile":
        sl_pct *= 1.6   # Much wider in volatile markets (was 1.5)
    elif regime == "ranging":
        sl_pct *= 1.4   # Wider in ranging markets (was 1.3)

    # FIXED: Ensure minimum SL percentage for crypto volatility
    min_sl_pct = {
        "Scalp": 1.5,      # Minimum 1.5% for scalps
        "Intraday": 1.8,   # Minimum 1.8% for intraday
        "Swing": 2.0       # Minimum 2.0% for swing trades
    }
    
    sl_pct = max(sl_pct, min_sl_pct.get(trade_type, 1.8))

    # If we have ATR, use it as additional validation but don't make SL too tight
    if atr:
        atr_factor = 1.8 if confidence >= 75 else 2.2  # More conservative ATR factors
        atr_sl_distance = atr * atr_factor
        atr_sl_pct = (atr_sl_distance / price) * 100
        
        # Use the WIDER of ATR-based or percentage-based SL
        sl_pct = max(sl_pct, atr_sl_pct)
        log(f"📊 ATR-based SL: {atr_sl_pct:.2f}%, Percentage-based: {sl_pct:.2f}%, Using: {max(sl_pct, atr_sl_pct):.2f}%")

    # Enhanced TP ratios optimized for catching bigger moves
    tp_ratio_map = {
        "Scalp": 2.2,      # Increased from 2.0
        "Intraday": 2.8,   # Increased from 2.5
        "Swing": 3.5       # Increased from 3.0
    }
    
    tp1_ratio = tp_ratio_map.get(trade_type, 2.8)
    
    # Adjust TP ratio based on regime
    if regime == "volatile":
        tp1_ratio *= 1.4   # Higher targets in volatile markets for pumps
    elif regime == "ranging":
        tp1_ratio *= 0.8   # Lower targets in ranging markets
    
    # Check for momentum to set even more aggressive targets
    has_momentum = False
    candles_1m = candles_by_tf.get('1')
    if candles_1m and len(candles_1m) >= 10:
        has_momentum = detect_momentum_surge(candles_1m)
        if has_momentum:
            log(f"🚀 Momentum detected during setup - setting aggressive targets")
            tp1_ratio *= 1.3
    
    # Calculate TP percentage and trailing stop percentage
    tp1_pct = sl_pct * tp1_ratio
    
    # FIXED: More reasonable trailing percentages
    trailing_pct_map = {
        "Scalp": 0.7,      # 70% of SL distance for scalps
        "Intraday": 0.8,   # 80% of SL distance for intraday
        "Swing": 0.9       # 90% of SL distance for swing trades
    }
    trailing_pct = sl_pct * trailing_pct_map.get(trade_type, 0.8)
    
    # Calculate actual price levels
    if direction.lower() == "long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    log(f"📊 SL/TP calculated: {direction} {trade_type} ({regime}) | Entry: {price} | SL: {sl} ({sl_pct:.2f}%) | TP: {tp1} ({tp1_pct:.2f}%) | RR: {tp1_ratio:.1f}x | Trail: {trailing_pct:.2f}%")
    return sl, tp1, sl_pct, trailing_pct, tp1_pct

async def calculate_enhanced_quantity(symbol, price, sl_price, account_balance, 
                                    candles_by_tf, trade_type, strategy, confidence,
                                    risk_pct=None, market_type="linear"):
    """
    Enhanced position sizing using advanced risk manager
    Combines original logic with position_manager.py improvements
    """
    try:
        # Use enhanced risk calculation if available
        if risk_pct is None:
            try:
                position_size, risk_amount, leverage = await calculate_position_size(
                    symbol=symbol,
                    candles_by_tf=candles_by_tf,
                    account_balance=account_balance,
                    entry_price=price,
                    stop_loss=sl_price,
                    trade_type=trade_type,
                    strategy=strategy,
                    confidence=confidence,
                    market_type=market_type
                )
                
                # Register the trade risk
                register_trade_risk(symbol, risk_amount / account_balance, strategy)
                
                return round_qty(symbol, position_size)
                
            except Exception as e:
                log(f"⚠️ Enhanced position sizing failed, using fallback: {e}", level="WARN")
        
        # Fallback to original calculation
        leverage = DEFAULT_LEVERAGE if market_type == "linear" else 1
        max_risk = risk_pct or (0.09 if trade_type == "Scalp" else 0.06 if trade_type == "Intraday" else 0.03)
        
        risk_amount = account_balance * max_risk
        position_value = risk_amount * leverage
        raw_qty = position_value / price
        
        log(f"📊 Position sizing for {symbol}:")
        log(f"  Price: {price}, SL: {sl_price}, Distance: {abs(price - sl_price) / price:.2%}")
        log(f"  Risk: ${risk_amount:.2f}, Leverage: {leverage}x")
        log(f"  Final Size: {raw_qty} units")
        
        return calculate_quantity(symbol, raw_qty)
        
    except Exception as e:
        log(f"❌ Error calculating position size: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return 0

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
                        log(f"⚠️ TWAP Slice {i+1} missing price data", level="WARN")
                else:
                    log(f"❌ TWAP Slice {i+1} failed: {result.get('retMsg')}", level="ERROR")
            except Exception as e:
                log(f"❌ Error in TWAP Slice {i+1}: {e}", level="ERROR")
            
            # Delay between slices (except for the last one)
            if i < slices - 1:
                await asyncio.sleep(delay_sec)
        
        # Calculate average entry price
        if entries:
            total_value = sum(e["price"] * e["qty"] for e in entries)
            total_qty = sum(e["qty"] for e in entries)
            
            if total_qty > 0:
                avg_entry = round(total_value / total_qty, 6)
                log(f"✅ Final TWAP Entry Price: {avg_entry}")
                return avg_entry
        
        log(f"❌ TWAP execution failed for {symbol} - no valid entries", level="ERROR")
        return None
        
    except Exception as e:
        log(f"❌ Error in TWAP execution: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def execute_market_entry(symbol, direction, qty, category="linear"):
    """
    Enhanced market order execution with better price discovery from position_manager.py
    """
    try:
        side = "Buy" if direction.lower() == "long" else "Sell"
        
        log(f"📤 Sending market order: {side} {qty} {symbol}")
        
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
            price = float(order_data.get("avgPrice") or order_data.get("price") or 0)
            
            if price > 0:
                log(f"✅ Market order executed at {price}")
                return price
            else:
                log(f"⚠️ Market order missing price data", level="WARN")
                
                # Try to get the price from order details API
                order_id = order_data.get("orderId")
                if order_id:
                    await asyncio.sleep(1)  # Brief delay to allow order to be processed
                    order_details = await signed_request("GET", "/v5/order/realtime", {
                        "category": category,
                        "symbol": symbol,
                        "orderId": order_id
                    })
                    
                    if order_details.get("retCode") == 0:
                        orders = order_details.get("result", {}).get("list", [])
                        if orders:
                            price = float(orders[0].get("avgPrice") or orders[0].get("price") or 0)
                            if price > 0:
                                log(f"✅ Retrieved order price from details: {price}")
                                return price
                
                # Fallback to current market price
                ticker_resp = await signed_request("GET", "/v5/market/tickers", {
                    "category": category, 
                    "symbol": symbol
                })
                
                if ticker_resp.get("retCode") == 0:
                    price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("lastPrice", 0))
                    if price > 0:
                        log(f"⚠️ Using market price as fallback: {price}", level="WARN")
                        return price
                
                log(f"❌ Failed to determine execution price", level="ERROR")
                return None
        else:
            log(f"❌ Market order failed: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error in market entry: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def set_position_leverage(symbol, leverage, category="linear"):
    """Set leverage for a position - from position_manager.py"""
    try:
        result = await signed_request("POST", "/v5/position/set-leverage", {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })
        
        if result.get("retCode") == 0:
            log(f"✅ Set leverage for {symbol} to {leverage}x")
            return True
        else:
            log(f"⚠️ Failed to set leverage: {result.get('retMsg')}", level="WARN")
            return False
            
    except Exception as e:
        log(f"❌ Error setting leverage: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

async def place_stop_loss_order(symbol, direction, qty, sl_price, market_type="linear"):
    """Enhanced stop loss placement with validation from position_manager.py"""
    try:
        # Validate the SL price is on the correct side of the market
        sl_price = await validate_sl_placement(symbol, direction, sl_price, market_type)
        
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
    """Enhanced take profit order placement from position_manager.py"""
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

async def cancel_all_orders(symbol, category="linear"):
    """Cancel all open orders for a symbol - from position_manager.py"""
    try:
        result = await signed_request("POST", "/v5/order/cancel-all", {
            "category": category,
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            log(f"✅ Cancelled all orders for {symbol}")
            return True
        else:
            log(f"⚠️ Failed to cancel orders: {result.get('retMsg')}", level="WARN")
            return False
            
    except Exception as e:
        log(f"❌ Error cancelling orders: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return False

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    """
    Enhanced trade execution combining the best of both systems
    Main function that orchestrates the complete trade setup
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
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long").strip().lower()
    regime = signal_data.get("regime", "trending")
    score = signal_data.get("score", 0)
    confidence = signal_data.get("confidence", 60)
    entry_price = float(signal_data.get("price", 1.0))
    candles_by_tf = signal_data.get("candles", {})
    
    # Determine strategy type
    strategy = "core_strategy"
    if "mean_reversion" in signal_data.get("tf_scores", {}):
        strategy = "mean_reversion"
    elif "breakout_sniper" in signal_data.get("tf_scores", {}):
        strategy = "breakout_sniper"
    
    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type} ({strategy})")
    
    # Execution state tracking
    exec_id = f"{symbol}_{int(time.time())}"
    EXECUTION_STATES[exec_id] = {"stage": "started", "success": False}
    
    try:
        # Step 1: Get account balance with enhanced caching
        account_balance = await get_account_balance()
        if account_balance <= 0:
            log(f"❌ Invalid account balance: {account_balance} USDT", level="ERROR")
            await send_telegram_message(f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: Invalid account balance.")
            return None
        
        EXECUTION_STATES[exec_id]["stage"] = "balance_checked"
        
        # Step 2: Calculate SL/TP levels using enhanced calculation
        # FIX: Properly unpack all 5 values including trailing_pct
        sl_tp_result = calculate_dynamic_sl_tp(
            candles_by_tf, entry_price, trade_type, direction, score, confidence, regime
        )
        
        # Ensure we have at least 5 values
        if len(sl_tp_result) >= 5:
            sl, tp1, sl_pct, trailing_pct, tp1_pct = sl_tp_result[:5]
        else:
            # Fallback if function returns fewer values
            sl, tp1, sl_pct = sl_tp_result[:3]
            trailing_pct = sl_pct * 0.5  # Default trailing percentage
            tp1_pct = sl_pct * 2.0      # Default TP percentage
        
        EXECUTION_STATES[exec_id]["stage"] = "sl_tp_calculated"
        
        # Step 3: Calculate position size using enhanced method
        qty = await calculate_enhanced_quantity(
            symbol=symbol,
            price=entry_price,
            sl_price=sl,
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
        
        EXECUTION_STATES[exec_id]["stage"] = "position_sized"
        
        # Step 4: Set leverage (for futures)
        leverage = DEFAULT_LEVERAGE if category == "linear" else 1
        if category == "linear":
            await set_position_leverage(symbol, leverage, category)
        
        # Step 5: Cancel any existing orders
        await cancel_all_orders(symbol, category)
        
        EXECUTION_STATES[exec_id]["stage"] = "orders_cancelled"
        
        # Step 6: Execute entry using appropriate method
        executed_entry = None
        
        if regime == "volatile" and category == "linear":
            # Use TWAP for volatile markets
            executed_entry = await execute_twap_entry(
                symbol=symbol,
                direction=direction,
                qty=qty,
                category=category,
                slices=3,
                delay_sec=2
            )
        else:
            # Use market order for normal conditions
            executed_entry = await execute_market_entry(
                symbol=symbol,
                direction=direction,
                qty=qty,
                category=category
            )
        
        if not executed_entry:
            log(f"❌ Entry execution failed for {symbol}", level="ERROR")
            EXECUTION_STATES[exec_id]["stage"] = "entry_failed"
            return None
        
        EXECUTION_STATES[exec_id]["stage"] = "entry_executed"
        
        # Step 7: Recalculate SL/TP based on actual entry price if different
        if executed_entry != entry_price:
            sl_tp_result = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence, regime
            )
            
            # FIX: Properly unpack the recalculated values
            if len(sl_tp_result) >= 5:
                sl, tp1, sl_pct, trailing_pct, tp1_pct = sl_tp_result[:5]
            else:
                sl, tp1, sl_pct = sl_tp_result[:3]
                trailing_pct = sl_pct * 0.5
                tp1_pct = sl_pct * 2.0
        
        # Step 8: Calculate exit tranches with enhanced logic
        volatility = "normal"
        if regime == "volatile":
            volatility = "high"
        elif regime == "ranging":
            volatility = "low"
            
        has_momentum = signal_data.get("momentum", False) or signal_data.get("pump_potential", False)
        
        exit_tranches = calculate_exit_tranches(
            symbol=symbol,
            total_qty=qty,
            trade_type=trade_type,
            volatility=volatility,
            momentum=has_momentum
        )
        
        # Step 9: Place stop loss order with enhanced validation
        sl_order_id = await place_stop_loss_order(
            symbol=symbol,
            direction=direction,
            qty=qty,
            sl_price=sl,
            market_type=category
        )
        
        EXECUTION_STATES[exec_id]["stage"] = "sl_placed"
        
        # Step 10: Place take profit order for first tranche
        tp1_qty = exit_tranches[0] if exit_tranches and len(exit_tranches) > 0 else round_qty(symbol, qty / 3)
        
        tp1_order_id = await place_take_profit_order(
            symbol=symbol,
            direction=direction,
            qty=tp1_qty,
            tp_price=tp1,
            market_type=category
        )
        
        EXECUTION_STATES[exec_id]["stage"] = "tp_placed"
        
        # Step 11: Set up additional TP levels for bigger moves
        tp2_price = None
        tp2_pct = None
        if trade_type in ["Intraday", "Swing"]:
            tp2_pct = tp1_pct * 1.8
            if direction.lower() == "long":
                tp2_price = round(executed_entry * (1 + tp2_pct / 100), 6)
            else:
                tp2_price = round(executed_entry * (1 - tp2_pct / 100), 6)
            
            log(f"🎯 Setting stretched TP2 at {tp2_price} ({tp2_pct:.2f}%) for potential pump")
        
        EXECUTION_STATES[exec_id]["success"] = True
        
        # Step 12: Log trade details
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", [])
        
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=executed_entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2_price,
            result="open",
            score=score,
            trade_type=trade_type,
            confidence=confidence,
            tf_scores=signal_data.get("tf_scores", {}),
            indicator_scores=indicator_scores,
            used_indicators=used_indicators,
            pattern_detected=signal_data.get("pattern"),
            whale_signal=signal_data.get("whale", False),
            volume_spike=signal_data.get("volume_spike", False),
            sl_strategy=f"Enhanced-{trade_type}"
        )
        
        # Build complete trade details
        trade_details = {
            "entry": executed_entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2_price,
            "qty": qty,
            "type": trade_type,
            "direction": direction,
            "symbol": symbol,
            "sl_pct": sl_pct,
            "tp1_pct": tp1_pct,
            "tp2_pct": tp2_pct,
            "trailing_pct": trailing_pct,  # Now properly defined
            "indicator_scores": indicator_scores,
            "used_indicators": used_indicators,
            "sl_order_id": sl_order_id,
            "tp1_order_id": tp1_order_id,
            "exit_tranches": exit_tranches,
            "regime": regime,
            "leverage": leverage,
            "strategy": strategy,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Log trade execution details
        write_log(f"TRADE_EXECUTED: {json.dumps(trade_details, default=str)}")
        
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
