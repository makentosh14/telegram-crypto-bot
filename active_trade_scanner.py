# active_trade_scanner.py - FIXED VERSION
# Remove duplicate exit logic and use unified exit manager

import asyncio
import json
import os
import time
import traceback
from datetime import datetime
from logger import log, write_log
from bybit_api import signed_request
from error_handler import send_telegram_message

# IMPORT THE UNIFIED EXIT MANAGER - This replaces all duplicate exit logic
from unified_exit_manager import process_trade_exits

# Cache and state management
_active_trades_cache = {}
_cache_timestamp = 0
_cache_ttl = 10  # 10 seconds cache
_last_save_time = 0
_save_cooldown = 5  # 5 seconds between saves

PERSIST_PATH = "active_trades.json"

# Prevent duplicate processing
_processing_symbols = set()

def load_active_trades_directly():
    """Load active trades directly from file"""
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
            
            return active_trades
        else:
            return {}
            
    except Exception as e:
        log(f"❌ HF SCANNER: Error loading active trades: {e}", level="ERROR")
        return {}

async def scan_active_trades():
    """
    MAIN SCANNER FUNCTION - FIXED VERSION
    Uses unified exit manager to prevent double logic
    """
    try:
        # Load current active trades
        active_trades = load_active_trades_directly()
        
        if not active_trades:
            return
        
        log(f"🔍 HF SCANNER: Scanning {len(active_trades)} active trades...")
        
        # Process each trade
        for symbol, trade in list(active_trades.items()):
            try:
                # Skip if already being processed
                if symbol in _processing_symbols:
                    continue
                
                # Skip if trade is exited
                if trade.get("exited"):
                    continue
                
                # Add to processing set
                _processing_symbols.add(symbol)
                
                # Get current price
                current_price = await get_current_price(symbol)
                if not current_price:
                    continue
                
                # Get recent candles for analysis
                candles = await get_recent_candles(symbol)
                
                # USE UNIFIED EXIT MANAGER - Single source of truth
                trade_modified = await process_trade_exits(
                    symbol=symbol,
                    trade=trade,
                    current_price=current_price,
                    candles=candles
                )
                
                if trade_modified:
                    log(f"🔄 HF SCANNER: Trade {symbol} modified by exit manager")
                    # Update our local cache
                    if symbol in _active_trades_cache:
                        _active_trades_cache[symbol] = trade
                
            except Exception as e:
                log(f"❌ HF SCANNER: Error processing {symbol}: {e}", level="ERROR")
                log(traceback.format_exc(), level="ERROR")
            finally:
                # Always remove from processing set
                _processing_symbols.discard(symbol)
        
        # Clear the cache to force reload next time
        _active_trades_cache = {}
        _cache_timestamp = 0
        
    except Exception as e:
        log(f"❌ HF SCANNER: Error in scan_active_trades: {e}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")

async def get_current_price(symbol):
    """Get current price for symbol"""
    try:
        result = await signed_request("GET", "/v5/market/tickers", {
            "category": "linear",
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            tickers = result.get("result", {}).get("list", [])
            if tickers:
                return float(tickers[0]["lastPrice"])
        
        return None
        
    except Exception as e:
        log(f"❌ HF SCANNER: Error getting price for {symbol}: {e}", level="ERROR")
        return None

async def get_recent_candles(symbol, interval="1", limit=20):
    """Get recent candles for analysis"""
    try:
        result = await signed_request("GET", "/v5/market/kline", {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        
        if result.get("retCode") == 0:
            klines = result.get("result", {}).get("list", [])
            
            # Convert to standard format
            candles = []
            for kline in klines:
                candles.append({
                    "open": kline[1],
                    "high": kline[2],
                    "low": kline[3], 
                    "close": kline[4],
                    "volume": kline[5],
                    "timestamp": int(kline[0])
                })
            
            # Reverse to get chronological order (oldest first)
            return list(reversed(candles))
        
        return []
        
    except Exception as e:
        log(f"❌ HF SCANNER: Error getting candles for {symbol}: {e}", level="ERROR")
        return []

async def high_frequency_monitoring(live_candles=None):
    """Main high frequency monitoring loop"""
    while True:
        try:
            await scan_active_trades()
            
            # Wait 5 seconds before next scan
            await asyncio.sleep(5)
            
        except Exception as e:
            log(f"❌ HF SCANNER: Error in monitoring loop: {e}", level="ERROR")
            await asyncio.sleep(10)  # Wait longer on error

# REMOVED FUNCTIONS - These are now handled by unified_exit_manager.py:
# - handle_trailing_sl_exit()
# - check_tp1_hit()
# - check_trailing_sl_hit()
# - handle_tp1_hit()
# - handle_trailing_stop()

if __name__ == "__main__":
    asyncio.run(high_frequency_monitoring())
