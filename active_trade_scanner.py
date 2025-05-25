# active_trade_scanner.py - FIXED VERSION with immediate trailing and fixed percentages

import asyncio
import time
import traceback
import json
import os
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order
from error_handler import send_telegram_message, send_error_to_telegram
from activity_logger import log_trade_to_file
from ai_memory import log_trade_result
from strategy_performance import log_strategy_result
from exit_manager import detect_momentum_surge

try:
    from monitor import active_trades as monitor_active_trades
    log("✅ HF SCANNER: Successfully imported active_trades from monitor")
except ImportError:
    monitor_active_trades = {}
    log("⚠️ HF SCANNER: Could not import active_trades from monitor")

# Configuration for active trade scanner
ACTIVE_SCAN_INTERVAL = 3  # Check active trades every 3 seconds
MAX_CONCURRENT_CHECKS = 5  # Limit concurrent API calls
PERSIST_PATH = "monitor_active_trades.json"

# Cache for active trades to avoid constant file reads
_active_trades_cache = {}
_cache_timestamp = 0
_cache_ttl = 10  # Cache TTL in seconds

# FIXED PERCENTAGES for SL/TP
FIXED_PERCENTAGES = {
    "Scalp": {
        "tp1_pct": 1.2,      # +1.2% take profit
        "sl_pct": 0.8,       # -0.8% stop loss
        "trailing_pct": 0.4  # 0.4% trailing stop
    },
    "Intraday": {
        "tp1_pct": 2.0,      # +2.0% take profit
        "sl_pct": 1.0,       # -1.0% stop loss
        "trailing_pct": 1.0  # 1.0% trailing stop
    },
    "Swing": {
        "tp1_pct": 5.0,      # Keep existing for swing
        "sl_pct": 2.0,       # Keep existing for swing
        "trailing_pct": 1.5  # Keep existing for swing
    }
}

def load_active_trades_directly():
    """Load active trades directly from file, bypassing potential import issues"""
    global _active_trades_cache, _cache_timestamp
    
    # Use cache if recent enough
    current_time = time.time()
    if _active_trades_cache and (current_time - _cache_timestamp) < _cache_ttl:
        return _active_trades_cache
    
    try:
        if os.path.exists(PERSIST_PATH):
            with open(PERSIST_PATH, 'r') as f:
                trades = json.load(f)
                
            # Filter out exited trades and return only active ones
            active_trades = {symbol: trade for symbol, trade in trades.items() 
                           if not trade.get("exited", False)}
            
            # Update cache
            _active_trades_cache = active_trades
            _cache_timestamp = current_time
            
            log(f"🔍 HF SCANNER: Loaded {len(active_trades)} active trades from file")
            return active_trades
        else:
            log(f"⚠️ HF SCANNER: No trades file found at {PERSIST_PATH}")
            return {}
    except Exception as e:
        log(f"❌ HF SCANNER: Error loading active trades: {e}", level="ERROR")
        return {}

def save_active_trades_directly(trades):
    """Save active trades directly to file"""
    try:
        # Load existing trades first to avoid overwriting
        existing_trades = {}
        if os.path.exists(PERSIST_PATH):
            with open(PERSIST_PATH, 'r') as f:
                existing_trades = json.load(f)
        
        # Update with modified trades
        existing_trades.update(trades)
        
        with open(PERSIST_PATH, 'w') as f:
            json.dump(existing_trades, f, indent=2)
            
        # Clear cache to force reload
        global _active_trades_cache, _cache_timestamp
        _active_trades_cache = {}
        _cache_timestamp = 0
        
        log(f"💾 HF SCANNER: Saved {len(trades)} updated trades")
    except Exception as e:
        log(f"❌ HF SCANNER: Error saving trades: {e}", level="ERROR")

