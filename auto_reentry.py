# auto_reentry.py - Enhanced with Win Ratio Improvements

import asyncio
import time
from datetime import datetime, timedelta
from collections import deque
import numpy as np

from error_handler import send_telegram_message, send_error_to_telegram
from logger import log, write_log
from score import score_symbol, determine_direction, calculate_confidence
from pattern_detector import detect_pattern, analyze_pattern_strength, get_pattern_direction
from volume import is_volume_spike, get_average_volume, analyze_volume_trend
from whale_detector import detect_whale_activity_advanced
from rsi import calculate_rsi_with_bands
from macd import get_macd_momentum, detect_macd_cross
from bollinger import get_bollinger_signal
from supertrend import get_supertrend_state
from exit_manager import detect_momentum_surge

# Enhanced configuration
COOLDOWN_CONFIGS = {
    "Scalp": {
        "base_cooldown": 6,      # 30 seconds (6 * 5s cycles)
        "max_cooldown": 60,      # 5 minutes max
        "min_score": 7.5,
        "win_rate_threshold": 0.6
    },
    "Intraday": {
        "base_cooldown": 12,     # 1 minute
        "max_cooldown": 180,     # 15 minutes max
        "min_score": 8.5,
        "win_rate_threshold": 0.65
    },
    "Swing": {
        "base_cooldown": 24,     # 2 minutes
        "max_cooldown": 360,     # 30 minutes max
        "min_score": 10.0,
        "win_rate_threshold": 0.7
    }
}

# Trade exit tracking with enhanced metadata
exit_history = {}  # symbol -> list of exit records
cooldown_exits = {}  # symbol -> cooldown cycles remaining
reentry_stats = {}  # symbol -> reentry performance stats

# Global performance tracking
global_reentry_stats = {
    "attempts": 0,
    "successes": 0,
    "failures": 0,
    "total_profit": 0,
    "win_rate": 0
}

class ExitRecord:
    """Track detailed exit information for better reentry decisions"""
    def __init__(self, symbol, trade_type, direction, exit_price, exit_reason, 
                 score_at_exit, profit_pct, timestamp=None):
        self.symbol = symbol
        self.trade_type = trade_type
        self.direction = direction
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.score_at_exit = score_at_exit
        self.profit_pct = profit_pct
        self.timestamp = timestamp or datetime.utcnow()
        self.market_conditions = {}  # Store market conditions at exit
        
def initialize_reentry_stats(symbol):
    """Initialize reentry statistics for a symbol"""
    if symbol not in reentry_stats:
        reentry_stats[symbol] = {
            "reentries": 0,
            "successful_reentries": 0,
            "failed_reentries": 0,
            "total_profit": 0,
            "last_reentry": None,
            "win_rate": 0,
            "avg_profit": 0,
            "best_conditions": []
        }

def calculate_dynamic_cooldown(symbol, trade_type, exit_reason, profit_pct):
    """Calculate dynamic cooldown based on exit conditions and performance"""
    config = COOLDOWN_CONFIGS.get(trade_type, COOLDOWN_CONFIGS["Intraday"])
    base_cooldown = config["base_cooldown"]
    
    # Adjust based on exit reason
    if exit_reason == "TP1_Hit" or exit_reason == "Trailing_SL":
        # Successful exits - shorter cooldown
        cooldown_multiplier = 0.5
    elif exit_reason == "SL_Hit":
        # Stop loss hit - longer cooldown
        cooldown_multiplier = 2.0
    elif exit_reason == "Time_Exit":
        # Time-based exit - normal cooldown
        cooldown_multiplier = 1.5
    else:
        cooldown_multiplier = 1.0
    
    # Adjust based on profit
    if profit_pct > 2:
        cooldown_multiplier *= 0.7  # Profitable exit, quicker reentry
    elif profit_pct < -1:
        cooldown_multiplier *= 1.5  # Loss, slower reentry
    
    # Adjust based on symbol's reentry performance
    if symbol in reentry_stats:
        win_rate = reentry_stats[symbol]["win_rate"]
        if win_rate > 0.7:
            cooldown_multiplier *= 0.8
        elif win_rate < 0.4:
            cooldown_multiplier *= 1.3
    
    final_cooldown = int(base_cooldown * cooldown_multiplier)
    return max(config["base_cooldown"], min(final_cooldown, config["max_cooldown"]))

