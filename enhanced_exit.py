# enhanced_exit.py - Advanced exit management for trading bot

import asyncio
import traceback
from datetime import datetime
from logger import log, write_log
from error_handler import send_telegram_message, send_error_to_telegram
from bybit_api import place_market_order, place_stop_loss, place_stop_loss_with_retry, check_order_exists
from symbol_info import round_qty
from auto_reentry import log_exit, update_reentry_performance

def detect_tp1_hit(symbol, trade, current_price, candles):
    """
    Enhanced TP1 hit detection with checks for wicks and multiple conditions
    
    Args:
        symbol: Trading symbol
        trade: Trade object
        current_price: Current market price
        candles: Recent candles
        
    Returns:
        bool: True if TP1 should be considered hit
    """
    if trade.get("tp1_hit"):
        return False  # Already hit TP1
        
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    
    if not entry_price or not direction:
        return False
        
    # Calculate TP1 level (1.8% move)
    tp1_level = entry_price * 1.018 if direction == "long" else entry_price * 0.982
    
    # Check current price
    price_hit = (direction == "long" and current_price >= tp1_level) or \
               (direction == "short" and current_price <= tp1_level)
               
    if price_hit:
        return True
        
    # Check if any recent candle wicks hit TP1
    if candles and len(candles) >= 2:
        last_candle = candles[-1]
        
        # For long positions, check if high price reached TP1
        if direction == "long" and float(last_candle["high"]) >= tp1_level:
            log(f"🔍 TP1 hit detected for {symbol} via high price: {last_candle['high']} >= {tp1_level}")
            return True
            
        # For short positions, check if low price reached TP1
        elif direction == "short" and float(last_candle["low"]) <= tp1_level:
            log(f"🔍 TP1 hit detected for {symbol} via low price: {last_candle['low']} <= {tp1_level}")
            return True
            
    return False

def calculate_smart_trailing_stop(symbol, entry_price, current_price, direction, candles, base_trail_pct=0.5):
    """
    Calculate an advanced trailing stop with dynamic adjustments
    
    Args:
        symbol: Trading symbol
        entry_price: Entry price
        current_price: Current market price
        direction: 'long' or 'short'
        candles: Recent candles for analysis
        base_trail_pct: Base trailing percentage
        
    Returns:
        float: Calculated stop loss price
    """
    # 1. Basic move calculation
    price_move = 0
    if direction.lower() == "long":
        price_move = current_price - entry_price
        if price_move <= 0:
            return None  # No trailing until in profit
    else:  # short
        price_move = entry_price - current_price
        if price_move <= 0:
            return None  # No trailing until in profit
    
    # Determine relative profit percentage
    profit_pct = (price_move / entry_price) * 100
    log(f"📊 Current profit for {symbol}: {profit_pct:.2f}%")
    
    # 2. Volatility-based adjustment
    volatility_factor = 1.0
    
    # Check for momentum which would use wider trailing
    has_momentum = False
    if candles and len(candles) >= 10:
        # Simple momentum check - 3 consecutive candles up/down with higher volume
        recent = candles[-5:]
        consecutive_up = 0
        consecutive_down = 0
        
        for i in range(len(recent)):
            if float(recent[i]['close']) > float(recent[i]['open']):
                consecutive_up += 1
                consecutive_down = 0
            elif float(recent[i]['close']) < float(recent[i]['open']):
                consecutive_down += 1
                consecutive_up = 0
                
        has_momentum = (direction.lower() == "long" and consecutive_up >= 3) or \
                      (direction.lower() == "short" and consecutive_down >= 3)
    
    if has_momentum:
        volatility_factor = 1.5  # Much wider trail during momentum
        log(f"🚀 Momentum detected for {symbol} - using wider trail: {volatility_factor}x")
    
    # 3. Profit-based adjustment (trailing width increases with profit)
    profit_factor = 1.0
    if profit_pct > 5.0:
        profit_factor = 1.2  # Wider trail for bigger winners
        log(f"💰 Large profit for {symbol} ({profit_pct:.2f}%) - using wider trail: {profit_factor}x")
    elif profit_pct > 10.0:
        profit_factor = 1.4  # Even wider trail for huge winners
        log(f"💰 Massive profit for {symbol} ({profit_pct:.2f}%) - using much wider trail: {profit_factor}x")
    
    # 4. Combine all factors (up to specified caps)
    adjustment_factor = min(max(volatility_factor * profit_factor, 0.7), 2.0)
    adjusted_trail_pct = base_trail_pct * adjustment_factor
    
    log(f"📊 Final trailing % for {symbol}: {base_trail_pct:.2f}% → {adjusted_trail_pct:.2f}% (adj: {adjustment_factor:.2f}x)")
    
    # 5. Calculate actual SL price
    if direction.lower() == "long":
        sl_price = current_price * (1 - (adjusted_trail_pct / 100))
    else:  # short
        sl_price = current_price * (1 + (adjusted_trail_pct / 100))
    
    return round(sl_price, 6)  # Return rounded to appropriate precision

