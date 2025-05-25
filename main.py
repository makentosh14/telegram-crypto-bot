import asyncio
import traceback
import time
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_direction, calculate_confidence, has_pump_potential
from telegram_bot import send_telegram_message, format_trade_signal, send_error_to_telegram
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import DEFAULT_LEVERAGE, ALWAYS_ALLOW_SWING
from performance_tracker import track_signal
from logger import log
from monitor_report import log_trade_result, send_daily_report
from trade_executor import calculate_dynamic_sl_tp, execute_trade_if_valid
from pump_detector import detect_early_pump
from symbol_info import fetch_symbol_info
from activity_logger import write_log, log_trade_to_file
from monitor import track_active_trade, monitor_trades, load_active_trades, check_and_restore_sl, active_trades
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

load_memory()

TIMEFRAMES = SUPPORTED_INTERVALS
active_signals = {}
recent_exits = {}
EXIT_COOLDOWN = 10
recent_swing_trades = {}  # Track recent swing trades by symbol with timestamp
SWING_COOLDOWN = 3600  # 1 hour cooldown in seconds

# Slightly reduced thresholds in volatile regime to capture more potential pumps
MIN_SCALP_SCORE = 7.5
MIN_INTRADAY_SCORE = 8.5
MIN_SWING_SCORE = 10

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

def meets_quality_standards(symbol, score, confidence, indicator_scores, used_indicators, trade_type):
    """
    Quality filter to ensure only high-probability trades are taken
    
    Returns:
        bool: True if trade meets quality standards
    """
    # 1. Require minimum confidence based on trade type
    min_confidence = {
        "Scalp": 65,
        "Intraday": 70,
        "Swing": 75
    }
    
    if confidence < min_confidence.get(trade_type, 65):
        log(f"⚠️ {symbol}: Confidence {confidence:.1f}% below minimum {min_confidence[trade_type]}%")
        return False
    
    # 2. Check for conflicting signals
    bullish_count = sum(1 for k, v in indicator_scores.items() if v > 0)
    bearish_count = sum(1 for k, v in indicator_scores.items() if v < 0)
    
    # If we have too many conflicting signals, skip
    if min(bullish_count, bearish_count) > 2:
        log(f"⚠️ {symbol}: Too many conflicting signals (Bull: {bullish_count}, Bear: {bearish_count})")
        return False
    
    # 3. Require at least one strong indicator (score > 1.0)
    strong_indicators = [k for k, v in indicator_scores.items() if abs(v) > 1.0]
    if len(strong_indicators) < 1:
        log(f"⚠️ {symbol}: No strong indicators found (need at least one with score > 1.0)")
        return False
    
    # 4. Require minimum number of confirming indicators
    min_indicators_required = {
        "Scalp": 4,
        "Intraday": 5,
        "Swing": 6
    }
    
    if len(used_indicators) < min_indicators_required.get(trade_type, 4):
        log(f"⚠️ {symbol}: Insufficient indicators: {len(used_indicators)} < {min_indicators_required[trade_type]}")
        return False
    
    # 5. For Swing trades, require even stronger confirmation
    if trade_type == "Swing":
        # Need at least 2 strong indicators for swing trades
        if len(strong_indicators) < 2:
            log(f"⚠️ {symbol}: Swing trade needs at least 2 strong indicators, found {len(strong_indicators)}")
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

async def scan_for_new_signals(symbols):
    trend_context = await get_trend_context()
    regime = trend_context.get("regime", "trending")

    # Adjust score thresholds based on regime
    # In volatile regimes, lower thresholds to catch more pumps
    score_adjustments = {
        "volatile": {"scalp": -0.2, "intraday": -0.2, "swing": -0.3},  # Less reduction in volatile markets
        "ranging": {"scalp": 0.8, "intraday": 0.8, "swing": 1.0},      # Higher penalty for ranging markets
        "trending": {"scalp": 0.0, "intraday": 0.0, "swing": 0.0},     # No adjustment for trending
    }
    adjust = score_adjustments.get(regime, {"scalp": 0, "intraday": 0, "swing": 0})
    adj_scalp = MIN_SCALP_SCORE + adjust["scalp"]
    adj_intraday = MIN_INTRADAY_SCORE + adjust["intraday"]
    adj_swing = MIN_SWING_SCORE + adjust["swing"]

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
        score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(symbol, candles_by_tf)
        direction = determine_direction(tf_scores)
        confidence = calculate_confidence(score, tf_scores, trend_context, trade_type)
        price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0

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
        if trade_type == "Scalp":
            base_risk = 0.09
        elif trade_type == "Intraday":
            base_risk = 0.06
        else:
            base_risk = 0.03
           
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
            log(f"⚠️ Skipping {symbol}: Score {score:.2f} below minimum threshold for {trade_type} ({adj_scalp if trade_type == 'Scalp' else adj_intraday if trade_type == 'Intraday' else adj_swing})")
            continue

        if not meets_quality_standards(symbol, score, confidence, indicator_scores, used_indicators, trade_type):
            log(f"⚠️ Skipping {symbol}: Failed quality standards check")
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
            "market_type": get_symbol_category(symbol)
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

            # Pass pump potential and exit tranches to trade tracker
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
                has_pump_potential=pump_potential  # Pass pump potential flag
            )

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

async def verify_stop_loss_placement(symbol, trade, direction):
    """Verifies that the stop-loss order was properly placed and attempts to fix if not"""
    from monitor import check_and_restore_sl
    
    if not trade or not trade.get("sl_order_id"):
        log(f"⚠️ No SL order ID found for {symbol}, attempting to restore", level="WARN")
        # Create a temporary trade object with the minimum needed info for check_and_restore_sl
        temp_trade = {
            "direction": direction,
            "qty": trade.get("qty"),
            "original_sl": trade.get("sl"),
            "entry_price": trade.get("entry"),
            "exited": False
        }
        await check_and_restore_sl(symbol, temp_trade)
        await send_telegram_message(f"🔄 <b>SL Verification</b>: Attempted to restore missing SL for {symbol}")
    else:
        log(f"✅ SL order confirmed for {symbol}: {trade.get('sl_order_id')}")


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
    asyncio.create_task(sl_verification_loop())
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(cleanup_pattern_cache())  # Add pattern cache cleanup
    asyncio.create_task(breakout_cache_cleanup())  # Add breakout cache cleanup
    asyncio.create_task(strategy_stats_report())   # Add strategy stats reporting
    asyncio.create_task(periodic_trade_sync())

    await startup_cleanup()

    await asyncio.sleep(5)

    while True:
        try:
            await scan_for_new_signals(symbols)
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