def log_exit(symbol, trade, price=None, reason="Manual", profit_pct=0):
    """Enhanced exit logging with detailed tracking"""
    log(f"📤 EXIT: {symbol} closed due to: {reason} | Price: {price} | Profit: {profit_pct:.2f}%")
    
    # Initialize stats if needed
    initialize_reentry_stats(symbol)
    
    # Create exit record
    exit_record = ExitRecord(
        symbol=symbol,
        trade_type=trade.get("trade_type", "Intraday"),
        direction=trade.get("direction", "Long"),
        exit_price=price,
        exit_reason=reason,
        score_at_exit=trade.get("score_history", [0])[-1] if trade.get("score_history") else 0,
        profit_pct=profit_pct
    )
    
    # Store exit history
    if symbol not in exit_history:
        exit_history[symbol] = deque(maxlen=10)  # Keep last 10 exits
    exit_history[symbol].append(exit_record)
    
    # Calculate dynamic cooldown
    cooldown = calculate_dynamic_cooldown(
        symbol, 
        trade.get("trade_type", "Intraday"),
        reason,
        profit_pct
    )
    
    cooldown_exits[symbol] = cooldown
    
    # Update performance tracking
    write_log(f"EXIT_LOGGED: {symbol} | Reason: {reason} | Cooldown: {cooldown} cycles")

def update_exit_cooldowns():
    """Update cooldowns and clean expired entries"""
    expired = []
    for symbol in cooldown_exits:
        cooldown_exits[symbol] -= 1
        if cooldown_exits[symbol] <= 0:
            expired.append(symbol)
    
    for symbol in expired:
        del cooldown_exits[symbol]
        log(f"⏰ Cooldown expired for {symbol}")

def analyze_exit_patterns(symbol):
    """Analyze historical exit patterns to improve reentry decisions"""
    if symbol not in exit_history or len(exit_history[symbol]) < 3:
        return None
    
    recent_exits = list(exit_history[symbol])[-5:]  # Last 5 exits
    
    analysis = {
        "avg_profit": np.mean([e.profit_pct for e in recent_exits]),
        "profitable_exits": sum(1 for e in recent_exits if e.profit_pct > 0),
        "common_exit_reason": max(set([e.exit_reason for e in recent_exits]), 
                                  key=[e.exit_reason for e in recent_exits].count),
        "avg_score_at_exit": np.mean([e.score_at_exit for e in recent_exits])
    }
    
    return analysis

async def evaluate_reentry_conditions(symbol, candles_by_tf, current_score, 
                                    current_direction, trade_type):
    """Comprehensive reentry evaluation with multiple checks"""
    
    # 1. Check basic score requirement
    config = COOLDOWN_CONFIGS.get(trade_type, COOLDOWN_CONFIGS["Intraday"])
    if current_score < config["min_score"]:
        return False, "Score below minimum"
    
    # 2. Analyze exit patterns
    exit_analysis = analyze_exit_patterns(symbol)
    if exit_analysis:
        # Don't reenter if recent exits were consistently unprofitable
        if exit_analysis["avg_profit"] < -1 and exit_analysis["profitable_exits"] < 2:
            return False, "Poor recent performance"
    
    # 3. Check market conditions
    market_checks = await check_market_conditions_for_reentry(symbol, candles_by_tf, current_direction)
    if not market_checks["suitable"]:
        return False, market_checks["reason"]
    
    # 4. Technical confirmation
    tech_confirmation = check_technical_confirmation(candles_by_tf, current_direction, trade_type)
    if tech_confirmation["score"] < 0.6:
        return False, "Insufficient technical confirmation"
    
    # 5. Risk assessment
    risk_check = assess_reentry_risk(symbol, current_score, trade_type)
    if risk_check["risk_level"] == "high":
        return False, "Risk level too high"
    
    return True, "All conditions met"