def should_trail_stop_enhanced(symbol, trade, current_price, candles):
    """
    Enhanced trailing stop logic
    
    Args:
        symbol: Trading symbol
        trade: Trade object with trade details
        current_price: Current market price
        candles: Recent price candles
        
    Returns:
        float or None: New stop loss price if trailing should activate, None otherwise
    """
    if not trade.get("tp1_hit"):
        return None
    
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    current_trailing_sl = trade.get("trailing_sl")
    base_trail_pct = trade.get("trailing_pct", 0.5)
    
    # Calculate new SL price using smart method
    new_sl = calculate_smart_trailing_stop(
        symbol=symbol,
        entry_price=entry_price,
        current_price=current_price,
        direction=direction,
        candles=candles,
        base_trail_pct=base_trail_pct
    )
    
    if not new_sl:
        return None
    
    # Only update if new SL is better than current
    if current_trailing_sl:
        if direction == "long" and new_sl <= current_trailing_sl:
            return None
        if direction == "short" and new_sl >= current_trailing_sl:
            return None
            
    return new_sl

async def execute_partial_exit_with_retry(symbol, trade, exit_percentage, max_attempts=3):
    """
    Execute a partial exit with retry logic
    
    Args:
        symbol: Trading symbol
        trade: Trade object from active_trades
        exit_percentage: Percentage of position to exit (e.g., 33 for 33%)
        max_attempts: Maximum retry attempts
        
    Returns:
        bool: True if partial exit was successful
    """
    direction = trade.get("direction", "").lower()
    total_qty = trade.get("qty", 0)
    
    if not direction or not total_qty or total_qty <= 0:
        log(f"❌ Cannot execute partial exit for {symbol}: Invalid trade data", level="ERROR")
        return False
    
    # Calculate exit quantity
    exit_qty = total_qty * (exit_percentage / 100)
    
    # Ensure exit quantity meets minimum requirements
    from symbol_info import round_qty
    min_qty = 0.001  # Default minimum quantity
    
    exit_qty = max(round_qty(symbol, exit_qty), min_qty)
    
    # Don't exit more than we have
    exit_qty = min(exit_qty, total_qty)
    
    log(f"🔍 Attempting partial exit for {symbol}: {exit_qty} units ({exit_percentage}% of {total_qty})")
    
    # Try to execute the exit with retries
    for attempt in range(max_attempts):
        try:
            # Execute market order
            side = "Sell" if direction == "long" else "Buy"
            
            result = await place_market_order(
                symbol=symbol,
                side=side,
                qty=str(exit_qty),
                market_type="linear",
                reduce_only=True
            )
            
            if result.get("retCode") == 0:
                # Update trade record with remaining quantity
                trade["qty"] = round_qty(symbol, total_qty - exit_qty)
                
                # Log the partial exit
                log(f"💰 Partial exit ({exit_percentage}%) executed for {symbol}: {exit_qty} out of {total_qty}")
                write_log(f"PARTIAL EXIT: {symbol} | {exit_percentage}% | Qty: {exit_qty}/{total_qty}")
                
                # Record in exit tranches history
                if "exit_tranches_history" not in trade:
                    trade["exit_tranches_history"] = []
                
                trade["exit_tranches_history"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "percentage": exit_percentage,
                    "qty": exit_qty
                })
                
                return True
            else:
                log(f"❌ Partial exit attempt {attempt+1}/{max_attempts} failed: {result.get('retMsg')}", level="ERROR")
                
                # Brief pause before retry
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        except Exception as e:
            log(f"❌ Error in partial exit attempt {attempt+1}/{max_attempts}: {e}", level="ERROR")
            
            # Brief pause before retry
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    
    # If we get here, all attempts failed
    log(f"❌ All partial exit attempts failed for {symbol}", level="ERROR")
    return False

