import asyncio
import traceback
import time
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_direction, calculate_confidence, has_pump_potential, detect_momentum_strength
from telegram_bot import send_telegram_message, format_trade_signal, send_error_to_telegram
from trend_filters import get_trend_context_cached, monitor_btc_trend_accuracy, monitor_altseason_status, validate_short_signal
from signal_memory import log_signal, is_duplicate_signal
from config import DEFAULT_LEVERAGE, ALWAYS_ALLOW_SWING, ALTSEASON_MODE, NORMAL_MAX_POSITIONS
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report
from trade_executor import calculate_dynamic_sl_tp, execute_trade_if_valid
from pump_detector import detect_early_pump
from symbol_info import fetch_symbol_info
from activity_logger import write_log, log_trade_to_file
from monitor import track_active_trade, monitor_trades, load_active_trades, check_and_restore_sl, active_trades, recover_active_trades_from_exchange, periodic_trade_sync
log(f"🔍 main.py - imported active_trades id: {id(active_trades)}")
from pattern_detector import (
    detect_pattern, analyze_pattern_strength, detect_pattern_cluster,
    get_pattern_direction, pattern_success_probability, cleanup_pattern_cache
)
from volume import is_volume_spike
from whale_detector import detect_whale_activity
from ai_memory import load_memory
from mean_reversion import score_mean_reversion
from breakout_sniper import (
    score_breakout_sniper, 
    get_breakout_stats, 
    update_breakout_performance,
    clear_cache as clear_breakout_cache
)
from strategy_performance import get_strategy_stats
from risk_manager import load_risk_state, update_risk_metrics
from sl_tp_utils import calculate_dynamic_sl_tp, calculate_exit_tranches, validate_sl_placement
from pattern_discovery import pattern_discovery_scan
from pattern_matcher import pattern_match_scan
from exit_manager import detect_momentum_surge
from trade_verification import verify_all_positions
from active_trade_scanner import high_frequency_scanner
from risk_manager import load_risk_state, update_risk_metrics
from symbol_utils import get_symbol_category
from ai_memory import periodic_cleanup
from volume import is_volume_spike, get_average_volume
from indicator_fixes import rebalance_indicator_scores, analyze_volume_direction
from auto_reentry import (
    should_reenter,
    handle_reentry,
    periodic_performance_report,
    cleanup_old_records,
    update_reentry_performance
)
from stealth_detector import cleanup_stealth_cache
from range_break_detector import range_break_detector, should_override_regime_for_break, scan_for_breaks_and_pumps
from symbol_utils import get_symbol_category
from typing import List, Dict, Tuple

load_memory()

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10
recent_swing_trades = {}  # Track recent swing trades by symbol with timestamp
SWING_COOLDOWN = 3600  # 1 hour cooldown in seconds

# Slightly reduced thresholds in volatile regime to capture more potential pumps
MIN_SCALP_SCORE = 9
MIN_INTRADAY_SCORE = 10
MIN_SWING_SCORE = 11

def has_strong_swing_conditions(candles_by_tf, tf_scores, direction, trend_context, indicator_scores, used_indicators):
    """
    Enhanced validation for swing trades to reduce false signals
    
    Args:
        candles_by_tf: Dictionary of candles by timeframe
        tf_scores: Dictionary of timeframe scores
        direction: Trade direction ("Long" or "Short")
        trend_context: Dictionary with market trend information
        indicator_scores: Dictionary of indicator scores
        used_indicators: List of indicators used in scoring
        
    Returns:
        bool: True if conditions are met, False otherwise
    """
    # 1. Check for trend alignment with BTC
    btc_trend = trend_context.get("btc_trend", "ranging")
    trend_aligned = (btc_trend == "uptrend" and direction == "Long") or \
                    (btc_trend == "downtrend" and direction == "Short")
    
    # 2. Verify agreement across multiple timeframes
    # Count how many higher timeframes (30m, 60m, 240m) are aligned with direction
    higher_tf_keys = ["30", "60", "240"]
    aligned_timeframes = 0
    for tf in higher_tf_keys:
        if tf in tf_scores:
            if (direction == "Long" and tf_scores[tf] > 0) or \
               (direction == "Short" and tf_scores[tf] < 0):
                aligned_timeframes += 1
    
    # 3. Check for strong technical indicators
    has_strong_pattern = False
    has_supertrend = False
    has_ema = False
    pattern_details = None
    
    # Enhanced pattern check with strength analysis
    for key, score in indicator_scores.items():
        if "pattern" in key and abs(score) >= 0.5:
            if (direction == "Long" and score > 0) or (direction == "Short" and score < 0):
                has_strong_pattern = True
                # Extract pattern name from key (e.g., "60m_pattern_hammer" -> "hammer")
                pattern_name = key.split('_')[-1] if '_' in key else None
                if pattern_name:
                    # Get pattern strength for higher timeframes
                    for tf in higher_tf_keys:
                        if tf in candles_by_tf:
                            detected_pattern = detect_pattern(candles_by_tf[tf])
                            if detected_pattern == pattern_name:
                                pattern_strength = analyze_pattern_strength(detected_pattern, candles_by_tf[tf])
                                if pattern_strength > 0.7:  # Strong pattern
                                    pattern_details = f"{detected_pattern} (strength: {pattern_strength:.2f})"
                                    break
                                    
        if "supertrend" in key and abs(score) >= 0.8:
            if (direction == "Long" and score > 0) or (direction == "Short" and score < 0):
                has_supertrend = True
        if "ema" in key and abs(score) >= 0.8:
            if (direction == "Long" and score > 0) or (direction == "Short" and score < 0):
                has_ema = True
    
    # 4. Check for volume support
    has_volume_support = False
    for key, score in indicator_scores.items():
        if "volume" in key and score > 0:
            has_volume_support = True
            break
    
    # 5. Check volatility conditions
    regime = trend_context.get("regime", "trending")
    is_volatile = regime == "volatile"
    
    # For volatile markets, we require stronger confirmation
    if is_volatile:
        # In volatile markets, require more confirmation factors
        valid = (aligned_timeframes >= 2 and  # At least 2 higher timeframes aligned
                has_strong_pattern and       # Must have a strong pattern
                (has_supertrend or has_ema) and  # Must have trend confirmation
                has_volume_support)          # Must have volume support
    else:
        # In trending/ranging markets, can be slightly more lenient
        valid = (aligned_timeframes >= 1 and  # At least 1 higher timeframe aligned
                (has_strong_pattern or has_supertrend or has_ema) and  # Need at least one strong indicator
                (trend_aligned or has_volume_support))  # Either trend aligned or volume support
    
    # Log detailed validation results for debugging
    log(f"🔍 Swing validation for {direction} trade: " +
        f"Aligned TFs: {aligned_timeframes}, " +
        f"Trend aligned: {trend_aligned}, " +
        f"Pattern: {has_strong_pattern} {pattern_details if pattern_details else ''}, " +
        f"Supertrend: {has_supertrend}, " +
        f"EMA: {has_ema}, " +
        f"Volume: {has_volume_support}, " +
        f"Result: {'✅ PASS' if valid else '❌ FAIL'}")
    
    return valid

def meets_quality_standards(symbol, score, confidence, indicator_scores, used_indicators, trade_type, direction, candles_by_tf, trend_context):
    """More flexible quality filter"""

    # Check if altseason mode is active
    altseason = trend_context.get("altseason", False)
    use_altseason_mode = ALTSEASON_MODE["enabled"] and altseason
    
    # Lower confidence requirements
    min_confidence = {
        "Scalp": 55,      # Reduced from 65
        "Intraday": 60,   # Reduced from 70
        "Swing": 65       # Reduced from 75
    }

    # Apply altseason confidence reduction
    if use_altseason_mode:
        conf_reduction = ALTSEASON_MODE["confidence_reduction"]
        for key in min_confidence:
            min_confidence[key] -= conf_reduction
    
    # For shorts during altseason, still require higher confidence
    if direction == "Short":
        if use_altseason_mode and ALTSEASON_MODE["prefer_longs"]:
            for key in min_confidence:
                min_confidence[key] += 15  # Much higher for shorts in altseason
        else:
            for key in min_confidence:
                min_confidence[key] += 5
    
    # For shorts, slightly higher but not too restrictive
    if direction == "Short":
        for key in min_confidence:
            min_confidence[key] += 5
    
    if trade_type is not None:
        if confidence < min_confidence.get(trade_type, 50):
            log(f"⚠️ {symbol}: Confidence {confidence:.1f}% below minimum {min_confidence[trade_type]}%")
            return False
    
    # Check for conflicting signals - more tolerant
    bullish_count = sum(1 for k, v in indicator_scores.items() if v > 0)
    bearish_count = sum(1 for k, v in indicator_scores.items() if v < 0)
    
    # Allow more conflicts
    if min(bullish_count, bearish_count) > 4:  # Increased from 2
        log(f"⚠️ {symbol}: Too many conflicting signals (Bull: {bullish_count}, Bear: {bearish_count})")
        return False
    
    # Require fewer strong indicators
    strong_indicators = [k for k, v in indicator_scores.items() if abs(v) > 0.7]  # Reduced from 0.8
    if len(strong_indicators) < 1:
        log(f"⚠️ {symbol}: No strong indicators found")
        return False
    
    # Lower indicator count requirements
    min_indicators_required = {
        "Scalp": 3,      # Reduced from 4-5
        "Intraday": 4,   # Reduced from 5-6
        "Swing": 5       # Reduced from 6-7
    }
    
    if len(used_indicators) < min_indicators_required.get(trade_type, 3):
        log(f"⚠️ {symbol}: Insufficient indicators: {len(used_indicators)} < {min_indicators_required[trade_type]}")
        return False
    
    return True

