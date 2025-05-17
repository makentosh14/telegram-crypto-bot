# score_debug.py
# Debug module to help diagnose scoring issues

import json
from logger import log, write_log
from datetime import datetime

# Dictionary to store historical score data for analysis
score_history = {}

def log_score_debug(symbol, score, tf_scores, trade_type, processed=False):
    """
    Log detailed score information for debugging
    
    Args:
        symbol: Trading pair
        score: Final calculated score
        tf_scores: Timeframe score dictionary
        trade_type: Type of trade (Scalp/Intraday/Swing)
        processed: Whether this setup passed all checks
    """
    if symbol not in score_history:
        score_history[symbol] = []
        
    # Limit history to 10 entries per symbol
    if len(score_history[symbol]) >= 10:
        score_history[symbol].pop(0)
        
    # Add current score data
    score_history[symbol].append({
        "score": score,
        "tf_scores": tf_scores,
        "trade_type": trade_type,
        "processed": processed,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # Log detailed score info
    log(f"📊 Score Debug for {symbol}: Score={score:.2f}, Type={trade_type}, Processed={processed}")
    write_log(f"SCORE_DEBUG: {symbol} | Score: {score:.2f} | Type: {trade_type} | TF: {json.dumps(tf_scores)} | Processed: {processed}")
    
def get_score_history(symbol=None, limit=10):
    """
    Get historical score data for analysis
    
    Args:
        symbol: Optional symbol to filter by
        limit: Maximum number of entries to return
        
    Returns:
        Dictionary of score history
    """
    if symbol:
        return {symbol: score_history.get(symbol, [])[-limit:]}
    
    # Return most recent entries for all symbols
    result = {}
    for sym, history in score_history.items():
        result[sym] = history[-limit:]
        
    return result

def analyze_score_patterns():
    """
    Analyze score history for patterns that might indicate issues
    
    Returns:
        List of possible issues identified
    """
    issues = []
    
    # Check for symbols with low scores that are being processed
    low_score_processed = []
    for symbol, history in score_history.items():
        for entry in history:
            if entry["score"] < 5.0 and entry["processed"]:
                low_score_processed.append({
                    "symbol": symbol,
                    "score": entry["score"],
                    "trade_type": entry["trade_type"],
                    "timestamp": entry["timestamp"]
                })
    
    if low_score_processed:
        issues.append({
            "type": "low_score_processed",
            "description": f"Found {len(low_score_processed)} instances of low scores being processed",
            "examples": low_score_processed[:5]  # Show first 5 examples
        })
    
    # Check for other patterns...
    # [Add more pattern detection as needed]
    
    return issues

def log_threshold_check(symbol, score, threshold, trade_type, passed):
    """
    Log information about threshold checks
    
    Args:
        symbol: Trading pair
        score: Score value
        threshold: Threshold being checked against
        trade_type: Type of trade
        passed: Whether the check passed
    """
    result = "PASSED" if passed else "FAILED"
    log(f"🔍 Threshold check for {symbol}: Score {score:.2f} vs Threshold {threshold:.2f} for {trade_type} - {result}")
    write_log(f"THRESHOLD_CHECK: {symbol} | Score: {score:.2f} | Threshold: {threshold:.2f} | Type: {trade_type} | Result: {result}")