async def execute_tp1_strategy(symbol, trade, current_price, candles):
    """
    FIXED: Comprehensive function to handle TP1 hit - Only exits 50% of position
    
    Args:
        symbol: Trading symbol
        trade: Trade object from active_trades
        current_price: Current market price
        candles: Price candles for analysis
        
    Returns:
        bool: True if TP1 execution was successful
    """
    try:
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        total_qty = trade.get("qty", 0)
        
        if not entry_price or not direction or total_qty <= 0:
            log(f"❌ Cannot execute TP1 for {symbol}: Missing trade data", level="ERROR")
            return False
        
        log(f"🎯 Executing TP1 strategy for {symbol} at {current_price}")
        
        # 1. Mark TP1 as hit in trade object - DON'T SET EXITED = TRUE
        trade["tp1_hit"] = True
        trade["tp1_hit_cycle"] = trade.get("cycles", 0)
        trade["break_even_triggered"] = True
        trade["tp1_price"] = current_price
        
        # 2. Calculate 50% exit quantity
        exit_qty = total_qty * 0.5  # 50% of position
        
        # Round to proper decimal places based on symbol
        from symbol_info import round_qty
        exit_qty = round_qty(symbol, exit_qty)
        exit_qty = min(exit_qty, total_qty)
        
        log(f"🔍 Executing 50% partial exit: {exit_qty} units out of {total_qty}")
        
        # 3. Execute first partial exit (retry up to 3 times)
        first_tranche_executed = False
        exit_success = await execute_partial_exit_with_retry(symbol, trade, 50)  # 50% exit
        
        if exit_success:
            # CRITICAL: Update remaining quantity
            remaining_qty = total_qty - exit_qty
            trade["qty"] = remaining_qty  # Update to remaining position size
            
            trade["tp1_partial_exit"] = True
            log(f"💰 50% partial exit executed for {symbol}. Remaining: {remaining_qty}")
            first_tranche_executed = True
            
            # Track the exit
            if "exit_tranches_history" not in trade:
                trade["exit_tranches_history"] = []
            
            trade["exit_tranches_history"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "percentage": 50,
                "qty": exit_qty,
                "price": current_price,
                "reason": "TP1_Strategy"
            })
            
        else:
            log(f"⚠️ 50% partial exit failed for {symbol}", level="WARN")
        
        # 4. Move stop loss to breakeven (retry up to 3 times)
        sl_updated = False
        
        # Define update SL function for retry
        async def update_sl_to_breakeven():
            from monitor import update_stop_loss_order
            return await update_stop_loss_order(symbol, trade, entry_price)
        
        # Try updating SL with retry
        for attempt in range(3):
            try:
                if not sl_updated:
                    sl_updated = await update_sl_to_breakeven()
                    
                    if sl_updated:
                        log(f"🛡️ Stop loss moved to breakeven for {symbol}: {entry_price}")
                        trade["trailing_sl"] = entry_price  # Set initial trailing SL
                        trade["trailing_active"] = True     # Activate trailing
                    else:
                        log(f"❌ Failed to update SL to breakeven for {symbol}", level="ERROR")
                
            except Exception as e:
                log(f"❌ Error in SL update attempt {attempt+1}/3 for {symbol}: {e}", level="ERROR")
                
            # If successful, break out of retry loop
            if sl_updated:
                break
                
            # Otherwise wait before retrying
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
            
        # 5. Send notification of TP1 hit
        msg = f"🎯 <b>TP1 Hit</b> on <b>{symbol}</b> @ {current_price:.6f}"
        if first_tranche_executed:
            msg += f"\n💰 50% Position Exited ({exit_qty} units)"
            msg += f"\n📍 50% Remaining ({trade['qty']} units)"
        if sl_updated:
            msg += f"\n🛡️ SL Moved to Breakeven: {entry_price:.6f}"
            msg += f"\n📈 Trailing stop active for remaining position"
            
        await send_telegram_message(msg)
        
        # 6. Log for analysis - Log as PARTIAL exit, not full exit
        if first_tranche_executed:
            # Calculate profit for the exited portion
            if direction == "long":
                profit_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                profit_pct = ((entry_price - current_price) / entry_price) * 100
            
            # This is a partial exit, not a full exit, so we don't log_exit here
            # Just update performance tracking
            write_log(f"TP1_PARTIAL_50PCT: {symbol} | Profit at TP1: {profit_pct:.2f}% | Remaining: {trade['qty']}")
        
        # 7. Save changes
        from monitor import save_active_trades
        save_active_trades()
        
        return first_tranche_executed
        
    except Exception as e:
        log(f"❌ Error in TP1 strategy execution for {symbol}: {e}", level="ERROR")
        import traceback
        log(f"Stack trace: {traceback.format_exc()}", level="ERROR")
        return False