def extract_last_pattern_enhanced(candles_by_tf):
    """Enhanced pattern extraction with strength analysis"""
    best_pattern = None
    best_strength = 0
    best_tf = None
    
    for tf in sorted(candles_by_tf, key=lambda x: int(x)):
        candles = candles_by_tf[tf]
        pattern = detect_pattern(candles)
        
        if pattern:
            strength = analyze_pattern_strength(pattern, candles)
            if strength > best_strength:
                best_pattern = pattern
                best_strength = strength
                best_tf = tf
    
    if best_pattern:
        log(f"🎯 Best pattern: {best_pattern} on {best_tf}m TF (strength: {best_strength:.2f})")
    
    return best_pattern

async def stealth_activity_report():
    """Report on stealth accumulation activity"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        # Get statistics for active symbols
        stealth_report = []
        for symbol in active_signals.keys():
            stats = get_stealth_statistics(symbol)
            if stats['status'] == 'active':
                stealth_report.append(
                    f"{symbol}: {stats['total_detections']} detections, "
                    f"avg strength: {stats['average_strength']}"
                )
        
        if stealth_report:
            msg = "🕵️ <b>Stealth Activity Report</b>\n\n"
            msg += "\n".join(stealth_report[:10])  # Top 10 symbols
            await send_telegram_message(msg)

# Add this function to main.py
async def cleanup_cooldowns():
    """Periodically clean up expired cooldown entries"""
    while True:
        try:
            current_time = time.time()
            expired_symbols = []
            
            for symbol, timestamp in recent_swing_trades.items():
                if current_time - timestamp > SWING_COOLDOWN:
                    expired_symbols.append(symbol)
                    
            for symbol in expired_symbols:
                del recent_swing_trades[symbol]
                
            log(f"🧹 Cleaned up {len(expired_symbols)} expired swing trade cooldowns")
            
        except Exception as e:
            log(f"❌ Error in cooldown cleanup: {e}", level="ERROR")
            
        # Run every 30 minutes
        await asyncio.sleep(1800)

async def breakout_cache_cleanup():
    """Periodically clean up breakout cache"""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        clear_breakout_cache()
        log("🧹 Cleared breakout cache")

async def strategy_stats_report():
    """Periodically report strategy statistics"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        # Get breakout stats
        breakout_stats = get_breakout_stats()
        
        # Get other strategy stats if available
        strategy_performance = get_strategy_stats()
        
        msg = (
            f"📊 <b>Hourly Strategy Report</b>\n\n"
            f"<b>Breakout Sniper:</b>\n"
            f"• Total Trades: {breakout_stats['total_trades']}\n"
            f"• Success Rate: {breakout_stats['success_rate']:.1%}\n"
            f"• Cache Size: {breakout_stats['cache_size']}\n"
        )
        
        if strategy_performance:
            for strategy, stats in strategy_performance.items():
                if strategy != "breakout_sniper":  # Already reported above
                    msg += f"\n<b>{strategy.replace('_', ' ').title()}:</b>\n"
                    msg += f"• Win Rate: {stats.get('win_rate', 0):.1%}\n"
                    msg += f"• Total Trades: {stats.get('total_trades', 0)}\n"
        
        await send_telegram_message(msg)

async def comprehensive_startup_cleanup():
    """Enhanced cleanup on bot startup"""
    log("🧹 Performing comprehensive startup cleanup...")
    
    try:
        # Cancel ALL stop orders across all symbols
        from bybit_api import signed_request
        
        stop_cleanup_count = 0
        
        # Get all stop orders
        stop_orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear",
            "orderFilter": "StopOrder"
        })
        
        if stop_orders_resp.get("retCode") == 0:
            orders = stop_orders_resp.get("result", {}).get("list", [])
            log(f"🧹 Found {len(orders)} stop orders to clean up")
            
            for order in orders:
                try:
                    cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                        "category": "linear",
                        "symbol": order.get("symbol"),
                        "orderId": order.get("orderId")
                    })
                    if cancel_resp.get("retCode") == 0:
                        stop_cleanup_count += 1
                    await asyncio.sleep(0.1)  # Rate limit protection
                except Exception as e:
                    log(f"⚠️ Error cancelling stop order: {e}")
        
        # Also cancel any limit orders that might be orphaned
        limit_orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear",
            "orderFilter": "Order"  # Regular orders
        })
        
        if limit_orders_resp.get("retCode") == 0:
            orders = limit_orders_resp.get("result", {}).get("list", [])
            log(f"🧹 Found {len(orders)} regular orders to clean up")
            
            for order in orders:
                try:
                    cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                        "category": "linear",
                        "symbol": order.get("symbol"),
                        "orderId": order.get("orderId")
                    })
                    await asyncio.sleep(0.1)  # Rate limit protection
                except Exception as e:
                    log(f"⚠️ Error cancelling regular order: {e}")
        
        log(f"✅ Startup cleanup completed: {stop_cleanup_count} stop orders cleaned")
        
    except Exception as e:
        log(f"❌ Error in startup cleanup: {e}", level="ERROR")

def is_short_favorable(candles_by_tf, trend_context):
    """Check if market conditions favor short trades"""
    
    # Check overall market trend
    if trend_context.get("btc_trend") == "uptrend":
        return False
    
    # Check recent price action (using 15m candles)
    candles_15m = candles_by_tf.get('15', [])
    if len(candles_15m) >= 10:
        # Calculate recent trend
        recent_high = max(float(c['high']) for c in candles_15m[-10:])
        recent_low = min(float(c['low']) for c in candles_15m[-10:])
        current = float(candles_15m[-1]['close'])
        
        # If price is near recent lows, shorts are risky
        if (current - recent_low) / (recent_high - recent_low) < 0.3:
            return False
    
    return True

async def range_break_scanner_loop(symbols):
    """Enhanced range break scanner with full feature utilization"""
    while True:
        try:
            trend_context = await get_trend_context_cached()

            # Check if we have valid candle data
            if not live_candles:
                log("⚠️ No live candles available for range break scanning")
                await asyncio.sleep(30)
                continue
            
            # Enhanced trend context with more data
            trend_context['market_season'] = trend_context.get('altseason', 'no')
            trend_context['volatility'] = 'high' if trend_context.get('regime') == 'volatile' else 'normal'
            
            # Scan all symbols for breaks and pumps
            potential_breaks, potential_pumps = await scan_for_breaks_and_pumps(
                symbols, live_candles, trend_context
            )
            
            # Sort by confidence for priority processing
            potential_pumps.sort(key=lambda x: x['confidence'], reverse=True)
            potential_breaks.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Process top pump signals with priority
            for pump_signal in potential_pumps[:5]:  # Top 5 pumps
                symbol = pump_signal['symbol']
                
                # Skip if already in active trade
                if symbol in active_trades:
                    continue
                
                if symbol in active_signals or is_duplicate_signal(symbol):
                    continue
                
                # Process high confidence pumps immediately
                if pump_signal['confidence'] >= 0.7:
                    log(f"🚀 HIGH CONFIDENCE PRE-PUMP: {symbol} - Confidence: {pump_signal['confidence']:.2f}")
                    await process_pump_signal(pump_signal, trend_context)
                    
                # Medium confidence pumps - wait for confirmation
                elif pump_signal['confidence'] >= 0.6:
                    # Store for monitoring
                    if symbol not in range_break_detector.pre_breakout_alerts:
                        log(f"👀 Monitoring potential pump: {symbol} - Confidence: {pump_signal['confidence']:.2f}")
            
            # Process break signals
            for break_signal in potential_breaks[:5]:  # Top 5 breaks
                symbol = break_signal['symbol']
                if symbol in active_signals or is_duplicate_signal(symbol):
                    continue
                
                if break_signal['confidence'] >= 0.65:
                    log(f"🎯 RANGE BREAK DETECTED: {symbol} - Direction: {break_signal['direction']}")
                    await process_break_signal(break_signal, trend_context)
                    
        except Exception as e:
            log(f"❌ Error in enhanced range break scanner: {e}", level="ERROR")
            import traceback
            log(traceback.format_exc(), level="ERROR")
            
        await asyncio.sleep(20)  # Faster scanning for better timing