async def check_market_conditions_for_reentry(symbol, candles_by_tf, direction):
    """Check if market conditions are suitable for reentry"""
    conditions = {"suitable": True, "reason": "", "score": 0}
    
    try:
        # 1. Volume check
        candles_5m = candles_by_tf.get('5', [])
        if candles_5m:
            avg_volume = get_average_volume(candles_5m)
            current_volume = float(candles_5m[-1]['volume'])
            
            if current_volume < avg_volume * 0.7:
                conditions["suitable"] = False
                conditions["reason"] = "Low volume"
                return conditions
            
            # Volume trend analysis
            vol_trend = analyze_volume_trend(candles_5m)
            if vol_trend.get('trend') == 'decreasing':
                conditions["score"] -= 0.2
        
        # 2. Momentum check
        candles_1m = candles_by_tf.get('1', [])
        if candles_1m:
            has_momentum = detect_momentum_surge(candles_1m)
            if has_momentum:
                conditions["score"] += 0.3
        
        # 3. Whale activity
        whale_activity = detect_whale_activity_advanced(candles_5m, symbol)
        if whale_activity['detected']:
            if (direction == "Long" and whale_activity['recommendation'] == 'potential_short') or \
               (direction == "Short" and whale_activity['recommendation'] == 'potential_long'):
                conditions["suitable"] = False
                conditions["reason"] = "Opposing whale activity"
                return conditions
        
        # 4. Check for adverse patterns
        pattern = detect_pattern(candles_5m)
        if pattern:
            pattern_direction = get_pattern_direction(pattern)
            if (direction == "Long" and pattern_direction == "bearish") or \
               (direction == "Short" and pattern_direction == "bullish"):
                conditions["suitable"] = False
                conditions["reason"] = f"Adverse pattern: {pattern}"
                return conditions
        
        conditions["score"] = min(1.0, max(0, conditions["score"] + 0.5))
        
    except Exception as e:
        log(f"❌ Error checking market conditions: {e}", level="ERROR")
        conditions["suitable"] = False
        conditions["reason"] = "Error in market analysis"
    
    return conditions

def check_technical_confirmation(candles_by_tf, direction, trade_type):
    """Check multiple technical indicators for reentry confirmation"""
    confirmation = {"score": 0, "signals": []}
    
    try:
        # Different timeframes based on trade type
        primary_tf = "5" if trade_type == "Scalp" else "15" if trade_type == "Intraday" else "60"
        candles = candles_by_tf.get(primary_tf, [])
        
        if not candles or len(candles) < 30:
            return confirmation
        
        # 1. RSI confirmation
        rsi_data = calculate_rsi_with_bands(candles)
        if rsi_data:
            rsi = rsi_data['rsi']
            if direction == "Long" and 30 < rsi < 70:
                confirmation["score"] += 0.2
                confirmation["signals"].append("RSI favorable")
            elif direction == "Short" and 30 < rsi < 70:
                confirmation["score"] += 0.2
                confirmation["signals"].append("RSI favorable")
        
        # 2. MACD confirmation
        macd_cross = detect_macd_cross(candles)
        macd_momentum = get_macd_momentum(candles)
        
        if (direction == "Long" and macd_cross == "bullish") or \
           (direction == "Short" and macd_cross == "bearish"):
            confirmation["score"] += 0.25
            confirmation["signals"].append("MACD aligned")
        
        if abs(macd_momentum) > 0.5:
            if (direction == "Long" and macd_momentum > 0) or \
               (direction == "Short" and macd_momentum < 0):
                confirmation["score"] += 0.15
                confirmation["signals"].append("MACD momentum strong")
        
        # 3. Bollinger Bands
        bb_signal = get_bollinger_signal(candles)
        if bb_signal['signal']:
            if (direction == "Long" and bb_signal['signal'] in ['oversold', 'squeeze_breakout_up']) or \
               (direction == "Short" and bb_signal['signal'] in ['overbought', 'squeeze_breakout_down']):
                confirmation["score"] += 0.2
                confirmation["signals"].append(f"BB: {bb_signal['signal']}")
        
        # 4. Supertrend
        st_state = get_supertrend_state(candles)
        if st_state['trend']:
            if (direction == "Long" and st_state['trend'] == 'up') or \
               (direction == "Short" and st_state['trend'] == 'down'):
                confirmation["score"] += 0.2
                confirmation["signals"].append("Supertrend aligned")
        
        # 5. Volume spike
        if is_volume_spike(candles, 2.0):
            confirmation["score"] += 0.15
            confirmation["signals"].append("Volume spike")
        
    except Exception as e:
        log(f"❌ Error in technical confirmation: {e}", level="ERROR")
    
    confirmation["score"] = min(1.0, confirmation["score"])
    return confirmation

