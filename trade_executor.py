from bybit_api import signed_request, get_futures_available_balance
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from error_handler import send_telegram_message
from atr import calculate_atr
from activity_logger import write_log, log_trade_to_file
from symbol_info import round_qty, symbol_precisions
from datetime import datetime
from volume import get_average_volume
from exit_manager import calculate_exit_tranches, detect_momentum_surge
from position_manager import execute_trade
from sl_tp_utils import calculate_dynamic_sl_tp
from risk_manager import calculate_position_size
import asyncio
import json
import traceback
import time


def calculate_quantity(symbol, raw_qty):
    if raw_qty <= 0:
        return 0
    min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
    rounded_qty = round_qty(symbol, raw_qty)
    if rounded_qty < min_qty:
        return 0
    return rounded_qty


def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending"):
    """
    Calculate optimal SL/TP levels based on trade type, regime, and confidence
    Enhanced for capturing big pumps
    """
    atr_tf_map = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    atr = calculate_atr(candles) if candles else None

    # Adjust ATR factor based on confidence
    atr_factor = 1.2 if confidence >= 75 else 1.6
    
    if atr:
        sl_distance = atr * atr_factor
        sl_pct = (sl_distance / price) * 100
    else:
        # More conservative stops for high confidence setups
        if confidence >= 85 and score >= 7.5:
            sl_pct = 1.5
        elif confidence < 60 or score < 6:
            sl_pct = 0.8  # Changed from 0.6 to be slightly wider
        else:
            sl_pct = 1.0

    # Adjust SL based on market regime
    if regime == "volatile":
        sl_pct *= 1.5
    elif regime == "ranging":
        sl_pct *= 1.3

    # Enhanced TP ratios optimized for catching bigger moves
    tp_ratio_map = {
        "Scalp": 2.0,      # Increased from 1.8 to 2.0
        "Intraday": 2.5,   # Increased from 1.8 to 2.5
        "Swing": 3.0       # Increased from 2.2 to 3.0
    }
    
    tp1_ratio = tp_ratio_map.get(trade_type, 2.5)
    
    # Adjust TP ratio based on regime
    if regime == "volatile":
        tp1_ratio *= 1.3   # Set higher targets in volatile markets to catch pumps
    elif regime == "ranging":
        tp1_ratio *= 0.85  # More conservative in ranging markets
    
    # Check for momentum to set even more aggressive targets
    has_momentum = False
    candles_1m = candles_by_tf.get('1')
    if candles_1m and len(candles_1m) >= 10:
        has_momentum = detect_momentum_surge(candles_1m)
        if has_momentum:
            log(f"🚀 Momentum detected during setup - setting aggressive targets")
            tp1_ratio *= 1.2  # Even higher targets for momentum
    
    # Calculate TP percentage and trailing stop percentage
    tp1_pct = sl_pct * tp1_ratio
    
    # Adjusted trailing percentages to better catch big pumps - wider for all types
    trailing_pct_map = {
        "Scalp": 0.5,     # More relaxed trailing for scalps
        "Intraday": 0.6,  # More relaxed trailing for intraday
        "Swing": 0.7      # More relaxed trailing for swings
    }
    trailing_pct = sl_pct * trailing_pct_map.get(trade_type, 0.5)
    
    # Calculate actual price levels
    if direction.lower() == "long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    log(f"📊 SL/TP calculated: {direction} {trade_type} ({regime}) | SL: {sl_pct:.2f}% | TP: {tp1_pct:.2f}% | Ratio: {tp1_ratio:.1f}x | Trailing: {trailing_pct:.2f}%")
    return sl, tp1, sl_pct, trailing_pct, tp1_pct