async def scan_for_breaks_and_pumps(symbols: List[str], live_candles: Dict, 
                                   trend_context: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Scan all symbols for potential range breaks AND pre-pump signals"""
    potential_breaks = []
    potential_pumps = []
    
    for symbol in symbols:
        if symbol not in live_candles:
            continue
            
        try:
            # Get candles for all timeframes
            candles_by_tf = {}
            for tf in ['1', '3', '5', '15', '30']:
                if tf in live_candles[symbol]:
                    candles_by_tf[tf] = list(live_candles[symbol][tf])
                    
            if not candles_by_tf.get('5') or len(candles_by_tf['5']) < 50:
                continue
                
            # Get current regime
            regime = trend_context.get('regime', 'trending')
            
            # Check for range breakout
            breakout_detected, direction, confidence, details = range_break_detector.detect_range_breakout(
                symbol, candles_by_tf.get('5', []), '5', trend_context
            )
            
            if breakout_detected:
                # Ensure range boundaries are in the reasons
                reasons = {
                    'range_high': details.get('range_high'),
                    'range_low': details.get('range_low'),
                    'range_width_pct': details.get('range_width_pct'),
                    'breakout_confidence': confidence
                }
                
                # Add other detection reasons
                if details.get('stealth_score', 0) > 0.3:
                    reasons['stealth_accumulation'] = {'strength': details['stealth_score']}
                if details.get('volume_analysis', {}).get('composite_score', 0) > 0.5:
                    reasons['volume_strength'] = {'strength': details['volume_analysis']['composite_score']}
                
                # Check if it's a pump signal (strong upward break with accumulation)
                if direction == "Long" and (
                    details.get('stealth_score', 0) > 0.5 or 
                    details.get('pre_breakout', False) or
                    confidence > 0.8
                ):
                    potential_pumps.append({
                        'symbol': symbol,
                        'confidence': confidence,
                        'reasons': reasons,
                        'current_price': float(candles_by_tf['5'][-1]['close'])
                    })
                else:
                    potential_breaks.append({
                        'symbol': symbol,
                        'direction': direction,
                        'confidence': confidence,
                        'reasons': reasons,
                        'current_price': float(candles_by_tf['5'][-1]['close'])
                    })
                    
        except Exception as e:
            log(f"❌ Error scanning {symbol}: {e}", level="ERROR")
            
    return potential_breaks, potential_pumps

def should_override_regime_for_break(break_confidence: float, current_regime: str) -> bool:
    """Determine if break signal should override current regime"""
    if break_confidence >= 0.8:
        return True  # High confidence breaks override any regime
    elif break_confidence >= 0.65 and current_regime == "ranging":
        return True  # Medium confidence sufficient in ranging markets
    return False

async def process_pump_signal(pump_signal, trend_context):
    """Enhanced pump signal processing with full range break integration"""
    symbol = pump_signal['symbol']
    
    # Skip if already in active trade or signals
    if symbol in active_trades or symbol in active_signals:
        return
    
    # Get comprehensive candle data
    candles_by_tf = {
        tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
        if str(tf) in live_candles[symbol]
    }
    
    # Run full range breakout analysis for detailed data
    breakout_detected, direction, confidence, details = range_break_detector.detect_range_breakout(
        symbol, candles_by_tf.get('5', []), '5', trend_context
    )

    # Ensure we have the range boundaries in details
    if 'range_high' not in details and 'resistance' in details:
        details['range_high'] = details['resistance']
    if 'range_low' not in details and 'support' in details:
        details['range_low'] = details['support']
    
    # Calculate enhanced score based on all factors
    base_score = 6.5 + (pump_signal['confidence'] * 1.5)
    
    # Add bonuses for specific patterns
    if details.get('pre_breakout'):
        base_score += 0.5
        log(f"   📈 Pre-breakout patterns: {details.get('buildup_patterns', [])}")
    
    if details.get('stealth_score', 0) > 0.5:
        base_score += 0.3
        log(f"   🕵️ Strong stealth accumulation: {details['stealth_score']:.2f}")
    
    if details.get('volume_analysis', {}).get('tightening', {}).get('detected'):
        base_score += 0.3
        log(f"   📉 Volume tightening detected")
    
    # Build comprehensive indicator scores
    indicator_scores = {}
    
    # Add all detected factors
    for reason, data in pump_signal['reasons'].items():
        if isinstance(data, dict) and 'strength' in data:
            indicator_scores[f"pump_{reason}"] = data['strength']
        else:
            indicator_scores[f"pump_{reason}"] = 1.0
    
    # Add range break specific indicators
    if details.get('integrated_factors'):
        for factor, score in details['integrated_factors'].items():
            indicator_scores[f"range_{factor}"] = score
    
    # Calculate optimal entry based on range position
    price = pump_signal['current_price']
    if details.get('range_low') and details.get('range_high'):
        # Adjust entry for better risk/reward
        range_position = (price - details['range_low']) / (details['range_high'] - details['range_low'])
        if range_position < 0.3:  # Near support - ideal entry
            base_score += 0.2
            indicator_scores['optimal_entry'] = 1.0
    
    # Enhanced exit strategy for pumps
    exit_strategy_params = {
        'exit_strategy': 'pump_optimized',
        'trailing_multiplier': 1.5,  # Wider trailing for pumps
        'tp1_multiplier': 1.3,  # Higher TP1 for pumps
        'exit_tranches': [0.25, 0.35, 0.40]  # Optimized for letting pumps run
    }
    
    # Calculate confidence
    confidence = min(pump_signal['confidence'] * 100, 95)
    
    # Calculate SL/TP - FIXED: Ensure we get all values
    result = calculate_dynamic_sl_tp(
        candles_by_tf, price, "Scalp", "Long", base_score, confidence, "volatile", trend_context
    )
    
    # FIXED: Properly unpack all values
    if len(result) >= 5:
        sl, tp1, sl_pct, trailing_pct, tp1_pct = result[:5]
    else:
        # Fallback values
        sl = price * 0.98  # 2% SL
        tp1 = price * 1.015  # 1.5% TP
        sl_pct = 2.0
        tp1_pct = 1.5
        trailing_pct = 0.5
    
    # Execute trade with enhanced parameters
    trade = await execute_trade_if_valid({
        "symbol": symbol,
        "price": price,
        "trade_type": "Scalp",  # Pumps usually start as scalps
        "direction": "Long",
        "score": base_score,
        "confidence": confidence,
        "candles": candles_by_tf,
        "indicator_scores": indicator_scores,
        "used_indicators": list(pump_signal['reasons'].keys()) + ['range_break'],
        "tf_scores": {"pump_detector": base_score},
        "regime": "volatile",
        "pump_potential": True,
        "range_break_details": details,
        "range_break_confidence": pump_signal['confidence'],
        **exit_strategy_params,
        "market_type": get_symbol_category(symbol)
    })
    
    if trade:
        # FIXED: Format and send the Telegram message with all required parameters
        msg = format_trade_signal(
            symbol=symbol,
            score=base_score,
            tf_scores={"range_break_pump": base_score},
            trend=trend_context,
            entry_price=trade['entry'],  # Use actual executed price
            sl=trade['sl'],              # Use actual SL from trade
            tp1=trade['tp1'],            # Use actual TP1 from trade
            trade_type="Scalp",
            direction="Long",
            trailing_pct=trade.get('trailing_pct', trailing_pct),
            leverage=DEFAULT_LEVERAGE,
            risk_pct=6.0,
            confidence=confidence,
            sl_pct=trade.get('sl_pct', sl_pct),      # FIXED: Add sl_pct
            tp1_pct=trade.get('tp1_pct', tp1_pct)    # FIXED: Add tp1_pct
        )
        
        # Add pump-specific information
        msg += f"\n\n🚀 <b>PUMP SIGNAL DETECTED</b>\n"
        msg += f"Confidence: {pump_signal['confidence']*100:.1f}%\n"
        
        if details.get('range_high') and details.get('range_low'):
            msg += f"\n📊 <b>Range Analysis:</b>\n"
            msg += f"• High: {details['range_high']:.8f}\n"
            msg += f"• Low: {details['range_low']:.8f}\n"
            msg += f"• Width: {details['range_width_pct']:.2f}%\n"
        
        if details.get('buildup_patterns'):
            msg += f"\n🎯 <b>Patterns:</b> {', '.join(details['buildup_patterns'])}"
        
        # Send the Telegram message
        await send_telegram_message(msg)
        
        # Track with enhanced data
        active_signals[symbol] = {
            'score': base_score,
            'score_history': [base_score],
            'pump_signal': True,
            'range_data': details
        }
        
        # Track the active trade with all parameters
        track_active_trade(
            symbol=symbol,
            trade_type="Scalp",
            initial_score=base_score,
            entry_price=trade['entry'],
            direction="Long",
            trailing_pct=trade.get("trailing_pct", trailing_pct),
            tp1_target=trade.get("tp1"),
            tp1_pct=trade.get('tp1_pct', tp1_pct),
            tp2=trade.get("tp2"),
            sl=trade.get("sl"),
            qty=trade.get("qty"),
            sl_order_id=trade.get("sl_order_id"),
            exit_tranches=trade.get("exit_tranches"),
            has_pump_potential=True,
            range_break_details=details
        )

async def process_break_signal(break_signal, trend_context):
    """Process a range break signal into a trade"""
    symbol = break_signal['symbol']
    
    # Skip if already in active trade or signals
    if symbol in active_trades or symbol in active_signals:
        return
    
    # Get candles
    candles_by_tf = {
        tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
        if str(tf) in live_candles[symbol]
    }
    
    # Base score for range breaks
    base_score = 7.0 + (break_signal['confidence'] * 2.0)  # Score 7-9
    
    # Build indicator scores
    indicator_scores = {}
    for reason, data in break_signal['reasons'].items():
        if isinstance(data, dict):
            indicator_scores[f"break_{reason}"] = data.get('strength', 1.0)
        else:
            indicator_scores[f"break_{reason}"] = 1.0
    
    # Setup trade parameters
    price = break_signal['current_price']
    trade_type = "Intraday"  # Range breaks are typically intraday trades
    direction = break_signal['direction']
    confidence = min(break_signal['confidence'] * 100, 95)
    
    # Get range details from the break signal
    range_details = break_signal.get('reasons', {})
    
    # Ensure we have the range boundaries in the details
    if 'range_high' not in range_details and 'resistance' in range_details:
        range_details['range_high'] = range_details['resistance']
    if 'range_low' not in range_details and 'support' in range_details:
        range_details['range_low'] = range_details['support']
    
    # Calculate range-based SL/TP levels
    range_levels = calculate_range_based_exit_levels({
        'direction': direction.lower(),
        'entry_price': price,
        'range_break_details': range_details
    })
    
    if not range_levels:
        log(f"❌ Failed to calculate range-based levels for {symbol}")
        return

    # Validate risk/reward ratio
    sl_distance = abs((range_levels['sl'] - price) / price)
    tp1_distance = abs((range_levels['tp1'] - price) / price)
    risk_reward = tp1_distance / sl_distance if sl_distance > 0 else 0
    
    # Skip if risk/reward is poor
    if risk_reward < 1.5:
        log(f"⚠️ Skipping {symbol}: Poor R:R ratio {risk_reward:.2f}")
        return
    
    # Adjust risk based on SL distance
    base_risk = 0.06  # 6% for Intraday
    if sl_distance > 0.02:  # If SL is more than 2%
        # Scale down risk to maintain reasonable position size
        adjusted_risk = base_risk * (0.02 / sl_distance)
        adjusted_risk = max(adjusted_risk, 0.03)  # Minimum 3% risk
        log(f"📊 Adjusting risk from {base_risk*100:.1f}% to {adjusted_risk*100:.1f}% due to SL at {sl_distance*100:.2f}%")
    else:
        adjusted_risk = base_risk
    
    # Execute trade with range-based levels
    trade = await execute_trade_if_valid({
        "symbol": symbol,
        "price": price,
        "trade_type": trade_type,
        "direction": direction,
        "score": base_score,
        "confidence": confidence,
        "candles": candles_by_tf,
        "indicator_scores": indicator_scores,
        "used_indicators": list(break_signal['reasons'].keys()),
        "tf_scores": {"range_break": base_score},
        "regime": "volatile",
        "market_type": get_symbol_category(symbol),
        # Pass the range-based SL/TP
        "override_sl": range_levels['sl'],
        "override_tp1": range_levels['tp1'],
        "override_tp2": range_levels.get('tp2'),
        "override_tp3": range_levels.get('tp3'),
        "range_break_details": range_details,
        "exit_strategy": "range_break",
        "trailing_multiplier": 1.2,  # Wider trailing for range breaks
        "exit_tranches": [0.33, 0.33, 0.34]  # Even distribution
    })
    
    if trade:
        # Calculate actual percentages
        sl_pct = abs((trade['sl'] - trade['entry']) / trade['entry']) * 100
        tp1_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
        actual_risk_pct = calculate_actual_risk_percentage(
            trade['entry'],
            trade['sl'],
            trade['qty'],
            account_balance  # You'll need to get this
        )
        
        # Send notification
        msg = format_trade_signal(
            symbol=symbol,
            score=base_score,
            tf_scores={"range_break": base_score},
            trend=trend_context,
            entry_price=trade['entry'],
            sl=trade['sl'],
            tp1=trade['tp1'],
            trade_type=trade_type,
            direction=direction,
            trailing_pct=trade.get('trailing_pct', 1.0),
            leverage=DEFAULT_LEVERAGE,
            risk_pct=actual_risk_pct,,
            confidence=confidence,
            sl_pct=sl_pct,
            tp1_pct=tp1_pct
        )
        
        # Add range break specific info
        msg += f"\n\n🎯 <b>RANGE BREAK SIGNAL</b>\n"
        msg += f"Direction: {direction}\n"
        msg += f"Confidence: {break_signal['confidence']*100:.1f}%\n"
        msg += f"\n💰 <b>Actual Risk:</b> {actual_risk_pct:.2f}% of balance"
        
        if range_details.get('range_high') and range_details.get('range_low'):
            msg += f"\n📊 <b>Range Analysis:</b>\n"
            msg += f"• Support: {range_details['range_low']:.8f}\n"
            msg += f"• Resistance: {range_details['range_high']:.8f}\n"
            msg += f"• Width: {((range_details['range_high'] - range_details['range_low']) / range_details['range_low'] * 100):.2f}%\n"
        
        msg += f"\n📍 <b>Exit Strategy:</b>\n"
        msg += f"• SL at {'resistance' if direction == 'Long' else 'support'} level\n"
        msg += f"• TP based on range width projection\n"
        msg += f"• Trailing stop after TP1"
        
        await send_telegram_message(msg)
        
        # Track the trade
        active_signals[symbol] = {
            'score': base_score,
            'score_history': [base_score],
            'range_break': True,
            'range_levels': range_levels
        }
        
        track_active_trade(
            symbol=symbol,
            trade_type=trade_type,
            initial_score=base_score,
            entry_price=trade['entry'],
            direction=direction,
            trailing_pct=trade.get("trailing_pct", 1.0),
            tp1_target=trade['tp1'],
            tp1_pct=tp1_pct,
            tp2=trade.get("tp2"),
            sl=trade['sl'],
            qty=trade['qty'],
            sl_order_id=trade.get('sl_order_id'),
            exit_tranches=trade.get("exit_tranches"),
            has_pump_potential=False,
            range_break_details=range_details
        )


async def scan_for_new_signals(symbols,trend_context):
    global active_trades
    
    regime = trend_context.get("regime", "trending")
    altseason = trend_context.get("altseason", False)
    altseason_strength = trend_context.get("altseason_strength", 0)
    
    # Check if we should use altseason mode
    use_altseason_mode = (
        ALTSEASON_MODE["enabled"] and 
        altseason and 
        altseason_strength > 0.6  # Only activate for strong altseason
    )
    
    if use_altseason_mode:
        log("🚀 ALTSEASON MODE ACTIVE - Using enhanced parameters")
    
    # Check max positions limit
    current_positions = sum(1 for t in active_trades.values() if not t.get("exited"))
    max_positions = ALTSEASON_MODE["max_positions"] if use_altseason_mode else NORMAL_MAX_POSITIONS
    
    if current_positions >= max_positions:
        log(f"⚠️ Maximum positions reached ({current_positions}/{max_positions})")
        return

    # Adjust score thresholds based on regime AND altseason mode
    score_adjustments = {
        "volatile": {"scalp": -1.0, "intraday": -0.8, "swing": -0.5},
        "ranging": {"scalp": -0.5, "intraday": -0.3, "swing": 0.0},
        "trending": {"scalp": 0.0, "intraday": 0.0, "swing": -0.5},
    }
    
    # Apply additional reduction during altseason
    if use_altseason_mode:
        reduction = ALTSEASON_MODE["score_threshold_reduction"]
        for regime_type in score_adjustments:
            for trade_type in score_adjustments[regime_type]:
                score_adjustments[regime_type][trade_type] -= reduction
    
    # Additional adjustment for altseason
    if altseason in ["confirmed", "strong_altseason"]:
        # Be more aggressive during altseason
        for trade_type in score_adjustments[regime]:
            score_adjustments[regime][trade_type] -= 0.5
            
    adjust = score_adjustments.get(regime, {"scalp": 0, "intraday": 0, "swing": 0})
    adj_scalp = MIN_SCALP_SCORE + adjust["scalp"]
    adj_intraday = MIN_INTRADAY_SCORE + adjust["intraday"]
    adj_swing = MIN_SWING_SCORE + adjust["swing"]

    trade_type = None
    for i, symbol in enumerate(symbols, 1):
        if symbol not in live_candles:
            continue
        if recent_exits.get(symbol, 0) > 0:
            recent_exits[symbol] -= 1
            continue

        try:
            candles_by_tf = {
                tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
            }
        except Exception:
            continue

        if not all(len(candles_by_tf[tf]) >= 30 for tf in TIMEFRAMES):
            continue

        # ---- Primary strategy scoring ----
        from score import enhanced_score_symbol
        score, tf_scores, trade_type, indicator_scores, used_indicators = enhanced_score_symbol(
            symbol, candles_by_tf, market_context=trend_context
        )
        direction = determine_direction(tf_scores)
        confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
        price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0
        indicator_scores = rebalance_indicator_scores(indicator_scores, trend_context)

        # Check for pump potential - important for exit strategy
        pump_potential = has_pump_potential(candles_by_tf, direction)
        
        # Check for momentum
        momentum_data = detect_momentum_strength(candles_by_tf.get("1", []))
        has_momentum = momentum_data[0] if momentum_data else False

        # NOW check for range break setup AFTER score is defined
        range_break_bonus = 0
        range_break_details = {}
        break_confidence = 0  # Initialize this too
        
        # Check for range break setup
        if candles_by_tf.get('5') and len(candles_by_tf['5']) >= 50:
            breakout, break_direction, break_confidence, details = range_break_detector.detect_range_breakout(
                symbol, candles_by_tf['5'], '5', trend_context
            )
            
            if breakout:
                # Add bonus to score based on confidence
                range_break_bonus = break_confidence * 2.0
                range_break_details = details
                
                # Add to indicator scores
                indicator_scores['range_break'] = break_confidence
                indicator_scores['range_confidence'] = break_confidence
                
                # If direction matches, add extra bonus
                if break_direction == direction:
                    range_break_bonus += 0.5
                    indicator_scores['range_direction_aligned'] = 1.0
                
                # Log range break detection
                log(f"   🎯 Range break detected: {break_direction} with {break_confidence:.2f} confidence")
                
                # Add specific pattern bonuses
                if details.get('pre_breakout'):
                    range_break_bonus += 0.3
                    indicator_scores['pre_breakout'] = 1.0
                    log(f"   📈 Pre-breakout patterns: {details.get('buildup_patterns', [])}")
                
                # Override trade type for range breaks
                if break_confidence > 0.7:
                    trade_type = "Scalp"  # Range breaks often start as scalps

        if use_altseason_mode and has_momentum:
            momentum_bonus = ALTSEASON_MODE["momentum_bias"]
            score += momentum_bonus
            indicator_scores["altseason_momentum"] = momentum_bonus
            log(f"🚀 Altseason momentum bonus: +{momentum_bonus}")

        # Update direction bias during altseason
        if use_altseason_mode and ALTSEASON_MODE["prefer_longs"] and direction == "Short":
            # Reduce confidence for shorts during altseason
            confidence *= 0.7
            log(f"📉 Short confidence reduced during altseason: {confidence:.1f}%")
                    
        # Apply range break bonus
        score += range_break_bonus

        # Enhanced pattern detection
        pattern = extract_last_pattern_enhanced(candles_by_tf)
        pattern_strength = 0
        if pattern:
            # Get pattern strength from the best timeframe
            for tf in candles_by_tf:
                if detect_pattern(candles_by_tf[tf]) == pattern:
                    pattern_strength = analyze_pattern_strength(pattern, candles_by_tf[tf])
                    break

        # Check for pump potential - important for exit strategy
        pump_potential = has_pump_potential(candles_by_tf, direction)
        if pump_potential:
            log(f"🚀 {symbol} shows strong pump potential - adjusting strategy")
            # Boost score to prioritize potential pumps
            score += 0.5
            # Add pump potential indicator
            indicator_scores["pump_potential"] = 1.0
            used_indicators.append("pump_potential")

        # Calculate risk percentage
        market_season = trend_context.get("altseason", "no")

        if trade_type == "Scalp":
            base_risk = 0.07 if market_season == "confirmed" else 0.09 if market_season == "strong_altseason" else 0.05
        elif trade_type == "Intraday":
            base_risk = 0.05 if market_season == "confirmed" else 0.06 if market_season == "strong_altseason" else 0.035
        else:  # Swing
            base_risk = 0.03 if market_season == "confirmed" else 0.04 if market_season == "strong_altseason" else 0.02

        if use_altseason_mode:
            base_risk *= ALTSEASON_MODE["risk_multiplier"]
            log(f"💰 Altseason risk multiplier applied: {base_risk:.2f}%")
           
        # Determine strategy type for risk manager
        strategy = "core_strategy"
        if tf_scores.get("mean_reversion"):
            strategy = "mean_reversion"
        elif tf_scores.get("breakout_sniper"):
            strategy = "breakout_sniper"
        
        # Get dynamic risk percentage based on confidence, strategy, and past performance
        risk_pct = base_risk

        tf_breakdown = ", ".join(f"{k}m: {v:.1f}" for k, v in tf_scores.items())
        log(f"📊 [{i}/{len(symbols)}] {symbol} | Score: {score:.2f} | Type: {trade_type} | Dir: {direction} | Conf: {confidence:.1f}% | TFs: {tf_breakdown}")
        
        # Log pattern details if detected
        if pattern:
            pattern_direction = get_pattern_direction(pattern)
            log(f"   🎯 Pattern: {pattern} ({pattern_direction}) | Strength: {pattern_strength:.2f}")

        # Calculate SL, TP levels
        result = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence, regime
        )
        sl, tp1, sl_pct, trailing_pct, tp1_pct = result[:5]

        # Check for early pump signals
        pump_data = await detect_early_pump(candles_by_tf, symbol)
        if pump_data["trigger_count"] >= 3:
            pump_reasons = ', '.join([k for k, v in pump_data.items() if v is True and k != "trigger_count"])
            await send_telegram_message(
                f"🚀 <b>Early Pump Signal Detected!</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Triggers:</b> {pump_reasons} ({pump_data['trigger_count']}/4)"
            )
            # Boost score for early pump signals
            score += 0.3
            # Add pump detection to indicators
            indicator_scores["early_pump"] = 1.5
            used_indicators.append("early_pump")

        # Check if score meets minimum thresholds
        min_score_met = False
        if trade_type == "Scalp" and score >= adj_scalp:
            min_score_met = True
        elif trade_type == "Intraday" and score >= adj_intraday:
            min_score_met = True
        elif trade_type == "Swing" and score >= adj_swing:
            # Check cooldown period for this symbol
            current_time = time.time()
            if symbol in recent_swing_trades and (current_time - recent_swing_trades[symbol] < SWING_COOLDOWN):
                log(f"⚠️ Skipping {symbol}: Swing trade cooldown period active ({int((current_time - recent_swing_trades[symbol])/60)} minutes elapsed)")
                min_score_met = False
            # Check for required technical conditions specific to swing trades
            elif not has_strong_swing_conditions(candles_by_tf, tf_scores, direction, trend_context, indicator_scores, used_indicators):
                log(f"⚠️ Skipping {symbol}: Failed additional swing trade validation checks")
                min_score_met = False
            else:
                min_score_met = True
                # Record this swing trade for cooldown tracking
                recent_swing_trades[symbol] = current_time

            if trade_type == "Swing":
                if trend_context.get("regime") != "trending" or trend_context.get("altseason") not in ["confirmed", "strong_altseason"]:
                    log(f"🚫 Skipping Swing setup for {symbol} — market not trending or altseason not confirmed")
                    continue
                    
        # Only allow ALWAYS_ALLOW_SWING exception if score is at least 70% of threshold (increased from 50%)
        elif trade_type == "Swing" and ALWAYS_ALLOW_SWING and score >= adj_swing * 0.7:
            log(f"⚠️ Swing setup below min score ({score} < {adj_swing}), but ALWAYS_ALLOW_SWING is enabled — checking additional conditions.")
    
            # Apply the same additional validation even when using ALWAYS_ALLOW_SWING
            current_time = time.time()
            if symbol in recent_swing_trades and (current_time - recent_swing_trades[symbol] < SWING_COOLDOWN):
                log(f"⚠️ Skipping {symbol}: Swing trade cooldown period active")
                min_score_met = False
            elif not has_strong_swing_conditions(candles_by_tf, tf_scores, direction, trend_context, indicator_scores, used_indicators):
                log(f"⚠️ Skipping {symbol}: Failed additional swing trade validation checks")
                min_score_met = False
            else:
                min_score_met = True
                # Record this swing trade for cooldown tracking
                recent_swing_trades[symbol] = current_time
        
        # Skip if minimum score not met
        if not min_score_met:
            # Check for special conditions that override score requirements
            special_conditions = check_special_entry_conditions(
                symbol, score, indicator_scores, used_indicators, 
                candles_by_tf, trend_context, trade_type
            )
    
            if special_conditions:
                log(f"✅ {symbol}: Special entry condition met despite low score")
                min_score_met = True

        if not meets_quality_standards(symbol, score, confidence, indicator_scores, used_indicators, trade_type, direction, candles_by_tf, trend_context):
            log(f"⚠️ Skipping {symbol}: Failed quality standards check")
            continue

        # Skip shorts in strong uptrends
        btc_trend = trend_context.get("btc_trend", "ranging")
        market_sentiment = trend_context.get("sentiment", "neutral")
        
        if direction == "Short" and btc_trend == "uptrend" and trade_type in ["Scalp", "Intraday"]:
            log(f"⚠️ Skipping {symbol}: Short signal in strong uptrend")
            continue
        
        # Require higher confidence for shorts in neutral/bullish markets
        if direction == "Short" and market_sentiment != "bearish":
            if confidence < 60:
                log(f"⚠️ Skipping {symbol}: Short confidence {confidence}% below 75% threshold")
                continue
        
        # Check if market conditions favor shorts
        if direction == "Short" and not is_short_favorable(candles_by_tf, trend_context):
            log(f"⚠️ Skipping {symbol}: Market conditions unfavorable for shorts")
            continue

        # Check active signals
        if symbol in active_signals:
            data = active_signals[symbol]
            data['score_history'].append(score)
            
            # Don't exit during momentum surges
            has_momentum = detect_momentum_surge(candles_by_tf.get("1", []))
            
            exit_required = (
                not has_momentum and  # Don't exit during momentum
                ((trade_type == "Scalp" and all(s < 5 for s in data['score_history'][-2:])) or
                (trade_type == "Intraday" and all(s < 5 for s in data['score_history'][-3:])) or
                (trade_type == "Swing" and all(s < 4 for s in data['score_history'][-4:])))
            )
            
            if exit_required:
                await send_telegram_message(f"❌ Exit {symbol} | Score dropped.")
                del active_signals[symbol]
                recent_exits[symbol] = EXIT_COOLDOWN
                await log_trade_result(symbol, "loss", -1.0)
            continue

        # OPTIMIZATION: Move duplicate check earlier to avoid wasting time
        if is_duplicate_signal(symbol):
            continue

        # OPTIMIZATION: Track signal and execute trade BEFORE notification
        log_signal(symbol)
        track_signal(symbol, score)

        # Calculate pattern confidence adjustment
        pattern_confidence_multiplier = 1.0
        if pattern and pattern_strength > 0:
            market_conditions = {
                'volatility': regime,
                'trend_strength': 0.5,  # Default moderate trend
                'volume': 'normal'
            }
            
            # Check volume condition
            if is_volume_spike(candles_by_tf.get("1", []), 2.0):
                market_conditions['volume'] = 'high'
            elif get_average_volume(candles_by_tf.get("1", [])) < 500:
                market_conditions['volume'] = 'low'
            
            pattern_prob = pattern_success_probability(pattern, market_conditions)
            pattern_confidence_multiplier = (pattern_prob * 0.6 + pattern_strength * 0.4)
            
            # Apply pattern confidence to overall confidence
            confidence = min(confidence * pattern_confidence_multiplier, 100)
            log(f"   📊 Pattern confidence adjustment: {pattern_confidence_multiplier:.2f} (final conf: {confidence:.1f}%)")

        # Execute trade immediately before Telegram notification - CRITICAL FIX: Pass always_allow_swing flag
        if min_score_met and meets_quality_standards(symbol, score, confidence, indicator_scores, used_indicators, trade_type, direction, candles_by_tf, trend_context):    
            trade = await execute_trade_if_valid({
                "symbol": symbol,
                "price": price,
                "trade_type": trade_type,
                "direction": direction,
                "score": score,
                "confidence": confidence,
                "candles": candles_by_tf,
                "indicator_scores": indicator_scores,
                "used_indicators": used_indicators,
                "tf_scores": tf_scores,
                "pattern": pattern,
                "pattern_strength": pattern_strength,
                "whale": detect_whale_activity(candles_by_tf.get("5", [])),
                "volume_spike": is_volume_spike(candles_by_tf.get("1", []), 2.5),
                "regime": regime,
                "pump_potential": pump_potential,
                "always_allow_swing": ALWAYS_ALLOW_SWING and trade_type == "Swing",
                "market_type": get_symbol_category(symbol),
                "range_break_active": range_break_bonus > 0,
                "range_break_details": range_break_details,
                "range_break_confidence": break_confidence if range_break_bonus > 0 else 0
            })

            # Format and send notification message after trade is placed
            msg = format_trade_signal(
                symbol=symbol,
                score=score,
                tf_scores=tf_scores,
                trend=trend_context,
                entry_price=price,
                sl=sl,
                tp1=tp1,
                trade_type=trade_type,
                direction=direction,
                trailing_pct=trailing_pct,
                leverage=DEFAULT_LEVERAGE,
                risk_pct=risk_pct,
                confidence=confidence,
                sl_pct=sl_pct,      # Add this line
                tp1_pct=tp1_pct     # Add this line
           )

            # Add pattern info to message if detected
            if pattern:
                pattern_dir = get_pattern_direction(pattern)
                msg += f"\n🎯 <b>Pattern:</b> {pattern} ({pattern_dir}) - Strength: {pattern_strength:.2f}"

            # Add pump potential info to message if detected
            if pump_potential:
                msg += "\n🚀 <b>Pump Potential Detected</b> - Using optimized exit strategy"

            await send_telegram_message(msg)
            
            active_signals[symbol] = {
                'score': score,
                'score_history': [score],
                'pattern': pattern
            }

            if trade:
                log(f"🛒 Trade placed successfully for {symbol} at {trade['entry']}")
                write_log(f"TRADE SENT: {symbol} | Entry: {trade['entry']} | SL: {trade['sl']} | TP1: {trade['tp1']}")

            
                track_active_trade(
                    symbol=symbol,
                    trade_type=trade_type,
                    initial_score=score,
                    entry_price=trade['entry'],
                    direction=direction,
                    trailing_pct=trade.get("trailing_pct"),
                    tp1_target=trade.get("tp1"),  # Store the actual TP1 price
                    tp1_pct=tp1_pct,             # Store the TP1 percentage used
                    tp2=trade.get("tp2"),  # Now including TP2 for bigger targets
                    sl=trade.get("sl"),
                    qty=trade.get("qty"),
                    sl_order_id=trade.get("sl_order_id"),
                    exit_tranches=trade.get("exit_tranches"),  # Pass exit tranches
                    has_pump_potential=pump_potential, # Pass pump potential flag
                    range_break_details=range_break_details if range_break_bonus > 0 else None  # Add this line
                )

                from monitor import active_trades
                if symbol in active_trades:
                    log(f"✅ Verified: {symbol} is in active_trades")
                else:
                    log(f"❌ ERROR: {symbol} was NOT added to active_trades!", level="ERROR")

                await verify_stop_loss_placement(symbol, trade, direction)
            else:
                log(f"⚠️ Trade execution failed for {symbol}")
       

        from auto_reentry import cooldown_exits, exit_history
    
        reentry_symbols = []
        for symbol in list(cooldown_exits.keys()):
            if symbol in active_signals:
                continue  # Skip if already tracking
        
            if symbol not in live_candles:
                continue
        
            # Check if cooldown has expired
            if cooldown_exits.get(symbol, 0) > 0:
                continue
        
            reentry_symbols.append(symbol)
    
        # Process reentry symbols first (higher priority)
        for symbol in reentry_symbols:
            try:
                candles_by_tf = {
                    tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
                    if str(tf) in live_candles[symbol]
                }
            
                if not all(len(candles_by_tf.get(tf, [])) >= 30 for tf in TIMEFRAMES):
                    continue
            
                # Score the symbol
                score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                    symbol, candles_by_tf, market_context=trend_context
                )

                if trend_context.get("altseason") == "strong_altseason":
                    score += 0.5
                    log(f"🔥 Score boosted due to strong altseason: {symbol} → {score:.2f}")
                elif trend_context.get("altseason") == "confirmed":
                    score += 0.3
            
                direction = determine_direction(tf_scores)
                confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
                price = float(candles_by_tf['1'][-1]['close'])
            
                # Check reentry conditions
                if await should_reenter(symbol, candles_by_tf, score, direction, trade_type):
                    log(f"🔄 Processing reentry for {symbol} with score {score:.2f}")
                
                    # Boost confidence for reentry trades that meet conditions
                    confidence = min(confidence * 1.1, 100)  # 10% confidence boost
                
                    # Execute the reentry trade
                    await handle_reentry(
                        symbol=symbol,
                        current_score=score,
                        trade_type=trade_type,
                        direction=direction,
                        entry_price=price,
                        candles_by_tf=candles_by_tf
                    )
                
                    # Continue with normal trade execution flow
                    # Calculate SL/TP
                    result = calculate_dynamic_sl_tp(
                        candles_by_tf, price, trade_type, direction, score, confidence, regime
                    )
                    sl, tp1, sl_pct, trailing_pct, tp1_pct = result[:5]
                
                    # Execute trade with reentry flag
                    trade = await execute_trade_if_valid({
                        "symbol": symbol,
                        "price": price,
                        "trade_type": trade_type,
                        "direction": direction,
                        "score": score,
                        "confidence": confidence,
                        "candles": candles_by_tf,
                        "indicator_scores": indicator_scores,
                        "used_indicators": used_indicators,
                        "tf_scores": tf_scores,
                        "regime": regime,
                        "is_reentry": True,  # Flag for tracking
                        "market_type": get_symbol_category(symbol)
                    })
                
                    if trade:
                        # Track the reentry trade
                        active_signals[symbol] = {
                            'score': score,
                            'score_history': [score],
                            'is_reentry': True
                        }
                    
                        log(f"✅ Reentry trade executed for {symbol}")
                    
                        # Skip normal scanning for this symbol
                        continue
                    
            except Exception as e:
                log(f"❌ Error processing reentry for {symbol}: {e}", level="ERROR")
                

            from monitor import active_trades
            if symbol in active_trades:
                log(f"✅ Verified: {symbol} is in active_trades")
            else:
                log(f"❌ ERROR: {symbol} was NOT added to active_trades!", level="ERROR")

            await verify_stop_loss_placement(symbol, trade, direction)
        else:
            log(f"⚠️ Trade execution failed for {symbol}")

        # ✅ Additional Strategy: Mean Reversion Logic
        if regime == "ranging":
            rev_score, rev_dir, rev_conf, rev_reasons = score_mean_reversion(symbol, candles_by_tf, regime)
            if rev_score >= 4 and not is_duplicate_signal(symbol):
                log_signal(symbol)
                track_signal(symbol, rev_score)

                result = calculate_dynamic_sl_tp(
                    candles_by_tf, price, trade_type, direction, score, confidence, regime
                )
                sl, tp1, sl_pct, trailing_pct, tp1_pct = result[:5]

                # OPTIMIZATION: Execute trade BEFORE notification for mean reversion strategy
                mr_trade = await execute_trade_if_valid({
                    "symbol": symbol,
                    "price": price,
                    "trade_type": "Scalp",
                    "direction": rev_dir,
                    "score": rev_score,
                    "confidence": rev_conf,
                    "candles": candles_by_tf,
                    "indicator_scores": {"mean_reversion": rev_score},
                    "used_indicators": list(rev_reasons.keys()),
                    "tf_scores": {"mean_reversion": rev_score},
                    "regime": regime,
                    "always_allow_swing": False  # Mean Reversion doesn't use ALWAYS_ALLOW_SWING
                })

                msg = format_trade_signal(
                    symbol=symbol,
                    score=rev_score,
                    tf_scores={"mean_reversion": rev_score},
                    trend=trend_context,
                    entry_price=price,
                    sl=sl,
                    tp1=tp1,
                    trade_type="Scalp",
                    direction=rev_dir,
                    trailing_pct=trailing_pct,
                    leverage=DEFAULT_LEVERAGE,
                    risk_pct=6.0,
                    confidence=rev_conf,
                    sl_pct=sl_pct,
                    tp1_pct=tp1_pct
                )
                msg += f"\n🧠 Mean Reversion Signal\nTriggers: {', '.join(rev_reasons.keys())}"
                await send_telegram_message(msg)

                if mr_trade:
                    track_active_trade(
                        symbol=symbol,
                        trade_type="Scalp",
                        initial_score=rev_score,
                        entry_price=price,
                        direction=rev_dir,
                        trailing_pct=trailing_pct,
                        tp1_target=mr_trade.get("tp1"),
                        tp1_pct=tp1_pct,
                        tp2=mr_trade.get("tp2"),  # Now including TP2
                        sl=mr_trade.get("sl"),
                        qty=mr_trade.get("qty"),
                        sl_order_id=mr_trade.get("sl_order_id"),
                        exit_tranches=mr_trade.get("exit_tranches")
                    )

        # ✅ Additional Strategy: Breakout Sniper Logic
        if regime == "volatile":
            bo_score, bo_dir, bo_conf, bo_reasons = score_breakout_sniper(symbol, candles_by_tf, regime)
            if bo_score >= 4 and not is_duplicate_signal(symbol):
                log_signal(symbol)
                track_signal(symbol, bo_score)

                result = calculate_dynamic_sl_tp(
                    candles_by_tf, price, trade_type, direction, score, confidence, regime
                )
                sl, tp1, sl_pct, trailing_pct, tp1_pct = result[:5]

                # Check for pump potential in breakout strategy
                bo_pump_potential = has_pump_potential(candles_by_tf, bo_dir)

                # OPTIMIZATION: Execute trade BEFORE notification for breakout strategy
                bo_trade = await execute_trade_if_valid({
                    "symbol": symbol,
                    "price": price,
                    "trade_type": "Scalp",
                    "direction": bo_dir,
                    "score": bo_score,
                    "confidence": bo_conf,
                    "candles": candles_by_tf,
                    "indicator_scores": {"breakout_sniper": bo_score},
                    "used_indicators": list(bo_reasons.keys()),
                    "tf_scores": {"breakout_sniper": bo_score},
                    "regime": regime,
                    "pump_potential": bo_pump_potential,
                    "always_allow_swing": False  # Breakout Sniper doesn't use ALWAYS_ALLOW_SWING
                })

                msg = format_trade_signal(
                    symbol=symbol,
                    score=bo_score,
                    tf_scores={"breakout_sniper": bo_score},
                    trend=trend_context,
                    entry_price=price,
                    sl=sl,
                    tp1=tp1,
                    trade_type="Scalp",
                    direction=bo_dir,
                    trailing_pct=trailing_pct,
                    leverage=DEFAULT_LEVERAGE,
                    risk_pct=6.5,
                    confidence=bo_conf,
                    sl_pct=sl_pct,
                    tp1_pct=tp1_pct
                )
                msg += f"\n💥 Breakout Sniper Signal\nTriggers: {', '.join(bo_reasons.keys())}"

            # Add pump potential info if detected
                if bo_pump_potential:
                    msg += "\n🚀 <b>Pump Potential Detected</b> - Using optimized exit strategy"
                    
                await send_telegram_message(msg)

                if bo_trade:
                    track_active_trade(
                        symbol=symbol,
                        trade_type="Scalp",
                        initial_score=bo_score,
                        entry_price=price,
                        direction=bo_dir,
                        trailing_pct=trailing_pct,
                        tp1_target=bo_trade.get("tp1"),
                        tp1_pct=tp1_pct,
                        tp2=bo_trade.get("tp2"),  # Now including TP2
                        sl=bo_trade.get("sl"),
                        qty=bo_trade.get("qty"),
                        sl_order_id=bo_trade.get("sl_order_id"),
                        exit_tranches=bo_trade.get("exit_tranches"),
                        has_pump_potential=bo_pump_potential
                    )        

        try:
            # Scan for both breaks and pumps
            potential_breaks, potential_pumps = await scan_for_breaks_and_pumps(
                [symbol], live_candles, trend_context
            )
    
            # Handle pump signals with priority
            if potential_pumps:
                pump_signal = potential_pumps[0]  # Current symbol
                log(f"🚀 Pre-pump signal detected for {symbol}! Confidence: {pump_signal['confidence']:.2f}")
        
                # Boost score significantly for pump signals
                score += 2.0
                confidence = min(confidence * 1.3, 100)
        
                # Add pump indicators
                indicator_scores.update({
                    f"pump_{k}": v.get('strength', 1.0) if isinstance(v, dict) else 1.0 
                    for k, v in pump_signal['reasons'].items()
                })
                used_indicators.extend([f"pump_{k}" for k in pump_signal['reasons'].keys()])
        
                # Force direction to Long for pumps
                direction = "Long"
        
                # Mark as pump potential for exit strategy
                pump_potential = True
        
            # Handle regular break signals
            elif potential_breaks:
                break_signal = potential_breaks[0]  # Current symbol
        
                # Override regime if high confidence break
                if break_signal['confidence'] >= 0.7:
                    regime = "volatile"
            
                # Continue with breakout logic...
        
        except Exception as e:
            log(f"❌ Error in break/pump detection for {symbol}: {e}", level="ERROR")

def check_special_entry_conditions(symbol, score, indicator_scores, used_indicators, candles_by_tf, trend_context, trade_type):
    """Check for special conditions that warrant entry despite lower score"""
    
    # 1. Strong whale activity
    whale_score = sum(v for k, v in indicator_scores.items() if 'whale' in k)
    if whale_score > 1.5:
        return True
    
    # 2. Multiple timeframe alignment
    aligned_timeframes = sum(1 for v in indicator_scores.values() if v > 0.5)
    if aligned_timeframes >= 4:
        return True
    
    # 3. Strong momentum
    momentum_score = sum(v for k, v in indicator_scores.items() if 'momentum' in k)
    if momentum_score > 1.0:
        return True
    
    # 4. Stealth accumulation
    stealth_score = sum(v for k, v in indicator_scores.items() if 'stealth' in k)
    if stealth_score > 1.0:
        return True
    
    # 5. Volume surge with pattern
    has_volume_surge = any('volume_spike' in k for k in indicator_scores)
    has_pattern = any('pattern_' in k for k in used_indicators)
    if has_volume_surge and has_pattern and score > (MIN_SCALP_SCORE * 0.8):
        return True
    
    # 6. During altseason, be more lenient
    if trend_context.get("altseason") in ["confirmed", "strong_altseason"]:
        if score > (MIN_SCALP_SCORE * 0.85):  # 85% of minimum
            return True
    
    return False

async def verify_stop_loss_placement(symbol, trade, direction):
    """Verifies that the stop-loss order was properly placed and attempts to fix if not"""
    if trade and trade.get("sl_order_id"):
        log(f"✅ SL order confirmed for {symbol}: {trade.get('sl_order_id')}")
    else:
        # Just log - don't try to restore immediately after placing a trade
        log(f"⚠️ SL order ID not immediately available for {symbol} - will be verified in monitor loop")


async def monitor_loop():
    while True:
        try:
            await monitor_trades(live_candles)
        except Exception as e:
            log(f"❌ Error in monitor loop: {e}", level="ERROR")
            await send_error_to_telegram(traceback.format_exc())
        await asyncio.sleep(5)


async def sl_verification_loop():
    """Periodically verify all stop-losses for active trades"""
    from telegram_bot import send_telegram_message
    from monitor import active_trades
    
    while True:
        try:
            # Only check after the bot has been running for at least 3 minutes
            if time.time() - startup_time < 180:
                await asyncio.sleep(30)
                continue
                
            log(f"🛡️ Running SL verification for {len(active_trades)} active trades")
            
            for symbol, trade in active_trades.items():
                if not trade or trade.get("exited"):
                    continue
                
                await check_and_restore_sl(symbol, trade)
                
            log("✅ SL verification complete")
            
        except Exception as e:
            log(f"❌ Error in SL verification loop: {e}", level="ERROR")
            await send_error_to_telegram(f"SL verification error: {str(e)}")
        
        # Run every 15 minutes
        await asyncio.sleep(900)


async def pattern_discovery_loop(symbols):
    while True:
        try:
            await pattern_discovery_scan(symbols)
        except Exception as e:
            log(f"❌ Error in pattern discovery loop: {e}", level="ERROR")
        await asyncio.sleep(60)


async def pattern_match_loop(symbols):
    while True:
        try:
            await pattern_match_scan(symbols)
        except Exception as e:
            log(f"❌ Error in pattern match loop: {e}")
        await asyncio.sleep(60)


async def pattern_summary_loop():
    while True:
        await asyncio.sleep(3600)
        from pattern_matcher import pattern_stats
        await send_telegram_message(
            f"⏱ <b>Pattern Scan Summary (last hour)</b>\n"
            f"Scans: {pattern_stats['scans']}\n"
            f"Matches: {pattern_stats['matches']}\n"
            f"Trades Triggered: {pattern_stats['trades']}"
        )
        pattern_stats['scans'] = 0
        pattern_stats['matches'] = 0
        pattern_stats['trades'] = 0

async def startup_cleanup():
    """Clean up any orphaned orders on startup"""
    log("🧹 Performing startup cleanup...")
    try:
        from bybit_api import signed_request
        result = await signed_request("POST", "/v5/order/cancel-all", {
            "category": "linear",
            "orderFilter": "Stop"
        })
        log(f"✅ Startup cleanup completed: {result}")
    except Exception as e:
        log(f"❌ Startup cleanup failed: {e}")

async def periodic_cleanup():
    """Periodically verify trade cleanup"""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        await verify_trade_cleanup()

async def verify_all_sl_on_startup():
    """One-time SL verification on startup"""
    log("🔍 Performing startup SL verification...")
    
    for symbol, trade in active_trades.items():
        if trade.get("exited"):
            continue
        
        # Only check if SL is missing
        if not trade.get("sl_order_id"):
            await check_and_restore_sl(symbol, trade)
            await asyncio.sleep(0.5)
    
    log("✅ Startup SL verification complete")

async def run_bot():
    log("🚀 Bot starting...")
    await fetch_symbol_info()
    symbols = await fetch_symbols()
    log(f"✅ Fetched {len(symbols)} symbols.")

    load_risk_state()
    asyncio.create_task(update_risk_metrics())

    load_active_trades()
    
    if len(active_trades) == 0:
        await recover_active_trades_from_exchange()
        
    asyncio.create_task(stream_candles(symbols))
    asyncio.create_task(monitor_loop())
    asyncio.create_task(pattern_discovery_loop(symbols))
    asyncio.create_task(pattern_match_loop(symbols))
    asyncio.create_task(pattern_summary_loop())
    asyncio.create_task(cleanup_cooldowns())
    asyncio.create_task(verify_all_positions(frequency_minutes=15))
    asyncio.create_task(high_frequency_scanner(live_candles))
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(cleanup_pattern_cache())  # Add pattern cache cleanup
    asyncio.create_task(breakout_cache_cleanup())  # Add breakout cache cleanup
    asyncio.create_task(strategy_stats_report())   # Add strategy stats reporting
    asyncio.create_task(periodic_trade_sync())
    asyncio.create_task(periodic_performance_report())
    asyncio.create_task(cleanup_old_records())
    asyncio.create_task(monitor_btc_trend_accuracy())
    asyncio.create_task(monitor_altseason_status())
    asyncio.create_task(cleanup_stealth_cache())
    asyncio.create_task(stealth_activity_report())
    asyncio.create_task(range_break_scanner_loop(symbols))

    await startup_cleanup()

    await asyncio.sleep(5)

    while True:
        try:
            trend_context = await get_trend_context_cached()# ✅ Define it here

            if trend_context.get("altseason") == "strong_altseason":
                ENABLE_MEME_SCANNER = True
                SCAN_SPEED = 3
                log("🚀 Strong altseason detected — enabling meme pump mode and faster scans")
            else:
                ENABLE_MEME_SCANNER = False
                SCAN_SPEED = 5
                
            await scan_for_new_signals(symbols, trend_context)
            await send_daily_report()
        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")
            write_log(f"MAIN LOOP ERROR: {str(e)}", level="ERROR")
            await send_error_to_telegram(traceback.format_exc())
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    log("🔧 DEBUG: main.py is running...")
    log(f"🔍 Starting scan with thresholds - Scalp: {MIN_SCALP_SCORE}, Intraday: {MIN_INTRADAY_SCORE}, Swing: {MIN_SWING_SCORE}")
    
    # Store bot startup time for reference in various functions
    import time
    startup_time = time.time()

    async def restart_forever():
        while True:
            try:
                await run_bot()
            except Exception as e:
                err_msg = f"🔁 Restarting bot due to crash:\n{traceback.format_exc()}"
                log(err_msg, level="ERROR")
                await send_error_to_telegram(err_msg)
                await asyncio.sleep(10)

    asyncio.run(restart_forever())