def assess_reentry_risk(symbol, current_score, trade_type):
    """Assess risk level for reentry"""
    risk_assessment = {
        "risk_level": "medium",
        "factors": [],
        "score": 0.5
    }
    
    # Check symbol's reentry performance
    if symbol in reentry_stats:
        stats = reentry_stats[symbol]
        win_rate = stats["win_rate"]
        
        if win_rate < 0.3:
            risk_assessment["risk_level"] = "high"
            risk_assessment["factors"].append("Poor historical win rate")
            risk_assessment["score"] = 0.8
        elif win_rate > 0.7:
            risk_assessment["risk_level"] = "low"
            risk_assessment["factors"].append("Strong historical win rate")
            risk_assessment["score"] = 0.2
        
        # Check recent performance
        if stats["last_reentry"]:
            time_since_last = (datetime.utcnow() - stats["last_reentry"]).total_seconds() / 60
            if time_since_last < 30:  # Less than 30 minutes
                risk_assessment["risk_level"] = "high"
                risk_assessment["factors"].append("Too soon since last reentry")
                risk_assessment["score"] = 0.9
    
    # Score-based risk
    config = COOLDOWN_CONFIGS.get(trade_type, COOLDOWN_CONFIGS["Intraday"])
    score_margin = current_score - config["min_score"]
    
    if score_margin < 1:
        risk_assessment["factors"].append("Score barely above minimum")
        risk_assessment["score"] += 0.2
    elif score_margin > 3:
        risk_assessment["factors"].append("Strong score margin")
        risk_assessment["score"] -= 0.2
    
    # Determine final risk level
    if risk_assessment["score"] > 0.7:
        risk_assessment["risk_level"] = "high"
    elif risk_assessment["score"] < 0.3:
        risk_assessment["risk_level"] = "low"
    
    return risk_assessment

def update_reentry_performance(symbol, success, profit_pct):
    """Update reentry performance statistics"""
    if symbol not in reentry_stats:
        initialize_reentry_stats(symbol)
    
    stats = reentry_stats[symbol]
    stats["reentries"] += 1
    
    if success:
        stats["successful_reentries"] += 1
    else:
        stats["failed_reentries"] += 1
    
    stats["total_profit"] += profit_pct
    stats["win_rate"] = stats["successful_reentries"] / stats["reentries"] if stats["reentries"] > 0 else 0
    stats["avg_profit"] = stats["total_profit"] / stats["reentries"] if stats["reentries"] > 0 else 0
    stats["last_reentry"] = datetime.utcnow()
    
    # Update global stats
    global_reentry_stats["attempts"] += 1
    if success:
        global_reentry_stats["successes"] += 1
    else:
        global_reentry_stats["failures"] += 1
    
    global_reentry_stats["total_profit"] += profit_pct
    global_reentry_stats["win_rate"] = (
        global_reentry_stats["successes"] / global_reentry_stats["attempts"] 
        if global_reentry_stats["attempts"] > 0 else 0
    )
    
    # Log performance update
    log(f"📊 Reentry performance updated for {symbol}: Win rate: {stats['win_rate']:.2%}, Avg profit: {stats['avg_profit']:.2f}%")

async def should_reenter(symbol, candles_by_tf, current_score, current_direction, trade_type):
    """Main function to determine if reentry should occur"""
    
    # Check if symbol is in cooldown
    if symbol in cooldown_exits:
        remaining = cooldown_exits[symbol]
        log(f"⏳ {symbol} still in cooldown: {remaining} cycles remaining")
        return False
    
    # Check if we have exit history
    if symbol not in exit_history:
        return False
    
    # Get last exit details
    last_exit = exit_history[symbol][-1]
    
    # Don't reenter if direction changed
    if last_exit.direction != current_direction:
        log(f"🔄 Direction changed for {symbol}: {last_exit.direction} -> {current_direction}")
        return False
    
    # Evaluate all reentry conditions
    should_enter, reason = await evaluate_reentry_conditions(
        symbol, candles_by_tf, current_score, current_direction, trade_type
    )
    
    if should_enter:
        log(f"✅ Reentry conditions met for {symbol}: {reason}")
        return True
    else:
        log(f"❌ Reentry denied for {symbol}: {reason}")
        return False

