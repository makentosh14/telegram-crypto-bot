import asyncio
import json
import os
from datetime import datetime
from logger import log, write_log
from error_handler import send_telegram_message
from pattern_detector import detect_pattern

# Pattern matching statistics
pattern_stats = {
    "scans": 0,
    "matches": 0,
    "trades": 0
}

# Pattern match memory (to avoid duplicate triggers)
recent_pattern_matches = {}
MATCH_COOLDOWN = 6  # hours before allowing same pattern to trigger again

PATTERN_DB_PATH = "pattern_match_memory.json"

def load_pattern_memory():
    if os.path.exists(PATTERN_DB_PATH):
        try:
            with open(PATTERN_DB_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed to load pattern memory: {e}", level="ERROR")
    return {}

def save_pattern_memory(data):
    try:
        with open(PATTERN_DB_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(f"❌ Failed to save pattern memory: {e}", level="ERROR")

async def pattern_match_scan(symbols):
    """
    Scan symbols for pattern matches against saved pattern database.
    """
    pattern_stats["scans"] += 1
    
    # Load pattern database and recent matches
    patterns_db = load_pattern_memory()
    
    if not patterns_db:
        return
        
    for symbol in symbols:
        try:
            # Get candles and detect pattern
            from websocket_candles import live_candles
            
            if symbol not in live_candles or not live_candles[symbol].get("5"):
                continue
                
            candles = list(live_candles[symbol]["5"])
            if len(candles) < 30:
                continue
                
            # Detect current pattern
            current_pattern = detect_pattern(candles)
            if not current_pattern:
                continue
                
            # Check if this pattern has meaningful matches in the database
            if current_pattern not in patterns_db:
                continue
            
            # Check for cooldown
            if symbol in recent_pattern_matches and current_pattern in recent_pattern_matches[symbol]:
                last_match_time = datetime.strptime(recent_pattern_matches[symbol][current_pattern], 
                                                   "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                hours_since_match = (now - last_match_time).total_seconds() / 3600
                
                if hours_since_match < MATCH_COOLDOWN:
                    continue
            
            # Get matching pattern data
            pattern_data = patterns_db[current_pattern]
            
            # Analyze current context for match
            current_context = analyze_pattern_context(candles)
            
            # Check for context similarity
            match_score = calculate_context_similarity(current_context, pattern_data["context"])
            
            if match_score > 0.7:  # 70% similarity threshold
                pattern_stats["matches"] += 1
                
                # Record match to prevent repeat triggers
                if symbol not in recent_pattern_matches:
                    recent_pattern_matches[symbol] = {}
                    
                recent_pattern_matches[symbol][current_pattern] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_pattern_memory(recent_pattern_matches)
                
                # Send alert
                await send_pattern_match_alert(symbol, current_pattern, pattern_data, match_score)
                
                # Potentially trigger trade
                if match_score > 0.85:  # Higher threshold for trade execution
                    trade_result = await execute_pattern_trade(symbol, pattern_data, current_pattern)
                    if trade_result:
                        pattern_stats["trades"] += 1
                    
        except ValueError as e:
            # Handle specific value error gracefully
            if "too many values to unpack" in str(e):
                log(f"❌ Pattern match failed for {symbol}: {e}", level="ERROR")
                # Fix: Check function return values in analyze_pattern_context or calculate_context_similarity
                continue
        except Exception as e:
            log(f"❌ Pattern match error for {symbol}: {e}", level="ERROR")
            continue

def analyze_pattern_context(candles):
    """
    Extract context features from candles to compare with stored patterns.
    Returns a dictionary of normalized pattern context metrics.
    """
    # Fix: This function should return only a dictionary of metrics
    
    try:
        if len(candles) < 20:
            return {
                "volume_ratio": 0,
                "price_velocity": 0,
                "range_expansion": 0,
                "pre_pattern_trend": "neutral"
            }
        
        # Recent volume vs previous
        recent_vol = sum(float(c["volume"]) for c in candles[-5:])
        prev_vol = sum(float(c["volume"]) for c in candles[-10:-5])
        volume_ratio = recent_vol / prev_vol if prev_vol > 0 else 1
        
        # Price velocity (normalized rate of change)
        close_prices = [float(c["close"]) for c in candles[-10:]]
        first_price = close_prices[0]
        last_price = close_prices[-1]
        price_velocity = (last_price - first_price) / first_price if first_price > 0 else 0
        
        # Volatility/range expansion
        recent_ranges = [float(c["high"]) - float(c["low"]) for c in candles[-5:]]
        prev_ranges = [float(c["high"]) - float(c["low"]) for c in candles[-10:-5]]
        avg_recent_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0
        avg_prev_range = sum(prev_ranges) / len(prev_ranges) if prev_ranges else 0
        range_expansion = avg_recent_range / avg_prev_range if avg_prev_range > 0 else 1
        
        # Pre-pattern trend direction
        pre_pattern_price_change = (close_prices[-2] - close_prices[0]) / close_prices[0] if close_prices[0] > 0 else 0
        pre_pattern_trend = "bullish" if pre_pattern_price_change > 0.01 else "bearish" if pre_pattern_price_change < -0.01 else "neutral"
        
        return {
            "volume_ratio": round(volume_ratio, 2),
            "price_velocity": round(price_velocity, 4),
            "range_expansion": round(range_expansion, 2),
            "pre_pattern_trend": pre_pattern_trend
        }
        
    except Exception as e:
        log(f"❌ Error analyzing pattern context: {e}", level="ERROR")
        return {
            "volume_ratio": 0,
            "price_velocity": 0,
            "range_expansion": 0,
            "pre_pattern_trend": "neutral"
        }

def calculate_context_similarity(current_context, stored_context):
    """
    Calculate similarity score between current context and stored pattern.
    Returns a score between 0 (no match) and 1 (perfect match).
    """
    try:
        if not current_context or not stored_context:
            return 0
            
        # Initialize with base score
        score = 0
        
        # Volume ratio similarity (max 0.25)
        vol_diff = abs(current_context.get("volume_ratio", 0) - stored_context.get("volume_ratio", 0))
        vol_score = max(0, 0.25 - vol_diff * 0.125)
        
        # Price velocity similarity (max 0.25)
        vel_diff = abs(current_context.get("price_velocity", 0) - stored_context.get("price_velocity", 0))
        vel_score = max(0, 0.25 - vel_diff * 5)  # Price velocity differences are typically small
        
        # Range expansion similarity (max 0.25)
        range_diff = abs(current_context.get("range_expansion", 0) - stored_context.get("range_expansion", 0))
        range_score = max(0, 0.25 - range_diff * 0.125)
        
        # Trend direction match (max 0.25)
        trend_match = current_context.get("pre_pattern_trend") == stored_context.get("pre_pattern_trend")
        trend_score = 0.25 if trend_match else 0
        
        # Combined score
        score = vol_score + vel_score + range_score + trend_score
        
        return round(score, 2)
        
    except Exception as e:
        log(f"❌ Error calculating pattern similarity: {e}", level="ERROR")
        return 0

async def send_pattern_match_alert(symbol, pattern_name, pattern_data, match_score):
    """
    Send Telegram alert for pattern match.
    """
    message = (
        f"🧬 <b>Pattern Match Detected</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Pattern:</b> {pattern_name}\n"
        f"<b>Similarity:</b> {match_score * 100:.1f}%\n"
        f"<b>Historical Direction:</b> {pattern_data.get('direction', 'unknown')}\n"
        f"<b>Average Move:</b> {pattern_data.get('avg_move', 0):.2f}%\n"
        f"<b>Win Rate:</b> {pattern_data.get('win_rate', 0):.1f}%"
    )
    
    await send_telegram_message(message)
    log(f"🧬 Pattern match alert sent for {symbol}: {pattern_name}")

async def execute_pattern_trade(symbol, pattern_data, pattern_name):
    """
    Execute trade based on pattern match if conditions are favorable.
    """
    # Placeholder for actual trade execution logic
    # You should implement this based on your trading strategy
    
    # For now, just log the potential trade
    log(f"🔍 Pattern trade opportunity for {symbol}: {pattern_name}")
    write_log(f"PATTERN TRADE: {symbol} | {pattern_name} | Historical Success: {pattern_data.get('win_rate', 0):.1f}%")
    
    # Return True if trade was executed, False otherwise
    return False