async def fetch_current_price(symbol):
    """Fetch current price for a symbol with optimized API call"""
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
        if ticker_resp.get("retCode") == 0:
            result_list = ticker_resp.get("result", {}).get("list", [])
            if result_list:
                mark_price = float(result_list[0].get("markPrice", 0))
                last_price = float(result_list[0].get("lastPrice", 0))
                return {
                    "mark_price": mark_price,
                    "last_price": last_price,
                    "timestamp": time.time()
                }
    except Exception as e:
        log(f"❌ HF SCANNER: Error fetching price for {symbol}: {e}", level="ERROR")
    return None

async def update_stop_loss_order(symbol, trade, new_sl_price):
    """Update stop loss order - simplified version for HF scanner"""
    try:
        from bybit_api import place_stop_loss_with_retry
        
        direction = trade.get("direction", "").lower()
        qty = trade.get("qty")
        old_sl_order_id = trade.get("sl_order_id")
        
        if not direction or not qty:
            log(f"❌ HF SCANNER: Cannot update SL for {symbol}: Missing trade data", level="ERROR")
            return False
        
        # Cancel existing SL if present
        if old_sl_order_id:
            try:
                cancel_result = await signed_request("POST", "/v5/order/cancel", {
                    "category": "linear",
                    "symbol": symbol,
                    "orderId": old_sl_order_id
                })
                
                if cancel_result.get("retCode") != 0:
                    log(f"⚠️ HF SCANNER: Failed to cancel old SL for {symbol}: {cancel_result.get('retMsg')}", level="WARN")
            except Exception as e:
                log(f"❌ HF SCANNER: Error cancelling SL order: {e}", level="ERROR")
        
        # Place new SL order with retry
        sl_resp = await place_stop_loss_with_retry(
            symbol=symbol,
            direction=direction,
            qty=qty,
            sl_price=new_sl_price
        )
        
        if sl_resp.get("retCode") == 0:
            # Update trade record
            trade["sl_order_id"] = sl_resp.get("result", {}).get("orderId")
            trade["trailing_sl"] = new_sl_price
            
            await send_telegram_message(f"🔐 <b>HF Scanner: SL Updated</b> for {symbol} | New SL: {new_sl_price}")
            log(f"🔐 HF SCANNER: SL updated for {symbol} to {new_sl_price}")
            write_log(f"HF_SCANNER_SL_UPDATE: {symbol} | New SL: {new_sl_price}")
            return True
        else:
            log(f"❌ HF SCANNER: Failed to place new SL: {sl_resp.get('retMsg')}", level="ERROR")
            return False
            
    except Exception as e:
        log(f"❌ HF SCANNER: Error placing new SL order: {e}", level="ERROR")
        return False

async def execute_partial_exit_with_retry(symbol, trade, exit_percentage, max_attempts=3):
    """Execute a partial exit with retry logic - HF scanner version"""
    direction = trade.get("direction", "").lower()
    total_qty = trade.get("qty", 0)
    
    if not direction or not total_qty or total_qty <= 0:
        log(f"❌ HF SCANNER: Cannot execute partial exit for {symbol}: Invalid trade data", level="ERROR")
        return False
    
    # Calculate exit quantity
    exit_qty = total_qty * (exit_percentage / 100)
    
    # Ensure exit quantity meets minimum requirements
    from symbol_info import round_qty
    min_qty = 0.001  # Default minimum quantity
    
    exit_qty = max(round_qty(symbol, exit_qty), min_qty)
    
    # Don't exit more than we have
    exit_qty = min(exit_qty, total_qty)
    
    log(f"🔍 HF SCANNER: Attempting partial exit for {symbol}: {exit_qty} units ({exit_percentage}% of {total_qty})")
    
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
                log(f"💰 HF SCANNER: Partial exit ({exit_percentage}%) executed for {symbol}: {exit_qty} out of {total_qty}")
                write_log(f"HF_SCANNER_PARTIAL_EXIT: {symbol} | {exit_percentage}% | Qty: {exit_qty}/{total_qty}")
                
                # Record in exit tranches history
                if "exit_tranches_history" not in trade:
                    trade["exit_tranches_history"] = []
                
                trade["exit_tranches_history"].append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "percentage": exit_percentage,
                    "qty": exit_qty,
                    "source": "hf_scanner_let_winners_run"
                })
                
                return True
            else:
                log(f"❌ HF SCANNER: Partial exit attempt {attempt+1}/{max_attempts} failed: {result.get('retMsg')}", level="ERROR")
                
                # Brief pause before retry
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        except Exception as e:
            log(f"❌ HF SCANNER: Error in partial exit attempt {attempt+1}/{max_attempts}: {e}", level="ERROR")
            
            # Brief pause before retry
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    
    # If we get here, all attempts failed
    log(f"❌ HF SCANNER: All partial exit attempts failed for {symbol}", level="ERROR")
    return False