# Optimized TWAP implementation for volatile markets only
async def twap_execute_trade(symbol, qty, direction, category, slices=3, delay_sec=2):
    """Optimized TWAP execution with reduced delays for volatile markets"""
    slice_qty = round(qty / slices, 6)
    side = "Buy" if direction == "long" else "Sell"
    entries = []

    log(f"🚀 Starting fast TWAP execution for {symbol} in {slices} slices...")

    # Execute first slice immediately
    log(f"📤 TWAP Slice 1/{slices}: {slice_qty} {side}")
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
        log(f"❌ TWAP First Slice Error: {e}", level="ERROR")

    # Execute remaining slices with minimal delay
    for i in range(1, slices):
        task = asyncio.create_task(execute_twap_slice(symbol, category, side, slice_qty, entries))
        # Use a very short delay between slices
        await asyncio.sleep(delay_sec)
    
    # Wait for all slices to finish
    await asyncio.sleep(delay_sec * (slices - 1) + 1)
    
    if entries:
        avg_entry = round(sum(entries) / len(entries), 6)
        log(f"🎯 Final Fast TWAP Entry Price: {avg_entry}")
        return avg_entry
    else:
        log(f"❌ All TWAP slices failed for {symbol}")
        return None

async def execute_twap_slice(symbol, category, side, slice_qty, entries):
    """Helper function to execute a single TWAP slice asynchronously"""
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