async def handle_reentry(symbol, current_score, trade_type, direction, 
                        entry_price, candles_by_tf):
    """Execute reentry with enhanced logging and tracking"""
    
    # Get technical confirmation for the message
    tech_confirm = check_technical_confirmation(candles_by_tf, direction, trade_type)
    
    # Get exit history analysis
    exit_analysis = analyze_exit_patterns(symbol)
    
    # Performance stats
    stats = reentry_stats.get(symbol, {})
    win_rate = stats.get("win_rate", 0) * 100
    
    # Build detailed message
    msg = (
        f"🔄 <b>Re-Entry Signal</b> on <b>{symbol}</b>\n"
        f"<b>Score:</b> {current_score:.1f} | <b>Type:</b> {trade_type} | <b>Dir:</b> {direction}\n"
        f"<b>Entry:</b> {entry_price:.6f}\n\n"
        f"<b>Technical Confirmation:</b>\n"
    )
    
    if tech_confirm["signals"]:
        for signal in tech_confirm["signals"][:3]:  # Show top 3 signals
            msg += f"✅ {signal}\n"
    
    msg += f"\n<b>Historical Performance:</b>\n"
    msg += f"📊 Win Rate: {win_rate:.1f}%\n"
    
    if exit_analysis:
        msg += f"📈 Avg Profit (last 5): {exit_analysis['avg_profit']:.2f}%\n"
    
    await send_telegram_message(msg)
    
    # Log for analysis
    write_log(f"RE-ENTRY SIGNAL: {symbol} | Score: {current_score} | Type: {trade_type} | Win Rate: {win_rate:.1f}%")
    log(f"🔄 Reentry triggered for {symbol} | Score = {current_score} | Tech Score: {tech_confirm['score']:.2f}")
    
    # Mark reentry in stats
    if symbol not in reentry_stats:
        initialize_reentry_stats(symbol)
    reentry_stats[symbol]["last_reentry"] = datetime.utcnow()

async def periodic_performance_report():
    """Send periodic performance reports for reentry system"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        if global_reentry_stats["attempts"] > 0:
            msg = (
                f"📊 <b>Reentry System Performance</b>\n\n"
                f"<b>Total Attempts:</b> {global_reentry_stats['attempts']}\n"
                f"<b>Successes:</b> {global_reentry_stats['successes']}\n"
                f"<b>Win Rate:</b> {global_reentry_stats['win_rate']:.1%}\n"
                f"<b>Total Profit:</b> {global_reentry_stats['total_profit']:.2f}%\n\n"
                f"<b>Top Performers:</b>\n"
            )
            
            # Find top performing symbols
            sorted_symbols = sorted(
                reentry_stats.items(), 
                key=lambda x: x[1]['win_rate'], 
                reverse=True
            )[:5]
            
            for symbol, stats in sorted_symbols:
                if stats["reentries"] > 0:
                    msg += f"{symbol}: {stats['win_rate']:.1%} ({stats['reentries']} trades)\n"
            
            await send_telegram_message(msg)

# Cleanup function for old exit records
async def cleanup_old_records():
    """Periodically clean up old exit records"""
    while True:
        await asyncio.sleep(1800)  # Every 30 minutes
        
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        for symbol in list(exit_history.keys()):
            # Remove exits older than 24 hours
            exit_history[symbol] = deque(
                [e for e in exit_history[symbol] if e.timestamp > cutoff_time],
                maxlen=10
            )
            
            if len(exit_history[symbol]) == 0:
                del exit_history[symbol]
        
        log(f"🧹 Cleaned up old exit records")

# Export functions for main.py integration
__all__ = [
    'log_exit',
    'update_exit_cooldowns',
    'should_reenter',
    'handle_reentry',
    'update_reentry_performance',
    'periodic_performance_report',
    'cleanup_old_records'
]
