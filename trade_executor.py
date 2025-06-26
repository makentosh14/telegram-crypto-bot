# trade_executor.py - SIMPLIFIED VERSION: Only SL/TP placement, NO trailing stops
# Let monitor.py and active_trade_scanner.py handle all trailing functionality

import asyncio
import traceback
import json
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order, get_symbol_price
from error_handler import send_telegram_message, send_error_to_telegram
from config import DEFAULT_LEVERAGE
from symbol_utils import get_symbol_category, round_qty
from activity_logger import log_trade_to_file

async def get_account_balance():
    """Get account balance from exchange"""
    try:
        result = await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })
        
        if result.get("retCode") == 0:
            accounts = result.get("result", {}).get("list", [])
            for account in accounts:
                coins = account.get("coin", [])
                for coin in coins:
                    if coin.get("coin") == "USDT":
                        balance = float(coin.get("walletBalance", 0))
                        log(f"💰 Account balance: {balance} USDT")
                        return balance
        
        log(f"❌ Failed to get account balance: {result.get('retMsg')}", level="ERROR")
        return 0.0
        
    except Exception as e:
        log(f"❌ Error getting account balance: {e}", level="ERROR")
        return 0.0

async def execute_trade_if_valid(
    symbol, 
    direction, 
    signal_data, 
    strategy, 
    score, 
    confidence, 
    regime, 
    account_balance,
    risk_per_trade=1.0
):
    """
    SIMPLIFIED execute_trade_if_valid - Only places initial SL and TP orders
    All trailing functionality handled by monitor.py and active_trade_scanner.py
    """
    try:
        log(f"🔄 TRADE EXECUTOR: Executing {direction} trade for {symbol} | Strategy: {strategy}")
        
        # Step 1: Get symbol info and category
        category = get_symbol_category(symbol)
        if not category:
            log(f"❌ Cannot determine category for {symbol}", level="ERROR")
            return None
        
        # Step 2: Get account balance
        if not account_balance or account_balance <= 0:
            account_balance = await get_account_balance()
            if account_balance <= 0:
                log(f"❌ Invalid account balance: {account_balance} USDT", level="ERROR")
                return None
        
        # Step 3: Calculate position size based on risk
        current_price = await get_symbol_price(symbol, category)
        if current_price <= 0:
            log(f"❌ Invalid current price for {symbol}: {current_price}", level="ERROR")
            return None
        
        # Get trade type from signal data
        trade_type = signal_data.get("trade_type", "Intraday")
        
        # Use fixed risk percentages based on trade type
        risk_percentages = {
            "Scalp": {"tp1_pct": 0.9, "sl_pct": 0.6, "trailing_pct": 0.4},
            "Intraday": {"tp1_pct": 1.2, "sl_pct": 0.8, "trailing_pct": 0.8}, 
            "Swing": {"tp1_pct": 3.5, "sl_pct": 1.5, "trailing_pct": 1.5}
        }
        
        params = risk_percentages.get(trade_type, risk_percentages["Intraday"])
        sl_pct = params["sl_pct"]
        tp1_pct = params["tp1_pct"]
        
        # Calculate SL and TP levels
        if direction.lower() == "long":
            sl_price = current_price * (1 - sl_pct/100)
            tp1_price = current_price * (1 + tp1_pct/100)
        else:
            sl_price = current_price * (1 + sl_pct/100)
            tp1_price = current_price * (1 - tp1_pct/100)
        
        # Calculate position size based on SL risk
        risk_amount = account_balance * (risk_per_trade / 100)
        price_diff = abs(current_price - sl_price)
        qty = risk_amount / price_diff
        qty = round_qty(symbol, qty)
        
        if qty <= 0:
            log(f"❌ Invalid quantity calculated: {qty}", level="ERROR")
            return None
        
        log(f"📊 TRADE SETUP: {symbol} | Balance: {account_balance} USDT | Qty: {qty} | Entry: {current_price} | SL: {sl_price} | TP1: {tp1_price}")
        
        # Step 4: Set leverage if needed
        if category == "linear":
            await set_leverage(symbol, DEFAULT_LEVERAGE, category)
        
        # Step 5: Execute market order
        side = "Buy" if direction.lower() == "long" else "Sell"
        
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=str(qty),
            market_type=category
        )
        
        if result.get("retCode") != 0:
            log(f"❌ Failed to place market order: {result.get('retMsg')}", level="ERROR")
            return None
        
        # Get execution details
        order_info = result.get("result", {})
        executed_qty = float(order_info.get("qty", qty))
        avg_entry_price = float(order_info.get("price", current_price))
        
        log(f"✅ Market order executed: {executed_qty} units at {avg_entry_price}")
        
        # Step 6: Place ONLY Stop Loss order (NO trailing stop)
        sl_order_id = await place_stop_loss_order(
            symbol=symbol,
            direction=direction,
            qty=executed_qty,
            sl_price=sl_price,
            market_type=category
        )
        
        if not sl_order_id:
            log(f"⚠️ Trade executed but SL placement failed for {symbol}", level="WARN")
            # Continue anyway - monitor can handle SL recovery
        
        # Step 7: Place Take Profit order (only TP1, no TP2)
        # The monitor will handle partial exits and trailing
        tp1_order_id = await place_take_profit_order(
            symbol=symbol,
            direction=direction,
            qty=executed_qty,
            tp_price=tp1_price,
            market_type=category
        )
        
        if not tp1_order_id:
            log(f"⚠️ TP1 order placement failed for {symbol}", level="WARN")
            # Continue anyway - monitor can handle TP detection
        
        # Step 8: Register trade with monitor system for trailing management
        try:
            from monitor import track_active_trade
            
            # Register with monitor for TP1 detection and trailing
            track_active_trade(
                symbol=symbol,
                trade_type=trade_type,
                initial_score=score,
                entry_price=avg_entry_price,
                direction=direction,
                trailing_pct=params["trailing_pct"],  # Monitor will use this for trailing
                tp1_target=tp1_price,
                tp1_pct=tp1_pct,
                sl=sl_price,
                sl_order_id=sl_order_id,
                qty=executed_qty
            )
            
            log(f"✅ Trade registered with monitor: TP1={tp1_price:.6f}, Trailing={params['trailing_pct']}%")
            
        except Exception as e:
            log(f"⚠️ Failed to register with monitor: {e}", level="WARN")
            # Trade still executed, just monitor integration failed
        
        # Calculate actual risk
        actual_risk = calculate_actual_risk_percentage(avg_entry_price, sl_price, executed_qty, account_balance)
        
        # Log successful execution
        log(f"🎯 Trade setup complete for {symbol}")
        log(f"   Entry: {avg_entry_price} | SL: {sl_price} | TP1 Target: {tp1_price:.6f}")
        log(f"   Quantity: {executed_qty} | Risk: {actual_risk:.2f}%")
        log(f"   Monitor will handle: TP1 detection → Partial exit → Trailing SL")
        
        # Return comprehensive trade details
        trade_details = {
            "symbol": symbol,
            "direction": direction,
            "trade_type": trade_type,
            "entry_price": avg_entry_price,
            "qty": executed_qty,
            "original_qty": executed_qty,
            "sl_price": sl_price,
            "tp1_price": tp1_price,
            "sl_pct": sl_pct,
            "tp1_pct": tp1_pct,
            "trailing_pct": params["trailing_pct"],  # For monitor reference
            "sl_order_id": sl_order_id,
            "tp1_order_id": tp1_order_id,
            "monitor_managed": True,  # Flag that monitor handles trailing
            "strategy": strategy,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "leverage": DEFAULT_LEVERAGE if category == "linear" else 1,
            "execution_type": "Market",
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
            "exit_tranches": signal_data.get("exit_tranches", [0.5, 0.5])  # 50% TP1, 50% trail
        }
        
        # Log trade execution
        write_log(f"TRADE_EXECUTED: {json.dumps(trade_details, default=str)}")
        
        # Send telegram notification - UPDATED message
        await send_telegram_message(
            f"✅ <b>Trade Executed</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"Strategy: <b>{strategy}</b>\n"
            f"Entry: <b>{avg_entry_price}</b>\n"
            f"Quantity: <b>{executed_qty}</b>\n"
            f"SL: <b>{sl_price}</b>\n"
            f"TP1: <b>{tp1_price}</b> (50% exit)\n"
            f"🔄 <b>Monitor Handles</b>: TP1 → 50% exit → Trailing SL\n"
            f"Risk: <b>{actual_risk:.2f}%</b>\n"
            f"✅ No conflicts - Monitor manages trailing"
        )
        
        # Log to activity file
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=avg_entry_price,
            sl=sl_price,
            tp1=tp1_price,
            tp2=None,  # No TP2 - monitor handles trailing
            result="executed",
            score=score,
            trade_type=trade_type,
            confidence=confidence
        )
        
        return trade_details
        
    except Exception as e:
        log(f"❌ Fatal error in execute_trade_if_valid: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        await send_error_to_telegram(f"Trade execution failed for {symbol}: {str(e)}")
        return None

async def set_leverage(symbol, leverage, market_type="linear"):
    """Set leverage for a symbol"""
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

async def place_stop_loss_order(symbol, direction, qty, sl_price, market_type="linear"):
    """Enhanced stop loss order placement - ONLY initial SL, no trailing"""
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
        
        # Place stop loss order
        log(f"🛡️ Placing initial SL order for {symbol}: {direction} at {sl_price}")
        
        # Use the enhanced stop loss function from bybit_api
        from bybit_api import place_stop_loss_with_retry
        
        result = await place_stop_loss_with_retry(
            symbol=symbol,
            direction=direction,
            qty=qty,
            sl_price=sl_price,
            market_type=market_type
        )
        
        if result.get("retCode") == 0:
            order_id = result.get("result", {}).get("orderId")
            log(f"✅ Initial SL order placed: {order_id}")
            return order_id
        else:
            log(f"❌ Failed to place SL order: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing SL order: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

async def place_take_profit_order(symbol, direction, qty, tp_price, market_type="linear"):
    """Enhanced take profit order placement - ONLY TP1"""
    try:
        side = "Sell" if direction.lower() == "long" else "Buy"
        
        log(f"💰 Placing TP1 order for {symbol}: {side} at {tp_price}")
        
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
            log(f"✅ TP1 order placed: {order_id}")
            return order_id
        else:
            log(f"❌ Failed to place TP1 order: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing TP1 order: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return None

def calculate_actual_risk_percentage(entry_price, sl_price, qty, account_balance):
    """Calculate the actual risk percentage of the trade"""
    try:
        risk_amount = abs(entry_price - sl_price) * qty
        risk_percentage = (risk_amount / account_balance) * 100
        return risk_percentage
    except Exception as e:
        log(f"❌ Error calculating risk percentage: {e}", level="ERROR")
        return 0.0

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

# REMOVED FUNCTIONS TO PREVENT CONFLICTS:
# - place_trailing_stop_order() - Monitor handles this
# - place_exchange_trailing_stop() - Monitor handles this  
# - Any other trailing stop functions - Monitor handles all trailing

# NOTE: This simplified trade_executor only handles:
# 1. Market order execution
# 2. Initial SL placement
# 3. Initial TP1 placement
# 4. Trade registration with monitor
#
# The monitor.py and active_trade_scanner.py handle:
# 1. TP1 detection and partial exits
# 2. Moving SL to breakeven after TP1
# 3. All trailing stop functionality
# 4. Final exit management