async def handle_post_tp1_momentum(symbol, trade, current_price, candles):
    """
    Handle momentum detection after TP1 hit
    
    Args:
        symbol: Trading symbol
        trade: Trade object from active_trades
        current_price: Current market price
        candles: Price candles for analysis
        
    Returns:
        bool: True if second exit tranche was executed
    """
    try:
        if not trade.get("tp1_hit") or trade.get("tp2_exit_executed"):
            return False
            
        # Get required values
        tp1_price = trade.get("tp1_price")
        if not tp1_price:
            return False
            
        # Check for significant move after TP1
        pump_move_pct = ((current_price - tp1_price) / tp1_price) * 100 if trade.get("direction", "").lower() == "long" else \
                        ((tp1_price - current_price) / tp1_price) * 100
                        
        # Check for momentum
        has_momentum = detect_momentum_surge(candles) if candles else False
        
        # Alert only once for smart pump detection
        if pump_move_pct >= 1.0 and not trade.get("smart_pump_alerted"):
            trade["smart_pump_alerted"] = True
            await send_telegram_message(
                f"🚀 <b>Smart Pump After TP1</b> on {symbol}\n"
                f"Move: +{pump_move_pct:.2f}% beyond TP1"
            )
            write_log(f"SMART PUMP AFTER TP1: {symbol} | +{pump_move_pct:.2f}% beyond TP1")
            
        # Execute second tranche if significant move and momentum detected
        if pump_move_pct >= 1.0 and has_momentum and not trade.get("tp2_exit_executed"):
            # Check if we have exit tranches
            if trade.get("exit_tranches") and len(trade.get("exit_tranches", [])) >= 2:
                second_tranche = trade["exit_tranches"][1]

                if exit_success:
                    # Calculate profit at this exit point
                    entry_price = trade.get("entry_price")
                    direction = trade.get("direction", "").lower()
            
                    if direction == "long":
                        profit_pct = ((current_price - entry_price) / entry_price) * 100
                    else:
                        profit_pct = ((entry_price - current_price) / entry_price) * 100
            
                    # Log this momentum-based exit
                    write_log(f"MOMENTUM_EXIT: {symbol} | Profit: {profit_pct:.2f}% | Pump: {pump_move_pct:.2f}%")
                
                # Execute second partial exit
                exit_success = await execute_partial_exit_with_retry(
                    symbol=symbol,
                    trade=trade,
                    exit_percentage=50  # 50% of remaining position (approx 33% of original)
                )
                
                if exit_success:
                    # Mark as executed
                    trade["tp2_exit_executed"] = True
                    
                    await send_telegram_message(
                        f"💰 <b>Second Partial Exit</b> on <b>{symbol}</b>\n"
                        f"50% of remaining position exited during pump\n"
                        f"Move: +{pump_move_pct:.2f}% beyond TP1"
                    )

                    # Reentry integration logging
                    if "entry_price" in trade:
                        entry_price = trade["entry_price"]
                        direction = trade["direction"].lower()
                    if direction == "long":
                        profit_pct = ((current_price - entry_price) / entry_price) * 100
                    else:
                        profit_pct = ((entry_price - current_price) / entry_price) * 100

                    log_exit(symbol, trade, price=current_price, reason="TP2_Momentum", profit_pct=profit_pct)
                    update_reentry_performance(symbol, success=(profit_pct > 0), profit_pct=profit_pct)
                    
                    log(f"💰 Second partial exit executed for {symbol} during pump")
                    write_log(f"SECOND EXIT: {symbol} | Price: {current_price} | Pump: {pump_move_pct:.2f}%")
                    
                    return True
                else:
                    log(f"❌ Failed to execute second exit tranche for {symbol} during pump", level="ERROR")
            else:
                log(f"⚠️ No second exit tranche available for {symbol} for pump exit", level="WARN")
                
        return False
        
    except Exception as e:
        log(f"❌ Error in post-TP1 momentum handler for {symbol}: {e}", level="ERROR")
        return False

