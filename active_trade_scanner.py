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

# Track which symbols we're processing to avoid duplicates
_processing_symbols = set()

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

_last_save_time = 0
_save_cooldown = 5  # 5 seconds between saves

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
            
            # IMPORTANT: Also update monitor's active_trades if available
            try:
                from monitor import active_trades as monitor_trades
                monitor_trades.clear()
                monitor_trades.update(active_trades)
                log(f"🔄 HF SCANNER: Synced {len(active_trades)} trades with monitor")
            except Exception as e:
                log(f"⚠️ HF SCANNER: Could not sync with monitor: {e}")
            
            log(f"🔍 HF SCANNER: Loaded {len(active_trades)} active trades from file")
            return active_trades
        else:
            log(f"⚠️ HF SCANNER: No trades file found at {PERSIST_PATH}")
            return {}
    except Exception as e:
        log(f"❌ HF SCANNER: Error loading active trades: {e}", level="ERROR")
        return {}

def save_active_trades_directly(trades):
    """Save active trades directly to file with debouncing"""
    global _last_save_time
    
    # Check if we saved recently
    current_time = time.time()
    if current_time - _last_save_time < _save_cooldown:
        log(f"🔄 HF SCANNER: Skipping save (cooldown active)")
        return
    
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
        
        # Update last save time
        _last_save_time = current_time
        
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
    """Process a single active trade - focused on TP1 and trailing only"""
    
    # Skip if already being processed
    if symbol in _processing_symbols:
        return
        
    # Skip exited trades
    if trade.get("exited"):
        return
    
    # Validate trade data
    direction = trade.get("direction", "").lower()
    entry_price = trade.get("entry_price")
    trade_type = trade.get("trade_type", "Intraday")
    trade_type_normalized = trade_type.strip().title()
    trade_type_normalized = trade_type.strip().title()  # Convert to Title Case

    # Map common variations
    trade_type_map = {
        "Scalp": "Scalp",
        "Scalping": "Scalp",
        "Intraday": "Intraday",
        "Intra": "Intraday",
        "Day": "Intraday",
        "Swing": "Swing",
        "Position": "Swing"
    }

    # Get the correct trade type
    trade_type = trade_type_map.get(trade_type_normalized, trade_type_normalized)

    # Validate trade type
    if trade_type not in ["Scalp", "Intraday", "Swing"]:
        log(f"⚠️ HF SCANNER: Invalid trade type '{trade.get('trade_type')}' for {symbol}, defaulting to Intraday")
        trade_type = "Intraday"  # Default to Intraday instead of Scalp
    
    if not direction or not entry_price:
        return
    
    _processing_symbols.add(symbol)
    
    try:
        # Get current price
        price_data = await fetch_current_price(symbol)
        if not price_data:
            return
            
        current_price = price_data.get("mark_price", price_data.get("last_price", 0))
        if current_price <= 0:
            return
        
        # Get candles for momentum detection
        candles = None
        if symbol in live_candles and '1' in live_candles[symbol]:
            candles = list(live_candles[symbol]['1'])
        
        # Get fixed percentages
        fixed_params = FIXED_PERCENTAGES.get(trade_type, FIXED_PERCENTAGES["Intraday"])
        tp1_pct = fixed_params["tp1_pct"]
        trailing_pct = fixed_params["trailing_pct"]
        
        # FOCUS 1: TP1 Detection (if not already hit)
        if not trade.get("tp1_hit"):
            tp1_level = trade.get("tp1_target")
            if not tp1_level:
                tp1_level = entry_price * (1 + tp1_pct/100) if direction == "long" else entry_price * (1 - tp1_pct/100)
                trade["tp1_target"] = tp1_level
            
            # Check for TP1 hit
            tp1_hit = False
            if direction == "long" and current_price >= tp1_level:
                tp1_hit = True
            elif direction == "short" and current_price <= tp1_level:
                tp1_hit = True
            
            # Check candle wicks
            if not tp1_hit and candles and len(candles) >= 2:
                last_candle = candles[-1]
                if direction == "long" and float(last_candle["high"]) >= tp1_level:
                    tp1_hit = True
                elif direction == "short" and float(last_candle["low"]) <= tp1_level:
                    tp1_hit = True
            
            if tp1_hit:
                log(f"🎯 HF SCANNER: TP1 hit detected for {symbol} at {current_price}")
                
                # Mark TP1 as hit
                trade["tp1_hit"] = True
                trade["tp1_price"] = tp1_level
                trade["trailing_pct"] = trailing_pct
                trade["modified"] = True
                
                # Execute partial exit
                if not trade.get("tp1_partial_exit"):
                    exit_success = await execute_partial_exit_with_retry(symbol, trade, 20)
                    if exit_success:
                        trade["tp1_partial_exit"] = True
                
                # Send notification
                await send_telegram_message(
                    f"🎯 <b>HF Scanner: TP1 Hit</b> on <b>{symbol}</b>\n"
                    f"Target: {tp1_level:.6f}\n"
                    f"Current: {current_price:.6f}\n"
                    f"🚀 20% exit, 80% riding!\n"
                    f"📍 Trailing: {trailing_pct}% active"
                )
        
        # FOCUS 2: Trailing Stop Updates (after TP1)
        elif trade.get("tp1_hit") and trade.get("trailing_pct"):
            current_trailing_sl = trade.get("trailing_sl")
            
            # Calculate new trailing SL
            if direction == "long":
                new_sl = current_price * (1 - trailing_pct/100)
            else:
                new_sl = current_price * (1 + trailing_pct/100)
            
            new_sl = round(new_sl, 6)
            
            # Check if update is needed (0.1% improvement)
            should_update = False
            sl_updated = False  # at top of function
            
            if current_trailing_sl is None:
                should_update = True
            elif direction == "long" and new_sl > current_trailing_sl:
                improvement = ((new_sl - current_trailing_sl) / current_trailing_sl) * 100
                if improvement >= 0.1:
                    should_update = True
            elif direction == "short" and new_sl < current_trailing_sl:
                improvement = ((current_trailing_sl - new_sl) / current_trailing_sl) * 100
                if improvement >= 0.1:
                    should_update = True
            
            if should_update:
                trade["trailing_sl"] = new_sl
                trade["needs_sl_update"] = True
                sl_updated = True
                if sl_updated:
                    trade["modified"] = True
                    log(f"🔐 HF SCANNER: Trailing SL updated for {symbol} to {new_sl}")
        
        # FOCUS 3: Check for trailing SL hit
        if trade.get("tp1_hit") and trade.get("trailing_sl"):
            trailing_sl = trade.get("trailing_sl")
            
            # Check with small buffer
            sl_hit = False
            buffer = 0.002  # 0.2%
            
            if direction == "long" and current_price <= trailing_sl * (1 - buffer):
                sl_hit = True
            elif direction == "short" and current_price >= trailing_sl * (1 + buffer):
                sl_hit = True
            
            if sl_hit:
                await handle_trailing_sl_exit(symbol, trade, current_price)
                
    except Exception as e:
        log(f"❌ HF SCANNER: Error processing {symbol}: {e}", level="ERROR")
    finally:
        _processing_symbols.discard(symbol)