async def process_active_trade(symbol, trade, live_candles):
    """Process a single active trade with high-frequency monitoring"""
    if trade.get("exited"):
        return

    # Get required trade data
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    trade_type = trade.get("trade_type", "Intraday")
    
    if not direction or not entry_price:
        log(f"❌ HF SCANNER: Invalid trade data for {symbol}: direction={direction}, entry={entry_price}")
        return
    
    # Get current price
    price_data = await fetch_current_price(symbol)
    if not price_data:
        log(f"❌ HF SCANNER: Failed to fetch current price for {symbol}")
        return
        
    current_price = price_data.get("mark_price", price_data.get("last_price", 0))
    if current_price <= 0:
        log(f"❌ HF SCANNER: Invalid current price for {symbol}: {current_price}")
        return
    
    # Get candles for momentum detection
    candles = None
    if symbol in live_candles and '1' in live_candles[symbol]:
        candles = list(live_candles[symbol]['1'])
    
    # Check for momentum
    has_momentum = False
    if candles and len(candles) >= 10:
        has_momentum = detect_momentum_surge(candles)
        if has_momentum:
            log(f"🚀 HF SCANNER: Momentum detected for {symbol}")
    
    # Get FIXED percentages based on trade type
    fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
    tp1_pct = fixed_params["tp1_pct"]
    trailing_pct = fixed_params["trailing_pct"]
    
    # Calculate TP1 level if not already stored
    tp1_level = trade.get("tp1_target")
    if not tp1_level:
        # Calculate using the FIXED percentages
        tp1_level = entry_price * (1 + tp1_pct/100) if direction == "long" else entry_price * (1 - tp1_pct/100)
        log(f"📊 HF SCANNER: Calculated TP1 for {symbol} using fixed {tp1_pct}% = {tp1_level}")
        
        # Store the calculated TP1 for future use
        trade["tp1_target"] = tp1_level
        trade["tp1_pct"] = tp1_pct

    # PRIORITY 1: Check for TP1 hit if not already hit
    if not trade.get("tp1_hit"):
        # Custom TP1 hit detection using the ACTUAL target
        tp1_hit = False
        if direction == "long" and current_price >= tp1_level:
            tp1_hit = True
        elif direction == "short" and current_price <= tp1_level:
            tp1_hit = True
        
        # Also check recent candle wicks
        if not tp1_hit and candles and len(candles) >= 2:
            last_candle = candles[-1]
            if direction == "long" and float(last_candle["high"]) >= tp1_level:
                tp1_hit = True
            elif direction == "short" and float(last_candle["low"]) <= tp1_level:
                tp1_hit = True
    
        if tp1_hit:
            # Log TP1 detection
            log(f"🎯 HF SCANNER (LET WINNERS RUN): TP1 hit detected for {symbol} at {current_price} (target was {tp1_level})")
        
            # Calculate actual profit percentage achieved
            profit_pct = ((tp1_level - entry_price) / entry_price * 100) if direction == "long" else \
                        ((entry_price - tp1_level) / entry_price * 100)
        
            # Mark TP1 as hit in trade object
            trade["tp1_hit"] = True
            trade["tp1_hit_cycle"] = trade.get("cycles", 0)
            trade["tp1_price"] = tp1_level  # Use the target that was actually hit
            trade["break_even_triggered"] = True
            trade["tp1_hit_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trade["let_winners_run_active"] = True
            
            # IMPORTANT: Set the fixed trailing percentage for immediate activation
            trade["trailing_pct"] = trailing_pct  # Use the fixed value
        
            # Send detailed notification with ACTUAL profit percentage
            await send_telegram_message(
                f"🎯 <b>HF Scanner: TP1 Hit (Let Winners Run)</b> on <b>{symbol}</b>\n"
                f"Target: {tp1_level:.6f}\n"
                f"Current: {current_price:.6f}\n"
                f"Entry: {entry_price:.6f}\n"
                f"Profit: {profit_pct:.2f}%\n"
                f"🚀 Strategy: Only 20% exit - letting 80% ride!\n"
                f"📍 Trailing: {trailing_pct}% activates immediately\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # Execute partial exit if not already done
            if not trade.get("tp1_partial_exit"):
                exit_success = await execute_partial_exit_with_retry(symbol, trade, 20)
                if exit_success:
                    trade["tp1_partial_exit"] = True
                    write_log(f"HF_SCANNER_TP1_PARTIAL_EXIT_LWR: {symbol} | 20% exit | Price: {current_price} | 80% riding")
                else:
                    log(f"⚠️ HF SCANNER: Partial exit (20%) failed for {symbol}", level="WARN")
            
            # Move SL to breakeven if not already done
            if not trade.get("tp1_sl_moved"):
                sl_updated = await update_stop_loss_order(symbol, trade, entry_price)
                if sl_updated:
                    trade["tp1_sl_moved"] = True
                    write_log(f"HF_SCANNER_TP1_SL_UPDATE: {symbol} | New SL: {entry_price} (breakeven)")
                else:
                    log(f"⚠️ HF SCANNER: SL update failed for {symbol}", level="WARN")
            
            # Log trade result
            trade_type = trade.get("trade_type", "Intraday")
            score = trade.get("score_history", [0])[-1] if trade.get("score_history") else 0
            log_trade_to_file(
                symbol=symbol,
                direction=direction,
                entry=entry_price,
                sl=entry_price,  # Now at breakeven
                tp1=tp1_level,
                tp2=None,
                result="tp1_let_winners_run",
                score=score,
                trade_type=trade_type,
                confidence=0
            )
            
            # Save the updated trade data
            save_active_trades_directly({symbol: trade})
    
    # PRIORITY 2: Check trailing stop (after TP1 hit) - IMMEDIATE ACTIVATION
    elif trade.get("tp1_hit") and trade.get("trailing_pct"):
        try:
            trailing_pct = trade.get("trailing_pct")  # Get the fixed trailing %
            current_trailing_sl = trade.get("trailing_sl")
            
            # IMMEDIATE TRAILING - no activation threshold
            # Calculate new trailing SL position
            if direction == "long":
                new_sl = current_price * (1 - trailing_pct/100)
            else:
                new_sl = current_price * (1 + trailing_pct/100)
            
            # Round to 6 decimal places
            new_sl = round(new_sl, 6)
            
            # Only update if new SL is better than current
            should_update = False
            if current_trailing_sl is None:
                should_update = True
                log(f"🔒 HF SCANNER: Initial trailing SL for {symbol} at {new_sl} ({trailing_pct}% from {current_price})")
            elif direction == "long" and new_sl > current_trailing_sl:
                improvement = ((new_sl - current_trailing_sl) / current_trailing_sl) * 100
                should_update = True
                log(f"🔒 HF SCANNER: Trailing SL improved for {symbol}: {current_trailing_sl} → {new_sl} (+{improvement:.2f}%)")
            elif direction == "short" and new_sl < current_trailing_sl:
                improvement = ((current_trailing_sl - new_sl) / current_trailing_sl) * 100
                should_update = True
                log(f"🔒 HF SCANNER: Trailing SL improved for {symbol}: {current_trailing_sl} → {new_sl} (+{improvement:.2f}%)")
            
            if should_update:
                sl_updated = await update_stop_loss_order(symbol, trade, new_sl)
                if sl_updated:
                    save_active_trades_directly({symbol: trade})
                    
        except Exception as e:
            log(f"❌ HF SCANNER: Error updating trailing SL for {symbol}: {e}", level="ERROR")
    
    # PRIORITY 3: Check if trailing SL hit
    if trade.get("tp1_hit") and trade.get("trailing_sl"):
        trailing_sl = trade.get("trailing_sl")
        
        # Check for SL hit with small buffer for wicks
        sl_buffer = 0.002  # 0.2% buffer
        
        # Check for SL hit
        sl_hit = False
        if direction == "long":
            sl_hit = current_price <= (trailing_sl * (1 - sl_buffer))
        elif direction == "short": 
            sl_hit = current_price >= (trailing_sl * (1 + sl_buffer))
            
        if sl_hit:
            try:
                # Log SL hit
                log(f"⛔ HF SCANNER (LET WINNERS RUN): Trailing SL hit for {symbol} at {current_price}")
                
                # Exit remaining position (should be around 80% depending on exits taken)
                remaining_qty = trade.get("qty", 0)
                if remaining_qty > 0:
                    side = "Sell" if direction == "long" else "Buy"
                    exit_result = await place_market_order(
                        symbol=symbol,
                        side=side,
                        qty=str(remaining_qty),
                        market_type="linear",
                        reduce_only=True
                    )
                    
                    if exit_result.get("retCode") == 0:
                        log(f"✅ HF SCANNER (LWR): Final position exit executed for {symbol} - {remaining_qty} units (~80% of original position)")
                    else:
                        log(f"❌ HF SCANNER: Final exit failed: {exit_result.get('retMsg')}", level="ERROR")
                
                # Mark trade as exited
                trade["exited"] = True
                trade["exit_price"] = current_price
                trade["exit_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trade["exit_reason"] = "trailing_sl_let_winners_run"
                trade["let_winners_run_completed"] = True
                
                # Calculate final profit
                profit_pct = ((current_price - entry_price) / entry_price * 100) if direction == "long" else \
                            ((entry_price - current_price) / entry_price * 100)
                
                # Send notification with results
                await send_telegram_message(
                    f"⛔ <b>HF Scanner: LET WINNERS RUN Complete</b> on {symbol}\n"
                    f"Final Price: {current_price:.6f}\n"
                    f"SL Level: {trailing_sl:.6f}\n"
                    f"Total Profit: {profit_pct:.2f}%\n"
                    f"🎯 Strategy: 20% @ TP1, 80% rode the trend!\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                # Log trade result with special designation
                trade_type = trade.get("trade_type", "Intraday")
                score = trade.get("score_history", [0])[-1] if trade.get("score_history") else 0
                           
                result = "let_winners_run_win" if profit_pct > 0 else "let_winners_run_loss"
                
                log_trade_to_file(
                    symbol=symbol,
                    direction=direction,
                    entry=entry_price,
                    sl=trailing_sl,
                    tp1=trade.get("tp1_price"),
                    tp2=None,
                    result=result,
                    score=score,
                    trade_type=trade_type,
                    confidence=0
                )
                
                # Log AI memory and strategy performance with special category
                tf_scores = {}
                log_trade_result(symbol, tf_scores, "let_winners_run_" + ("win" if profit_pct > 0 else "loss"))
                
                # Get strategy type for logging
                strategy = "let_winners_run_strategy"  # Special strategy designation
                
                log_strategy_result(strategy, "win" if profit_pct > 0 else "loss", round(profit_pct, 2))
                
                # Save updated trade status
                save_active_trades_directly({symbol: trade})
                
            except Exception as e:
                log(f"❌ HF SCANNER: Error processing SL hit for {symbol}: {e}", level="ERROR")
                log(traceback.format_exc(), level="ERROR")

async def high_frequency_scanner(live_candles):
    """Main high-frequency scanner loop for active trades only"""
    log("🚀 HF SCANNER: Starting high-frequency active trade scanner")
    
    # Give some time for the main bot to initialize
    await asyncio.sleep(10)
    
    consecutive_empty_checks = 0
    max_empty_checks = 10  # Log warning after 10 consecutive empty checks
    
    while True:
        start_time = time.time()
        
        try:
            # First try to get trades from monitor module
            if monitor_active_trades:
                log(f"📊 HF SCANNER: Using monitor's active_trades: {len(monitor_active_trades)} trades")
                active_trades = dict(monitor_active_trades)  # Make a copy
            else:
                # Fall back to loading from file
                active_trades = load_active_trades_directly()
            
            # Filter to only non-exited trades
            active_symbols = [symbol for symbol, trade in active_trades.items() 
                            if not trade.get("exited", False)]
            
            if active_symbols:
                consecutive_empty_checks = 0  # Reset counter
                
                # Process trades in small batches to avoid rate limits
                for i in range(0, len(active_symbols), MAX_CONCURRENT_CHECKS):
                    batch = active_symbols[i:i+MAX_CONCURRENT_CHECKS]
                    tasks = []
                    
                    for symbol in batch:
                        if symbol in active_trades:
                            tasks.append(process_active_trade(symbol, active_trades[symbol], live_candles))
                    
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Small delay between batches to avoid rate limits
                    if i + MAX_CONCURRENT_CHECKS < len(active_symbols):
                        await asyncio.sleep(0.5)
                        
                log(f"⚡ HF SCANNER: Processed {len(active_symbols)} active trades")
                
                # Save any updated trades back to file
                updated_trades = {symbol: active_trades[symbol] for symbol in active_symbols 
                                if symbol in active_trades}
                if updated_trades:
                    save_active_trades_directly(updated_trades)
                    
            else:
                consecutive_empty_checks += 1
                
                if consecutive_empty_checks == 1:
                    log("⚡ HF SCANNER: No active trades to monitor")
                elif consecutive_empty_checks >= max_empty_checks:
                    log(f"⚠️ HF SCANNER: No active trades found for {consecutive_empty_checks} consecutive checks. "
                        f"File exists: {os.path.exists(PERSIST_PATH)}", level="WARN")
                    
                    # Try to debug the file contents
                    if os.path.exists(PERSIST_PATH):
                        try:
                            with open(PERSIST_PATH, 'r') as f:
                                content = f.read()
                                if content.strip():
                                    trades_data = json.loads(content)
                                    total_trades = len(trades_data)
                                    exited_trades = sum(1 for t in trades_data.values() if t.get("exited", False))
                                    log(f"📊 HF SCANNER: File contains {total_trades} total trades, {exited_trades} exited, {total_trades - exited_trades} should be active")
                                else:
                                    log("📊 HF SCANNER: Trade file is empty")
                        except Exception as e:
                            log(f"📊 HF SCANNER: Error reading trade file: {e}")
                    
                    # Reset counter to avoid spam
                    consecutive_empty_checks = 0
        
        except Exception as e:
            log(f"❌ HF SCANNER: Error in high-frequency scanner: {e}", level="ERROR")
            log(traceback.format_exc(), level="ERROR")
        
        # Calculate elapsed time and adjust sleep to maintain consistent interval
        elapsed = time.time() - start_time
        sleep_time = max(0.1, ACTIVE_SCAN_INTERVAL - elapsed)
        
        await asyncio.sleep(sleep_time)