def detect_momentum_surge(candles, lookback=5):
    """
    Detect if price is showing strong momentum based on recent candles.
    Returns True if strong momentum is detected
    """
    if len(candles) < lookback + 5:
        return False
        
    # Get recent candles and slightly older candles for comparison
    recent = candles[-lookback:]
    prior = candles[-(lookback+5):-lookback]
    
    # Calculate average volume increase
    recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
    prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
    vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
    
    # Calculate price momentum
    recent_opens = [float(c['open']) for c in recent]
    recent_closes = [float(c['close']) for c in recent]
    
    # Count consecutive up/down candles
    if recent_closes[-1] > recent_opens[-1]:  # Current candle is up
        consecutive_up = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] > recent_opens[i]:
                consecutive_up += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive up candles with 2x+ volume
        if consecutive_up >= 3 and vol_increase >= 2.0:
            return True
    
    # For downward momentum (for shorts)
    if recent_closes[-1] < recent_opens[-1]:  # Current candle is down
        consecutive_down = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] < recent_opens[i]:
                consecutive_down += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive down candles with 2x+ volume
        if consecutive_down >= 3 and vol_increase >= 2.0:
            return True
    
    return False

def calculate_dynamic_exit_tranches(symbol, total_qty, trade_type="Intraday", volatility_level=1.0, 
                                  momentum_score=0, has_pump_potential=False):
    """
    Calculate exit tranches dynamically based on market conditions and trade type
    
    Args:
        symbol: Trading symbol for precision lookup
        total_qty: Total position size
        trade_type: "Scalp", "Intraday", or "Swing"
        volatility_level: Relative volatility (1.0 = normal)
        momentum_score: 0-1 momentum indicator
        has_pump_potential: Flag indicating setup has pump characteristics
        
    Returns:
        list: List of quantities for each exit tranche
    """
    if total_qty <= 0:
        return []
    
    # Get symbol precision for rounding
    from symbol_info import get_precision
    precision = get_precision(symbol)
    min_qty = 0.001  # Fallback min quantity
    
    # Base distribution by trade type
    if trade_type == "Scalp":
        # Scalps: Take profit quickly with larger first tranche
        distribution = [0.40, 0.30, 0.30]
    elif trade_type == "Swing":
        # Swings: Let profits run with smaller first tranche
        distribution = [0.25, 0.35, 0.40]
    else:  # Intraday default
        distribution = [0.33, 0.33, 0.34]
    
    # Adjust for volatility
    if volatility_level > 1.5:  # High volatility
        # In high volatility, secure more profit early
        distribution[0] += 0.05
        distribution[2] -= 0.05
        log(f"📊 High volatility adjustment: {distribution}")
    elif volatility_level < 0.7:  # Low volatility
        # In low volatility, can be more patient
        distribution[0] -= 0.05
        distribution[2] += 0.05
        log(f"📊 Low volatility adjustment: {distribution}")
    
    # Adjust for momentum
    if momentum_score > 0.7:  # Strong momentum
        # In strong momentum, keep more for potential runners
        distribution[0] -= 0.08
        distribution[2] += 0.08
        log(f"🚀 Strong momentum adjustment: {distribution}")
    
    # Special case for pump potential setups
    if has_pump_potential:
        # Optimize for potential large moves
        distribution = [0.30, 0.30, 0.40]  # Weight more to final tranche
        log(f"💥 Pump potential adjustment: {distribution}")
    
    # Calculate raw tranches
    raw_tranches = [total_qty * dist for dist in distribution]
    
    # Round to valid quantities
    valid_tranches = []
    for qty in raw_tranches:
        # Ensure minimum notional value
        rounded_qty = round_qty(symbol, qty)
        if rounded_qty < min_qty:
            rounded_qty = min_qty
        valid_tranches.append(rounded_qty)
    
    # Adjust final tranche to ensure total equals original quantity
    sum_first_tranches = sum(valid_tranches[:-1])
    final_tranche = round_qty(symbol, max(total_qty - sum_first_tranches, min_qty))
    valid_tranches[-1] = final_tranche
    
    log(f"📊 Exit tranches for {symbol}: {valid_tranches} (from total {total_qty})")
    
    # Handle edge case where sum of tranches exceeds total due to rounding
    if sum(valid_tranches) > total_qty * 1.01:  # Allow 1% tolerance
        log(f"⚠️ Tranches sum exceeds total - adjusting")
        # Recalculate with priority on later tranches
        valid_tranches[0] = round_qty(symbol, max(total_qty - valid_tranches[1] - valid_tranches[2], min_qty))
    
    return valid_tranches
