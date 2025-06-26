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
        "tp1_pct": 0.9,      # +1.2% take profit
        "sl_pct": 0.6,       # -0.8% stop loss
        "trailing_pct": 0.4  # 0.4% trailing stop
    },
    "Intraday": {
        "tp1_pct": 1.2,      # +2.0% take profit
        "sl_pct": 0.8,       # -1.0% stop loss
        "trailing_pct": 0.8  # 1.0% trailing stop
    },
    "Swing": {
        "tp1_pct": 3.5,      # Keep existing for swing
        "sl_pct": 1.5,       # Keep existing for swing
        "trailing_pct": 1.5  # Keep existing for swing
    }
}

_last_save_time = 0
_save_cooldown = 5  # 5 seconds between saves

async def handle_trailing_sl_exit(symbol, trade, current_price):
    """Handle trailing stop loss exit for HF scanner - Updated for 50/50"""
    try:
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        
        # Calculate total profit percentage
        if direction == "long":
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Mark trade as exited
        trade["exited"] = True
        trade["exit_price"] = current_price
        trade["exit_reason"] = "Trailing_SL_Hit"
        trade["profit_pct"] = profit_pct
        trade["modified"] = True
        
        # Send notification - Updated for 50/50 strategy
        await send_telegram_message(
            f"💔 <b>HF Scanner: Trailing SL</b> on <b>{symbol}</b>\n"
            f"Exit Price: {current_price:.6f}\n"
            f"Total Trade Profit: {profit_pct:.2f}%\n"
            f"Strategy: 50% secured @ TP1\n"
            f"Final 50% exit via trailing SL"
        )
        
        # Log the exit
        log(f"💔 HF SCANNER: Trailing SL hit for {symbol} at {current_price} ({profit_pct:.2f}% total profit)")
        write_log(f"HF_SCANNER_TRAILING_FINAL: {symbol} | Price: {current_price} | Total Profit: {profit_pct:.2f}%")
        
        # Log to activity file with 50/50 strategy context
        log_trade_to_file(
            symbol=symbol,
            direction=direction,
            entry=entry_price,
            sl=trade.get("trailing_sl"),
            tp1=trade.get("tp1_target"),
            tp2=None,
            result="trailing_sl_50_50",  # New result type
            score=trade.get("score_history", [0])[-1] if trade.get("score_history") else 0,
            trade_type=trade.get("trade_type", "Unknown"),
            confidence=0
        )
        
        return True
        
    except Exception as e:
        log(f"❌ HF SCANNER: Error handling trailing SL exit for {symbol}: {e}", level="ERROR")
        return False

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

async def handle_tp1_detection(symbol, trade, current_price):
    """Handle TP1 detection in high-frequency scanner - 50% exit"""
    try:
        log(f"🎯 HF SCANNER: TP1 detected for {symbol} at {current_price}")
        
        # Execute 50% partial exit
        exit_success = await execute_partial_exit_with_retry(symbol, trade, 50)  # 50% instead of 33%
        
        if exit_success:
            trade["tp1_hit"] = True
            trade["tp1_partial_exit"] = True
            trade["tp1_price_actual"] = current_price
            
            # Calculate profit at TP1
            entry_price = trade.get("entry_price")
            direction = trade.get("direction", "").lower()
            
            if direction == "long":
                profit_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                profit_pct = ((entry_price - current_price) / entry_price) * 100
            
            # Send notification
            await send_telegram_message(
                f"🎯 <b>HF Scanner TP1</b> on <b>{symbol}</b>\n"
                f"Price: {current_price:.6f}\n"
                f"50% Position Exited\n"
                f"Profit: {profit_pct:.2f}%\n"
                f"50% remaining for trailing"
            )
            
            # Log the 50% exit
            write_log(f"HF_SCANNER_TP1_50PCT: {symbol} | Price: {current_price} | Profit: {profit_pct:.2f}%")
            
            # Mark for trailing stop management
            trade["trailing_active"] = True
            trade["breakeven_target"] = entry_price
            
            log(f"✅ HF SCANNER: 50% TP1 exit completed for {symbol}")
            return True
            
    except Exception as e:
        log(f"❌ HF SCANNER: Error in TP1 detection for {symbol}: {e}", level="ERROR")
        return False

async def scan_active_trade(symbol, trade):
    """Main scanning function for active trades - Updated for 50/50"""
    try:
        if trade.get("exited"):
            return
            
        direction = trade.get("direction", "").lower()
        entry_price = trade.get("entry_price")
        tp1_target = trade.get("tp1_target")
        trailing_pct = trade.get("trailing_pct", 1.0)
        
        # Get current price
        price_data = await get_current_price(symbol)
        if not price_data:
            return
            
        current_price = price_data.get("mark_price", 0)
        if current_price <= 0:
            return
        
        # Check for TP1 hit (if not already hit)
        if not trade.get("tp1_hit") and tp1_target:
            tp1_hit = False
            
            if direction == "long" and current_price >= tp1_target:
                tp1_hit = True
            elif direction == "short" and current_price <= tp1_target:
                tp1_hit = True
                
            if tp1_hit:
                await handle_tp1_detection(symbol, trade, current_price)
                return  # Exit early after TP1 processing
        
        # Handle trailing stop for remaining 50% (only after TP1 hit)
        if trade.get("tp1_hit") and trade.get("trailing_active"):
            current_trailing_sl = trade.get("trailing_sl")
            
            # Calculate new trailing stop
            if direction == "long":
                new_trailing_sl = current_price * (1 - trailing_pct/100)
            else:
                new_trailing_sl = current_price * (1 + trailing_pct/100)
            
            new_trailing_sl = round(new_trailing_sl, 6)
            
            # Update trailing SL if improved
            should_update = False
            if current_trailing_sl is None:
                should_update = True
            elif direction == "long" and new_trailing_sl > current_trailing_sl:
                should_update = True
            elif direction == "short" and new_trailing_sl < current_trailing_sl:
                should_update = True
            
            if should_update:
                trade["trailing_sl"] = new_trailing_sl
                trade["modified"] = True
                log(f"🔄 HF SCANNER: Trailing SL updated for {symbol}: {new_trailing_sl}")
            
            # Check if trailing SL hit
            sl_hit = False
            if direction == "long" and current_price <= new_trailing_sl:
                sl_hit = True
            elif direction == "short" and current_price >= new_trailing_sl:
                sl_hit = True
                
            if sl_hit:
                await handle_trailing_sl_exit(symbol, trade, current_price)
        
    except Exception as e:
        log(f"❌ HF SCANNER: Error scanning {symbol}: {e}", level="ERROR")

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
