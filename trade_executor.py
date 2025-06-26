# trade_executor.py - PURE EXECUTION ONLY
# All strategies and logic are in main.py - this only executes what main.py decides

import asyncio
import traceback
import json
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order
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
    except Exception as e:
        log(f"❌ Error getting account balance: {e}", level="ERROR")
        return 0.0

async def get_symbol_price(symbol, category="linear"):
    """Get current symbol price from exchange"""
    try:
        resp = await signed_request("GET", "/v5/market/tickers", {
            "category": category,
            "symbol": symbol
        })
        if resp.get("retCode") == 0:
            return float(resp["result"]["list"][0]["lastPrice"])
    except Exception as e:
        log(f"❌ Error getting symbol price: {e}", level="ERROR")
    return 0

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending", trend_context=None):
    """
    Calculate dynamic SL/TP - Compatibility function for main.py
    This is a simplified version - main.py should handle the full logic
    """
    try:
        # Import the enhanced function from sl_tp_utils
        from sl_tp_utils import calculate_dynamic_sl_tp as enhanced_calculate_dynamic_sl_tp
        
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
        
        # Fallback calculation
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
    PURE EXECUTION FUNCTION - Executes trades based on main.py decisions
    
    Args:
        symbol: Trading symbol (from main.py)
        direction: Trade direction (from main.py)
        signal_data: Signal data with all calculations (from main.py)
        strategy: Strategy name (from main.py)
        score: Signal score (from main.py)
        confidence: Signal confidence (from main.py)
        regime: Market regime (from main.py)
        account_balance: Account balance (from main.py)
        risk_per_trade: Risk percentage (from main.py)
        
    Returns:
        dict: Trade execution details or None if failed
    """
    try:
        log(f"🔄 EXECUTING TRADE: {direction} {symbol} | Strategy: {strategy}")
        
        # Get execution parameters from main.py's signal_data
        category = signal_data.get("market_type", get_symbol_category(symbol))
        qty = signal_data.get("qty", 0)
        current_price = signal_data.get("price", 0)
        sl_price = signal_data.get("sl_price", 0)
        tp1_price = signal_data.get("tp1_price", 0)
        trade_type = signal_data.get("trade_type", "Intraday")
        
        # Validate execution parameters (main.py should have calculated these)
        if not all([category, qty > 0, current_price > 0, sl_price > 0, tp1_price > 0]):
            log(f"❌ Invalid execution parameters from main.py for {symbol}", level="ERROR")
            log(f"   Category: {category}, Qty: {qty}, Price: {current_price}, SL: {sl_price}, TP1: {tp1_price}")
            return None
        
        log(f"📊 EXECUTING: {symbol} | Qty: {qty} | Entry: {current_price} | SL: {sl_price} | TP1: {tp1_price}")
        
        # Step 1: Set leverage if needed
        if category == "linear":
            await set_leverage(symbol, DEFAULT_LEVERAGE, category)
        
        # Step 2: Execute market order
        side = "Buy" if direction.lower() == "long" else "Sell"
        
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=str(qty),
            market_type=category
        )
        
        if result.get("retCode") != 0:
            log(f"❌ Market order failed: {result.get('retMsg')}", level="ERROR")
            return None
        
        # Get execution details
        order_info = result.get("result", {})
        executed_qty = float(order_info.get("qty", qty))
        avg_entry_price = float(order_info.get("price", current_price))
        
        log(f"✅ Market order executed: {executed_qty} units at {avg_entry_price}")
        
        # Step 3: Place Stop Loss order
        sl_order_id = await place_stop_loss_order(
            symbol=symbol,
            direction=direction,
            qty=executed_qty,
            sl_price=sl_price,
            market_type=category
        )
        
        if not sl_order_id:
            log(f"⚠️ SL placement failed for {symbol}", level="WARN")
        
        # Step 4: Place Take Profit order
        tp1_order_id = await place_take_profit_order(
            symbol=symbol,
            direction=direction,
            qty=executed_qty,
            tp_price=tp1_price,
            market_type=category
        )
        
        if not tp1_order_id:
            log(f"⚠️ TP1 placement failed for {symbol}", level="WARN")
        
        # Step 5: Register with monitor for trailing management
        try:
            from monitor import track_active_trade
            
            # Get trailing percentage from signal_data (calculated by main.py)
            trailing_pct = signal_data.get("trailing_pct", 1.0)
            tp1_pct = signal_data.get("tp1_pct", 2.0)
            
            track_active_trade(
                symbol=symbol,
                trade_type=trade_type,
                initial_score=score,
                entry_price=avg_entry_price,
                direction=direction,
                trailing_pct=trailing_pct,
                tp1_target=tp1_price,
                tp1_pct=tp1_pct,
                sl=sl_price,
                sl_order_id=sl_order_id,
                qty=executed_qty
            )
            
            log(f"✅ Trade registered with monitor for trailing management")
            
        except Exception as e:
            log(f"⚠️ Monitor registration failed: {e}", level="WARN")
        
        # Calculate actual risk (for logging)
        actual_risk = calculate_actual_risk_percentage(avg_entry_price, sl_price, executed_qty, account_balance)
        
        # Prepare trade details
        trade_details = {
            "symbol": symbol,
            "direction": direction,
            "trade_type": trade_type,
            "entry_price": avg_entry_price,
            "qty": executed_qty,
            "sl_price": sl_price,
            "tp1_price": tp1_price,
            "sl_order_id": sl_order_id,
            "tp1_order_id": tp1_order_id,
            "strategy": strategy,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "leverage": DEFAULT_LEVERAGE if category == "linear" else 1,
            "actual_risk_pct": actual_risk,
            "confidence": confidence,
            "score": score,
            "regime": regime,
            "market_type": category,
            "monitor_managed": True  # Flag for monitor
        }
        
        # Log execution
        write_log(f"TRADE_EXECUTED: {json.dumps(trade_details, default=str)}")
        
        # Send notification
        await send_telegram_message(
            f"✅ <b>Trade Executed</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"Strategy: <b>{strategy}</b>\n"
            f"Entry: <b>{avg_entry_price}</b>\n"
            f"Quantity: <b>{executed_qty}</b>\n"
            f"SL: <b>{sl_price}</b>\n"
            f"TP1: <b>{tp1_price}</b> (50% exit)\n"
            f"Risk: <b>{actual_risk:.2f}%</b>\n"
            f"🔄 Monitor handles: TP1 → 50% exit → Trailing SL"
        )
        
        # Log to activity file
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=avg_entry_price,
            sl=sl_price,
            tp1=tp1_price,
            tp2=None,
            result="executed",
            score=score,
            trade_type=trade_type,
            confidence=confidence
        )
        
        log(f"🎯 Trade execution complete for {symbol}")
        return trade_details
        
    except Exception as e:
        log(f"❌ Trade execution error: {e}", level="ERROR")
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
    """Place stop loss order"""
    try:
        log(f"🛡️ Placing SL order for {symbol}: {direction} at {sl_price}")
        
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
            log(f"✅ SL order placed: {order_id}")
            return order_id
        else:
            log(f"❌ Failed to place SL: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing SL: {e}", level="ERROR")
        return None

async def place_take_profit_order(symbol, direction, qty, tp_price, market_type="linear"):
    """Place take profit order"""
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
            log(f"❌ Failed to place TP1: {result.get('retMsg')}", level="ERROR")
            return None
            
    except Exception as e:
        log(f"❌ Error placing TP1: {e}", level="ERROR")
        return None

def calculate_actual_risk_percentage(entry_price, sl_price, qty, account_balance):
    """Calculate actual risk percentage"""
    try:
        risk_amount = abs(entry_price - sl_price) * qty
        risk_percentage = (risk_amount / account_balance) * 100
        return risk_percentage
    except Exception as e:
        log(f"❌ Error calculating risk: {e}", level="ERROR")
        return 0.0

# REMOVED FUNCTIONS (handled by main.py):
# - All strategy logic
# - Signal generation
# - Risk calculations
# - SL/TP calculations
# - Position sizing
# - Market analysis
# - Trailing stop placement (monitor handles this)

# ONLY HANDLES:
# - Market order execution
# - SL order placement
# - TP1 order placement
# - Monitor registration
# - Execution logging
