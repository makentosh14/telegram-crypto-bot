# active_trade_scanner.py

import asyncio
import time
import traceback
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request, place_market_order
from error_handler import send_telegram_message, send_error_to_telegram
from monitor import active_trades, save_active_trades, update_stop_loss_order, execute_partial_exit_with_retry
from activity_logger import log_trade_to_file
from ai_memory import log_trade_result
from strategy_performance import log_strategy_result
from exit_manager import detect_momentum_surge

# Configuration for active trade scanner
ACTIVE_SCAN_INTERVAL = 3  # Check active trades every 3 seconds
MAX_CONCURRENT_CHECKS = 5  # Limit concurrent API calls

async def fetch_current_price(symbol):
    """Fetch current price for a symbol with optimized API call"""
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
        if ticker_resp.get("retCode") == 0:
            mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
            last_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("lastPrice", 0))
            return {
                "mark_price": mark_price,
                "last_price": last_price,
                "timestamp": time.time()
            }
    except Exception as e:
        log(f"❌ Error fetching price for {symbol}: {e}", level="ERROR")
    return None

async def process_active_trade(symbol, trade, live_candles):
    """Process a single active trade with high-frequency monitoring"""
    if trade.get("exited"):
        return

    # Get required trade data
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    
    # Calculate TP1 level if not already stored
    tp1_level = trade.get("tp1_target")
    if not tp1_level:
        tp1_level = entry_price * 1.018 if direction == "long" else entry_price * 0.982
        trade["tp1_target"] = tp1_level
        log(f"📊 HF SCANNER: Setting explicit TP1 target for {symbol}: {tp1_level}")
        save_active_trades()

    # Get current price data
    price_data = await fetch_current_price(symbol)
    if not price_data:
        return

    current_price = price_data["mark_price"]  # Use mark price for more reliable triggering
    
    # Get candles if available
    candles = []
    if symbol in live_candles and '1' in live_candles[symbol]:
        candles = list(live_candles[symbol]['1'])
    
    # Check for momentum (important for decision making)
    has_momentum = False
    if candles:
        has_momentum = detect_momentum_surge(candles)

    # PRIORITY 1: Check for TP1 hit if not already hit
    if not trade.get("tp1_hit"):
        # Custom TP1 hit detection
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
            log(f"🎯 HF SCANNER: TP1 hit detected for {symbol} at {current_price}")
            
            # Mark TP1 as hit in trade object
            trade["tp1_hit"] = True
            trade["tp1_hit_cycle"] = trade.get("cycles", 0)
            trade["tp1_price"] = tp1_level  # Use explicit target
            trade["break_even_triggered"] = True
            trade["tp1_hit_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Send detailed notification
            profit_pct = ((tp1_level - entry_price) / entry_price * 100) if direction == "long" else \
                        ((entry_price - tp1_level) / entry_price * 100)
            await send_telegram_message(
                f"🎯 <b>HF Scanner: TP1 Hit</b> on <b>{symbol}</b>\n"
                f"Target: {tp1_level:.6f}\n"
                f"Current: {current_price:.6f}\n"
                f"Entry: {entry_price:.6f}\n"
                f"Profit: {profit_pct:.2f}%\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # Execute partial exit if not already done
            if not trade.get("tp1_partial_exit"):
                exit_success = await execute_partial_exit_with_retry(symbol, trade, 33)
                if exit_success:
                    trade["tp1_partial_exit"] = True
                    write_log(f"HF SCANNER: TP1 PARTIAL EXIT: {symbol} | Price: {current_price} | Success")
                else:
                    log(f"⚠️ HF SCANNER: Partial exit failed for {symbol}", level="WARN")
            
            # Move SL to breakeven if not already done
            if not trade.get("tp1_sl_moved"):
                sl_updated = await update_stop_loss_order(symbol, trade, entry_price)
                if sl_updated:
                    trade["tp1_sl_moved"] = True
                    write_log(f"HF SCANNER: TP1 SL UPDATE: {symbol} | New SL: {entry_price} (breakeven)")
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
                result="tp1",
                score=score,
                trade_type=trade_type,
                confidence=0
            )
            
            save_active_trades()
    
    # PRIORITY 2: Check trailing stop (after TP1 hit)
    elif trade.get("tp1_hit") and trade.get("trailing_pct"):
        try:
            trailing_pct = trade.get("trailing_pct")
            current_trailing_sl = trade.get("trailing_sl")
            
            # Skip trailing during strong momentum to avoid early exit
            if has_momentum and trade.get("has_pump_potential"):
                log(f"🚀 HF SCANNER: Momentum detected for {symbol} - holding trailing SL")
            else:
                # Calculate simple trailing distance based on percentage
                if direction == "long":
                    new_sl = current_price * (1 - trailing_pct/100)
                else:
                    new_sl = current_price * (1 + trailing_pct/100)
                
                # Round to 6 decimal places
                new_sl = round(new_sl, 6)
                
                # Only update if new SL is better than current
                if current_trailing_sl is None or \
                   (direction == "long" and new_sl > current_trailing_sl) or \
                   (direction == "short" and new_sl < current_trailing_sl):
                    
                    log(f"🔒 HF SCANNER: Trailing SL update for {symbol}: {current_trailing_sl} → {new_sl}")
                    await update_stop_loss_order(symbol, trade, new_sl)
                    save_active_trades()
                    
        except Exception as e:
            log(f"❌ HF SCANNER: Error updating trailing SL for {symbol}: {e}", level="ERROR")
    
    # PRIORITY 3: Check if trailing SL hit
    if trade.get("tp1_hit") and trade.get("trailing_sl"):
        trailing_sl = trade.get("trailing_sl")
        
        # Check for SL hit
        sl_hit = False
        if direction == "long" and current_price <= trailing_sl:
            sl_hit = True
        elif direction == "short" and current_price >= trailing_sl:
            sl_hit = True
            
        if sl_hit:
            try:
                # Log SL hit
                log(f"⛔ HF SCANNER: Trailing SL hit for {symbol} at {current_price}")
                
                # Exit remaining position
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
                        log(f"✅ HF SCANNER: Final position exit executed for {symbol}")
                    else:
                        log(f"❌ HF SCANNER: Final exit failed: {exit_result.get('retMsg')}", level="ERROR")
                
                # Mark trade as exited
                trade["exited"] = True
                trade["exit_price"] = current_price
                trade["exit_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trade["exit_reason"] = "trailing_sl"
                
                # Send notification
                await send_telegram_message(
                    f"⛔ <b>HF Scanner: Trailing SL Hit</b> on {symbol} at {current_price:.6f}\n"
                    f"SL Level: {trailing_sl:.6f}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                # Log trade result
                trade_type = trade.get("trade_type", "Intraday")
                score = trade.get("score_history", [0])[-1] if trade.get("score_history") else 0
                profit_pct = ((current_price - entry_price) / entry_price * 100) if direction == "long" else \
                            ((entry_price - current_price) / entry_price * 100)
                           
                result = "win" if profit_pct > 0 else "loss"
                
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
                
                # Log AI memory and strategy performance
                tf_scores = {}  # No TF scores in HF scanner
                log_trade_result(symbol, tf_scores, result)
                
                # Get strategy type for logging
                strategy = "core_strategy"
                if trade.get("tf_scores", {}).get("mean_reversion"):
                    strategy = "mean_reversion"
                elif trade.get("tf_scores", {}).get("breakout_sniper"):
                    strategy = "breakout_sniper"
                
                log_strategy_result(strategy, result, round(profit_pct, 2))
                
                # Save updated trade status
                save_active_trades()
                
            except Exception as e:
                log(f"❌ HF SCANNER: Error processing SL hit for {symbol}: {e}", level="ERROR")
                log(traceback.format_exc(), level="ERROR")

async def high_frequency_scanner(live_candles):
    """Main high-frequency scanner loop for active trades only"""
    log("🚀 Starting high-frequency active trade scanner")
    
    while True:
        start_time = time.time()
        
        try:
            # Only scan active trades (not exited)
            active_symbols = []
            for symbol, trade in active_trades.items():
                exited = trade.get("exited")
                # More explicit checking - trade is active if exited is False/None AND has required data
                if ((exited is False or exited is None or not exited) and 
                    trade.get("direction") and trade.get("entry_price") and trade.get("qty")):
                    active_symbols.append(symbol)
                    log(f"🔍 HF SCANNER: {symbol} marked as active (exited={repr(exited)})")
                else:
                    log(f"🔍 HF SCANNER: {symbol} skipped - exited={repr(exited)}, has_data={bool(trade.get('direction') and trade.get('entry_price') and trade.get('qty'))}")
            
            if active_symbols:
                # Process trades in small batches to avoid rate limits
                for i in range(0, len(active_symbols), MAX_CONCURRENT_CHECKS):
                    batch = active_symbols[i:i+MAX_CONCURRENT_CHECKS]
                    tasks = [process_active_trade(symbol, active_trades[symbol], live_candles) for symbol in batch]
                    await asyncio.gather(*tasks)
                    
                    # Small delay between batches to avoid rate limits
                    if i + MAX_CONCURRENT_CHECKS < len(active_symbols):
                        await asyncio.sleep(0.5)
                        
                log(f"⚡ HF SCANNER: Checked {len(active_symbols)} active trades")
            else:
                log("⚡ HF SCANNER: No active trades to monitor", level="DEBUG")
        
        except Exception as e:
            log(f"❌ Error in high-frequency scanner: {e}", level="ERROR")
            log(traceback.format_exc(), level="ERROR")
        
        # Calculate elapsed time and adjust sleep to maintain consistent interval
        elapsed = time.time() - start_time
        sleep_time = max(0.1, ACTIVE_SCAN_INTERVAL - elapsed)
        
        await asyncio.sleep(sleep_time)
