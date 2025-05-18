from logger import log
from error_handler import send_error_to_telegram
import asyncio
import traceback

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
