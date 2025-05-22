# atr.py - Corrected ATR calculation
import asyncio
import traceback
from error_handler import send_error_to_telegram

def calculate_atr(candles, period=14):
    """
    Calculate the Average True Range (ATR) from candles
    
    Args:
        candles: List of candle dictionaries with 'high', 'low', 'close' keys
        period: ATR calculation period (default 14)
        
    Returns:
        float: ATR value or None if not enough candles
    """
    try:
        if not candles or len(candles) < period + 1:
            return None

        # Convert to floats and validate data
        highs = []
        lows = []
        closes = []
        
        for candle in candles:
            try:
                high = float(candle['high'])
                low = float(candle['low'])
                close = float(candle['close'])
                
                # Basic validation
                if high < low or close < 0:
                    continue
                    
                highs.append(high)
                lows.append(low)
                closes.append(close)
            except (ValueError, KeyError):
                continue
        
        if len(highs) < period + 1:
            return None

        # Calculate True Range for each candle (starting from index 1)
        true_ranges = []
        
        for i in range(1, len(highs)):
            # True Range = max of:
            # 1. High - Low
            # 2. |High - Previous Close|
            # 3. |Low - Previous Close|
            tr = max(
                highs[i] - lows[i],                    # Current high - low
                abs(highs[i] - closes[i-1]),           # Current high - previous close
                abs(lows[i] - closes[i-1])             # Current low - previous close
            )
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return None
            
        # Calculate ATR as Simple Moving Average of True Ranges
        # Take the last 'period' true ranges
        recent_trs = true_ranges[-period:]
        atr = sum(recent_trs) / len(recent_trs)
        
        return round(atr, 8)  # More precision for crypto
        
    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>ATR Calculation Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return None

def calculate_smoothed_atr(candles, period=14):
    """
    Calculate Smoothed ATR (Wilder's smoothing method)
    More commonly used in professional trading
    
    Args:
        candles: List of candle dictionaries
        period: ATR calculation period
        
    Returns:
        float: Smoothed ATR value or None if not enough candles
    """
    try:
        if not candles or len(candles) < period * 2:  # Need more data for smoothing
            return None

        # Get basic data
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        # Calculate True Ranges
        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return None
            
        # First ATR is simple average of first 'period' TRs
        first_atr = sum(true_ranges[:period]) / period
        
        # Apply Wilder's smoothing for subsequent values
        smoothed_atr = first_atr
        for i in range(period, len(true_ranges)):
            # Wilder's smoothing: ATR = ((previous_ATR * (period-1)) + current_TR) / period
            smoothed_atr = ((smoothed_atr * (period - 1)) + true_ranges[i]) / period
        
        return round(smoothed_atr, 8)
        
    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>Smoothed ATR Calculation Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return None

def calculate_atr_percentage(candles, period=14):
    """
    Calculate ATR as a percentage of current price
    Useful for comparing volatility across different price levels
    
    Args:
        candles: List of candle dictionaries
        period: ATR calculation period
        
    Returns:
        float: ATR percentage or None if calculation fails
    """
    try:
        atr = calculate_atr(candles, period)
        if not atr or not candles:
            return None
            
        current_price = float(candles[-1]['close'])
        if current_price <= 0:
            return None
            
        atr_percentage = (atr / current_price) * 100
        return round(atr_percentage, 4)
        
    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>ATR Percentage Calculation Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return None