async def high_frequency_scanner(live_candles):
    """Main high-frequency scanner loop - simplified and focused"""
    log("🚀 HF SCANNER: Starting high-frequency active trade scanner")
    
    # Give time for main bot to initialize
    await asyncio.sleep(10)
    
    while True:
        start_time = time.time()
        trades_to_save = {}
        
        try:
            # Load active trades
            active_trades = load_active_trades_directly()
            
            # Filter to only non-exited trades
            active_symbols = [
                symbol for symbol, trade in active_trades.items() 
                if not trade.get("exited", False)
            ]
            
            if active_symbols:
                # Process in batches
                for i in range(0, len(active_symbols), MAX_CONCURRENT_CHECKS):
                    batch = active_symbols[i:i+MAX_CONCURRENT_CHECKS]
                    
                    # Process each symbol in batch
                    tasks = []
                    for symbol in batch:
                        if symbol in active_trades:
                            task = process_active_trade(symbol, active_trades[symbol], live_candles)
                            tasks.append(task)
                    
                    # Wait for batch to complete
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Collect modified trades
                    for symbol in batch:
                        if symbol in active_trades and active_trades[symbol].get("modified"):
                            trades_to_save[symbol] = active_trades[symbol]
                            active_trades[symbol].pop("modified", None)
                    
                    # Small delay between batches
                    if i + MAX_CONCURRENT_CHECKS < len(active_symbols):
                        await asyncio.sleep(0.5)
                
                # Save modified trades
                if trades_to_save:
                    save_active_trades_directly(trades_to_save)
                    
        except Exception as e:
            log(f"❌ HF SCANNER: Error in main loop: {e}", level="ERROR")
            log(traceback.format_exc(), level="ERROR")
        
        # Calculate sleep time
        elapsed = time.time() - start_time
        sleep_time = max(0.1, ACTIVE_SCAN_INTERVAL - elapsed)
        
        await asyncio.sleep(sleep_time)
