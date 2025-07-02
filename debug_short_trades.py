# debug_short_trades.py - Debug why short trades aren't being saved

import json
import os
from datetime import datetime
from logger import log

def debug_active_trades_file():
    """Debug the active trades file to see what's actually being saved"""
    persist_path = "monitor_active_trades.json"
    
    try:
        if os.path.exists(persist_path):
            with open(persist_path, 'r') as f:
                trades = json.load(f)
            
            print(f"\n📊 Active Trades File Analysis:")
            print(f"Total trades in file: {len(trades)}")
            
            long_trades = []
            short_trades = []
            exited_trades = []
            
            for symbol, trade in trades.items():
                direction = trade.get("direction", "").lower()
                exited = trade.get("exited", False)
                
                if exited:
                    exited_trades.append(symbol)
                elif direction == "long":
                    long_trades.append(symbol)
                elif direction == "short":
                    short_trades.append(symbol)
                else:
                    print(f"⚠️ Unknown direction for {symbol}: '{trade.get('direction')}'")
            
            print(f"\nBreakdown:")
            print(f"🟢 Long trades: {len(long_trades)} - {long_trades}")
            print(f"🔴 Short trades: {len(short_trades)} - {short_trades}")
            print(f"❌ Exited trades: {len(exited_trades)} - {exited_trades}")
            
            # Check for case sensitivity issues
            uppercase_shorts = []
            for symbol, trade in trades.items():
                if trade.get("direction") == "Short":  # Uppercase
                    uppercase_shorts.append(symbol)
            
            if uppercase_shorts:
                print(f"⚠️ Found uppercase 'Short' directions: {uppercase_shorts}")
                print("This might be causing filtering issues!")
            
        else:
            print(f"❌ Active trades file not found: {persist_path}")
            
    except Exception as e:
        print(f"❌ Error reading active trades file: {e}")

def add_debug_logging_to_track_function():
    """Generate enhanced debug version of track_active_trade function"""
    
    enhanced_code = '''
def track_active_trade_debug(symbol, trade_type, initial_score, entry_price=None, direction=None, 
                           trailing_pct=None, tp1_target=None, tp1_pct=None, tp2=None, sl=None, 
                           sl_order_id=None, qty=None, exit_tranches=None, has_pump_potential=False, range_break_details=None):
    """
    Enhanced debug version of track_active_trade to diagnose short trade issues
    """
    global active_trades
    
    # ENHANCED DEBUG LOGGING
    log(f"🔍 TRACK_ACTIVE_TRADE_DEBUG called for {symbol}")
    log(f"   Trade Type: {trade_type}")
    log(f"   Direction: '{direction}' (type: {type(direction)})")
    log(f"   Direction lowercase: '{direction.lower() if direction else None}'")
    log(f"   Entry: {entry_price}, Qty: {qty}")
    log(f"   SL Order ID: {sl_order_id}")
    
    # Check for direction case issues
    if direction:
        if direction == "Short":
            log(f"⚠️ WARNING: Direction is uppercase 'Short' - this might cause issues!")
        elif direction == "short":
            log(f"✅ Direction is lowercase 'short' - correct format")
        elif direction.lower() == "short":
            log(f"⚠️ Direction contains 'short' but with mixed case: '{direction}'")
    
    # Validate and normalize trade type
    valid_trade_types = ["Scalp", "Intraday", "Swing"]
    if trade_type not in valid_trade_types:
        log(f"⚠️ Invalid trade type '{trade_type}' for {symbol}, defaulting to Intraday", level="WARN")
        trade_type = "Intraday"
    
    # Validate required parameters with detailed logging
    missing_params = []
    if not entry_price:
        missing_params.append("entry_price")
    if not direction:
        missing_params.append("direction")
    if not qty:
        missing_params.append("qty")
    
    if missing_params:
        log(f"❌ TRACK_ACTIVE_TRADE_DEBUG: Missing required data for {symbol}", level="ERROR")
        log(f"   Missing parameters: {missing_params}", level="ERROR")
        log(f"   entry_price={entry_price}, direction='{direction}', qty={qty}", level="ERROR")
        
        # Don't return early - let's see what happens if we continue with partial data
        log(f"⚠️ Continuing with partial data for debugging...", level="WARN")
        
    # Normalize direction to lowercase
    if direction:
        original_direction = direction
        direction = direction.lower()
        if original_direction != direction:
            log(f"🔄 Normalized direction from '{original_direction}' to '{direction}'")
    
    # Create the trade entry with debug info
    trade_entry = {
        "score_history": [initial_score],
        "trade_type": trade_type,
        "entry_price": entry_price,
        "direction": direction,  # Should be lowercase now
        "cycles": 0,
        "exited": False,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "qty": qty,
        "sl_order_id": sl_order_id,
        "debug_info": {
            "original_direction": original_direction if 'original_direction' in locals() else direction,
            "created_at": datetime.utcnow().isoformat(),
            "function_called": "track_active_trade_debug"
        }
    }
    
    # Add to active_trades
    active_trades[symbol] = trade_entry
    
    log(f"✅ Trade entry created for {symbol}")
    log(f"📊 Active trades count: {len(active_trades)}")
    log(f"📋 All active symbols: {list(active_trades.keys())}")
    
    # Debug the active_trades dictionary state
    short_trades_in_memory = [s for s, t in active_trades.items() if t.get("direction") == "short"]
    long_trades_in_memory = [s for s, t in active_trades.items() if t.get("direction") == "long"]
    
    log(f"🔍 Active trades in memory:")
    log(f"   Long trades: {len(long_trades_in_memory)} - {long_trades_in_memory}")
    log(f"   Short trades: {len(short_trades_in_memory)} - {short_trades_in_memory}")
    
    # Save to file with debug logging
    log(f"📝 Saving active trades to file...")
    try:
        from monitor import save_active_trades
        save_active_trades()
        log(f"✅ Save completed for {symbol}")
        
        # Immediately verify the save worked
        verify_save_worked(symbol, direction)
        
    except Exception as e:
        log(f"❌ Error saving active trades: {e}", level="ERROR")
        import traceback
        log(traceback.format_exc(), level="ERROR")

def verify_save_worked(symbol, expected_direction):
    """Verify that the trade was actually saved to file"""
    persist_path = "monitor_active_trades.json"
    
    try:
        if os.path.exists(persist_path):
            with open(persist_path, 'r') as f:
                saved_trades = json.load(f)
            
            if symbol in saved_trades:
                saved_direction = saved_trades[symbol].get("direction")
                if saved_direction == expected_direction:
                    log(f"✅ VERIFICATION: {symbol} saved correctly with direction '{saved_direction}'")
                else:
                    log(f"❌ VERIFICATION: {symbol} direction mismatch! Expected '{expected_direction}', got '{saved_direction}'", level="ERROR")
            else:
                log(f"❌ VERIFICATION: {symbol} not found in saved file!", level="ERROR")
        else:
            log(f"❌ VERIFICATION: Active trades file doesn't exist!", level="ERROR")
            
    except Exception as e:
        log(f"❌ VERIFICATION ERROR: {e}", level="ERROR")
'''
    
    return enhanced_code