# Cached balance values for faster execution
_cached_balance = None
_balance_timestamp = 0

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    """
    Execute a trade if the setup meets all validation criteria
    
    Args:
        signal_data: Dictionary containing trade setup details
        max_risk: Maximum risk percentage per trade
        
    Returns:
        Trade details dictionary if executed, None if not
    """
    global _cached_balance, _balance_timestamp
    
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long").strip().lower()
    regime = signal_data.get("regime", "trending")
    
    # FIX: Add score validation at the executor level as final safeguard
    score = signal_data.get("score", 0)
    
    # Base thresholds (exactly matching the ones in main.py)
    base_thresholds = {
        "Scalp": 6.0,
        "Intraday": 6.5,
        "Swing": 7.0
    }
    min_score_required = base_thresholds.get(trade_type, 6.0)
    
    # Adjust based on regime - exactly matching main.py adjustments
    score_adjustments = {
        "volatile": {"scalp": -0.5, "intraday": -0.5, "swing": -0.5},
        "ranging": {"scalp": 0.5, "intraday": 0.5, "swing": 0.5},
        "trending": {"scalp": 0.0, "intraday": 0.0, "swing": 0.0},
    }
    adjust = score_adjustments.get(regime, {"scalp": 0, "intraday": 0, "swing": 0})
    
    if trade_type == "Scalp":
        min_score_required += adjust["scalp"]
    elif trade_type == "Intraday":
        min_score_required += adjust["intraday"]
    elif trade_type == "Swing":
        min_score_required += adjust["swing"]
        
    # Check for alternative strategies
    is_mean_reversion = "mean_reversion" in signal_data.get("tf_scores", {})
    is_breakout_sniper = "breakout_sniper" in signal_data.get("tf_scores", {})
    
    # Validation logic - matching the main.py validation
    score_valid = False
    
    if is_mean_reversion:
        # Mean Reversion has a minimum of 4.0, adjusted for regime
        mean_rev_min = 4.0
        if regime == "ranging":
            mean_rev_min += 0.5  # More stringent in ranging markets
        elif regime == "volatile":
            mean_rev_min -= 0.5  # Less stringent in volatile markets
            
        if score >= mean_rev_min:
            score_valid = True
            log(f"✅ Mean Reversion validation passed: {score:.2f} >= {mean_rev_min}", level="INFO")
        else:
            log(f"❌ Mean Reversion validation failed: {score:.2f} < {mean_rev_min}", level="WARN")
            
    elif is_breakout_sniper:
        # Breakout Sniper has a minimum of 4.0, adjusted for regime
        breakout_min = 4.0
        if regime == "ranging":
            breakout_min += 0.5  # More stringent in ranging markets
        elif regime == "volatile":
            breakout_min -= 0.5  # Less stringent in volatile markets
            
        if score >= breakout_min:
            score_valid = True
            log(f"✅ Breakout Sniper validation passed: {score:.2f} >= {breakout_min}", level="INFO")
        else:
            log(f"❌ Breakout Sniper validation failed: {score:.2f} < {breakout_min}", level="WARN")
            
    elif trade_type == "Swing" and signal_data.get("always_allow_swing", False):
        # Handle ALWAYS_ALLOW_SWING flag - only when explicitly passed in signal_data
        # Must be at least 50% of the adjusted threshold
        if score >= min_score_required:
            score_valid = True
            log(f"✅ Swing validation passed: {score:.2f} >= {min_score_required}", level="INFO")
        elif score >= min_score_required * 0.5:
            score_valid = True
            log(f"⚠️ Swing validation passed via ALWAYS_ALLOW_SWING: {score:.2f} >= {min_score_required * 0.5}", level="WARN")
        else:
            log(f"❌ Swing validation failed: {score:.2f} < {min_score_required * 0.5}", level="WARN")
            
    else:
        # Standard validation for regular trade types
        if score >= min_score_required:
            score_valid = True
            log(f"✅ {trade_type} validation passed: {score:.2f} >= {min_score_required}", level="INFO")
        else:
            log(f"❌ {trade_type} validation failed: {score:.2f} < {min_score_required}", level="WARN")
    
    # CRITICAL FIX: Exit early if validation fails
    if not score_valid:
        return None
        
    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        # OPTIMIZATION: Use cached balance if available and recent
        current_time = time.time()
        if _cached_balance is None or current_time - _balance_timestamp > 60:
            usdt_balance = await get_futures_available_balance()
            _cached_balance = usdt_balance
            _balance_timestamp = current_time
            log(f"💰 Fetched fresh balance: {usdt_balance} USDT")
        else:
            usdt_balance = _cached_balance
            log(f"💰 Using cached balance: {usdt_balance} USDT (cached {int(current_time - _balance_timestamp)}s ago)")
        
        if usdt_balance <= 0:
            error_msg = f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: Futures available balance is 0."
            log(error_msg, level="ERROR")
            await send_telegram_message(error_msg)
            return None

        price = float(signal_data.get("price", 1.0))
        planned_entry = price
        leverage = DEFAULT_LEVERAGE
        risk_amount = usdt_balance * max_risk
        position_value = risk_amount * leverage
        raw_qty = position_value / price
        
        log(f"📈 Trade calculation: Risk {max_risk*100}% of {usdt_balance} USDT = {risk_amount} USDT risk")
        log(f"📈 Position value: {position_value} USDT ({risk_amount} × {leverage})")
        log(f"📈 Raw quantity: {raw_qty} units ({position_value} ÷ {price})")
        qty = calculate_quantity(symbol, raw_qty)
        log(f"📈 Final quantity after rounding: {qty}")

        if qty <= 0:
            log(f"⚠️ Skipped {symbol}: Quantity too small.")
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", {})

        # Calculate exit tranches for this trade
        exit_tranches = calculate_exit_tranches(symbol, qty)
        log(f"📊 Exit tranches calculated for {symbol}: {exit_tranches}")

        # OPTIMIZATION: Run leverage setting and order cancellation in parallel
        leverage_task = signed_request("POST", "/v5/position/set-leverage", {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })

        cancel_task = signed_request("POST", "/v5/order/cancel-all", {
            "category": category, 
            "symbol": symbol
        })

        # Wait for both tasks
        await asyncio.gather(leverage_task, cancel_task)

        executed_entry = None
        order_result = None
        
        # Use TWAP only for volatile markets, otherwise immediate execution
        if regime == "volatile":
            executed_entry = await twap_execute_trade(symbol, qty, direction, category, slices=3, delay_sec=2)
            if not executed_entry:
                await send_telegram_message(f"❌ <b>{symbol}</b> TWAP failed.")
                return None
        else:
            # Execute market order immediately
            order_payload = {
                "category": category,
                "symbol": symbol,
                "side": "Buy" if direction.lower() == "long" else "Sell",
                "orderType": "Market",
                "qty": str(qty),
                "timeInForce": "IOC"
            }
        
            log(f"📤 Sending market order: {order_payload}")
            order_result = await signed_request("POST", "/v5/order/create", order_payload)
            log(f"📥 Order result: {order_result}")
            
            if order_result.get("retCode") == 0:
                executed_entry = float(order_result.get("result", {}).get("avgPrice", price)) or price
                
        # Only proceed if we have a valid entry price
        if executed_entry:
            # Calculate SL/TP based on actual entry price
            sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence, regime
            )

            # Get market price for SL validation
            try:
                ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": category, "symbol": symbol})
                mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", executed_entry))
                
                # Ensure SL is on the correct side of mark price
                if direction.lower() == "long" and sl >= mark_price:
                    sl = round(mark_price * 0.995, 6)  # 0.5% below mark price
                    log(f"🔧 Adjusted Long SL to {sl} (below mark price {mark_price})")
                elif direction.lower() == "short" and sl <= mark_price:
                    sl = round(mark_price * 1.005, 6)  # 0.5% above mark price
                    log(f"🔧 Adjusted Short SL to {sl} (above mark price {mark_price})")
            except Exception as e:
                log(f"⚠️ Failed to validate SL: {e}", level="WARN")

            side = "Sell" if direction.lower() == "long" else "Buy"

            # Use the first exit tranche for TP1
            tp1_qty = exit_tranches[0] if exit_tranches and len(exit_tranches) > 0 else round_qty(symbol, qty / 3)
            
            # Execute SL and TP orders in parallel
            from bybit_api import place_stop_loss
            sl_task = place_stop_loss(
                symbol=symbol,
                direction=direction,
                qty=qty,
                sl_price=sl,
                market_type=category
            )

            tp1_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": "Limit",
                "qty": str(tp1_qty),
                "price": str(tp1),
                "timeInForce": "GTC",
                "reduceOnly": True
            })

            # Wait for both orders to complete
            sl_result, tp1_result = await asyncio.gather(sl_task, tp1_task)
            
            log(f"📤 TP1 response: {tp1_result}")
            log(f"📤 SL response: {sl_result}")

            sl_order_id = sl_result.get("result", {}).get("orderId")
            if not sl_order_id:
                log(f"⚠️ Warning: No SL order ID returned. Will need to set SL manually.", level="WARN")

            # Also set up a more distant TP2 for catching bigger moves (optional)
            tp2_price = None
            if trade_type in ["Intraday", "Swing"]:
                # Set TP2 at 2x the TP1 distance for potential home runs
                tp2_pct = tp1_pct * 1.8  # Even more aggressive
                if direction.lower() == "long":
                    tp2_price = round(executed_entry * (1 + tp2_pct / 100), 6)
                else:
                    tp2_price = round(executed_entry * (1 - tp2_pct / 100), 6)
                
                log(f"🎯 Setting stretched TP2 at {tp2_price} ({tp2_pct:.2f}%) for potential pump")

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
                sl_strategy=f"ATR-{trade_type}"
            )

            return {
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
                "tp2_pct": tp2_pct * 1.8 if tp2_price else None,
                "trailing_pct": trailing_pct,
                "indicator_scores": indicator_scores,
                "used_indicators": used_indicators,
                "sl_order_id": sl_order_id,
                "exit_tranches": exit_tranches,
                "regime": regime
            }
        else:
            error_msg = f"❌ Order failed: {order_result.get('retMsg', 'Unknown error')}"
            log(error_msg, level="ERROR")
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\nSymbol: <b>{symbol}</b>\nReason: {order_result.get('retMsg', 'Unknown error')}"
            )

    except Exception as e:
        error_trace = traceback.format_exc()
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        log(f"Stack trace: {error_trace}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: {str(e)}"
        )

    return None