def check_main_filtering():
    """Generate code to check main.py filtering logic"""
    
    check_code = '''
def check_short_filtering_in_main(symbol, direction, btc_trend, market_sentiment, confidence, trade_type):
    """
    Check if short trades are being filtered out in main.py before reaching track_active_trade
    """
    print(f"\\n🔍 Checking filtering for {symbol}:")
    print(f"  Direction: {direction}")
    print(f"  BTC Trend: {btc_trend}")
    print(f"  Market Sentiment: {market_sentiment}")
    print(f"  Confidence: {confidence}%")
    print(f"  Trade Type: {trade_type}")
    
    # Check 1: Skip shorts in strong uptrends
    if direction == "Short" and btc_trend == "uptrend" and trade_type in ["Scalp", "Intraday"]:
        print(f"❌ FILTERED: Short signal in strong uptrend")
        return False
    
    # Check 2: Require higher confidence for shorts in neutral/bullish markets
    if direction == "Short" and market_sentiment != "bearish":
        if confidence < 60:  # Note: code shows 60, but comment mentions 75%
            print(f"❌ FILTERED: Short confidence {confidence}% below 60% threshold in {market_sentiment} market")
            return False
    
    print(f"✅ PASSED: No filtering detected")
    return True

# Example usage:
# check_short_filtering_in_main("BTCUSDT", "Short", "uptrend", "neutral", 55, "Scalp")
'''
    
    return check_code

if __name__ == "__main__":
    print("🔧 Short Trades Debug Analysis")
    print("=" * 50)
    
    # Run the file analysis
    debug_active_trades_file()
    
    print(f"\n📝 Generated enhanced debug functions:")
    print(f"1. track_active_trade_debug() - Enhanced logging version")
    print(f"2. check_short_filtering_in_main() - Check main.py filtering")
    print(f"3. verify_save_worked() - Verify trades are saved correctly")
    
    print(f"\n💡 Next steps:")
    print(f"1. Replace track_active_trade with track_active_trade_debug temporarily")
    print(f"2. Check your logs for direction case sensitivity issues") 
    print(f"3. Verify BTC trend and market sentiment aren't filtering shorts")
    print(f"4. Check if short signals are reaching the tracking function at all")
