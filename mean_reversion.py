# mean_reversion.py - Enhanced Mean Reversion Strategy with Advanced Pattern Detection

import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional
from bollinger import calculate_bollinger_bands_advanced, get_bollinger_signal
from rsi import calculate_rsi_with_bands, calculate_stoch_rsi, get_rsi_signal
from whale_detector import detect_whale_activity, detect_whale_activity_advanced
from volume import get_average_volume, get_volume_momentum, analyze_volume_trend, get_volume_profile
from pattern_detector import (
    detect_pattern, analyze_pattern_strength, detect_pattern_cluster,
    get_pattern_direction, get_all_patterns, REVERSAL_PATTERNS, PATTERN_WEIGHTS
)
from atr import calculate_atr
from logger import log, write_log
from ema import calculate_dema, calculate_tema, calculate_ema_ribbon, analyze_ema_ribbon
from macd import get_macd_divergence
from stealth_detector import detect_stealth_accumulation_advanced
import time

# Configuration constants
MIN_MEAN_REVERSION_SCORE = 4.0
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VOLUME_THRESHOLD = 1000
BB_SQUEEZE_THRESHOLD = 0.02

# Cache for recent calculations to avoid redundant computations
_mr_cache = {}
_cache_ttl = 60  # 60 seconds cache TTL

class MeanReversionAnalyzer:
    """
    Advanced mean reversion analyzer with performance optimizations
    """
    def __init__(self):
        self.score_history = deque(maxlen=100)
        self.success_rate = 0.0
        self.total_trades = 0
        self.successful_trades = 0
        
    def update_performance(self, symbol: str, success: bool):
        """Update performance metrics for mean reversion trades"""
        self.total_trades += 1
        if success:
            self.successful_trades += 1
        self.success_rate = self.successful_trades / self.total_trades if self.total_trades > 0 else 0.0
        log(f"📊 Mean Reversion Performance: {self.success_rate:.2%} success rate ({self.total_trades} trades)")

# Global analyzer instance
_analyzer = MeanReversionAnalyzer()

def calculate_mean_reversion_probability(candles: List[Dict], lookback: int = 20) -> float:
    """
    Calculate the probability of mean reversion based on historical price action
    
    Args:
        candles: List of candle data
        lookback: Period to analyze
        
    Returns:
        float: Probability score (0-1)
    """
    if len(candles) < lookback:
        return 0.0
        
    try:
        closes = np.array([float(c['close']) for c in candles[-lookback:]])
        highs = np.array([float(c['high']) for c in candles[-lookback:]])
        lows = np.array([float(c['low']) for c in candles[-lookback:]])
        
        # Calculate price range and current position
        price_range = highs.max() - lows.min()
        current_price = closes[-1]
        mean_price = closes.mean()
        
        # Calculate how far price is from mean
        deviation = abs(current_price - mean_price) / mean_price
        
        # Calculate volatility
        returns = np.diff(closes) / closes[:-1]
        volatility = returns.std()
        
        # Higher probability when:
        # 1. Price is far from mean (high deviation)
        # 2. Volatility is moderate (not too high, not too low)
        # 3. Price hasn't been trending strongly
        
        # Check for trending vs ranging
        trend_strength = abs(closes[-1] - closes[0]) / price_range if price_range > 0 else 0
        
        # Calculate probability score
        deviation_score = min(deviation * 10, 1.0)  # Cap at 1.0
        volatility_score = 1.0 - abs(volatility - 0.02) * 20  # Optimal volatility around 2%
        ranging_score = 1.0 - trend_strength
        
        probability = (deviation_score * 0.4 + volatility_score * 0.3 + ranging_score * 0.3)
        
        return max(0.0, min(1.0, probability))
        
    except Exception as e:
        log(f"❌ Error calculating mean reversion probability: {e}", level="ERROR")
        return 0.0

def detect_extreme_conditions(candles: List[Dict], rsi_vals: List[float], bb_data: Dict) -> Dict[str, bool]:
    """
    Detect extreme market conditions that favor mean reversion
    
    Returns:
        Dict with extreme condition flags
    """
    extreme_conditions = {
        "extreme_rsi": False,
        "bb_squeeze": False,
        "price_exhaustion": False,
        "volume_climax": False,
        "momentum_divergence": False
    }
    
    if not candles or not rsi_vals or not bb_data:
        return extreme_conditions
        
    try:
        # Check RSI extremes
        current_rsi = rsi_vals[-1]
        extreme_conditions["extreme_rsi"] = current_rsi < 25 or current_rsi > 75
        
        # Check Bollinger Band squeeze
        if bb_data and bb_data[-1]:
            bandwidth = bb_data[-1].get("bandwidth", 1.0)
            extreme_conditions["bb_squeeze"] = bandwidth < BB_SQUEEZE_THRESHOLD
            
        # Check price exhaustion (multiple consecutive candles in same direction)
        if len(candles) >= 5:
            last_5_candles = candles[-5:]
            consecutive_ups = sum(1 for c in last_5_candles if float(c['close']) > float(c['open']))
            consecutive_downs = sum(1 for c in last_5_candles if float(c['close']) < float(c['open']))
            extreme_conditions["price_exhaustion"] = consecutive_ups >= 4 or consecutive_downs >= 4
            
        # Check volume climax
        if len(candles) >= 10:
            volumes = [float(c['volume']) for c in candles[-10:]]
            avg_volume = np.mean(volumes[:-1])
            current_volume = volumes[-1]
            extreme_conditions["volume_climax"] = current_volume > avg_volume * 2.5
            
        # Check momentum divergence
        if len(candles) >= 10 and len(rsi_vals) >= 10:
            # Price making new high/low but RSI not confirming
            price_highs = [float(c['high']) for c in candles[-10:]]
            price_lows = [float(c['low']) for c in candles[-10:]]
            
            if price_highs[-1] == max(price_highs) and rsi_vals[-1] < max(rsi_vals[-10:]):
                extreme_conditions["momentum_divergence"] = True  # Bearish divergence
            elif price_lows[-1] == min(price_lows) and rsi_vals[-1] > min(rsi_vals[-10:]):
                extreme_conditions["momentum_divergence"] = True  # Bullish divergence
                
    except Exception as e:
        log(f"❌ Error detecting extreme conditions: {e}", level="ERROR")
        
    return extreme_conditions

def calculate_support_resistance_levels(candles: List[Dict], lookback: int = 50) -> Dict[str, float]:
    """
    Calculate key support and resistance levels for mean reversion
    
    Returns:
        Dict with support and resistance levels
    """
    if len(candles) < lookback:
        return {}
        
    try:
        highs = np.array([float(c['high']) for c in candles[-lookback:]])
        lows = np.array([float(c['low']) for c in candles[-lookback:]])
        closes = np.array([float(c['close']) for c in candles[-lookback:]])
        volumes = np.array([float(c['volume']) for c in candles[-lookback:]])
        
        # Volume-weighted average price as key level
        vwap = np.sum(closes * volumes) / np.sum(volumes) if np.sum(volumes) > 0 else np.mean(closes)
        
        # Find local highs and lows
        resistance_levels = []
        support_levels = []
        
        for i in range(2, len(highs) - 2):
            # Local high
            if highs[i] > highs[i-1] and highs[i] > highs[i+1] and highs[i] > highs[i-2] and highs[i] > highs[i+2]:
                resistance_levels.append(highs[i])
            # Local low
            if lows[i] < lows[i-1] and lows[i] < lows[i+1] and lows[i] < lows[i-2] and lows[i] < lows[i+2]:
                support_levels.append(lows[i])
                
        # Get strongest levels (most recent and most tested)
        primary_resistance = max(resistance_levels) if resistance_levels else highs.max()
        primary_support = min(support_levels) if support_levels else lows.min()
        
        return {
            "vwap": round(vwap, 8),
            "resistance": round(primary_resistance, 8),
            "support": round(primary_support, 8),
            "range_high": round(highs.max(), 8),
            "range_low": round(lows.min(), 8)
        }
        
    except Exception as e:
        log(f"❌ Error calculating support/resistance: {e}", level="ERROR")
        return {}

def enhanced_pattern_check_for_mean_reversion(candles, tf, direction, score, reasons, confidence_factors):
    """Enhanced pattern confirmation for mean reversion with new pattern detector"""
    # Get all patterns
    all_patterns = get_all_patterns(candles)
    
    # Check for reversal patterns that align with mean reversion
    if direction == "Long":
        bullish_reversals = [p for p in REVERSAL_PATTERNS["bullish"] if all_patterns.get(p, False)]
        if bullish_reversals:
            # Find the strongest pattern
            strongest_pattern = max(bullish_reversals, key=lambda p: PATTERN_WEIGHTS.get(p, 0.5))
            pattern_strength = analyze_pattern_strength(strongest_pattern, candles)
            
            # Adjust score based on pattern strength
            pattern_score = 0.5 * pattern_strength
            score += pattern_score
            reasons[f"{tf}m_pattern_{strongest_pattern}"] = pattern_strength
            confidence_factors.append(0.6 * pattern_strength)
            
            log(f"   🎯 Bullish reversal pattern: {strongest_pattern} (strength: {pattern_strength:.2f})")
    
    elif direction == "Short":
        bearish_reversals = [p for p in REVERSAL_PATTERNS["bearish"] if all_patterns.get(p, False)]
        if bearish_reversals:
            # Find the strongest pattern
            strongest_pattern = max(bearish_reversals, key=lambda p: PATTERN_WEIGHTS.get(p, 0.5))
            pattern_strength = analyze_pattern_strength(strongest_pattern, candles)
            
            # Adjust score based on pattern strength
            pattern_score = 0.5 * pattern_strength
            score += pattern_score
            reasons[f"{tf}m_pattern_{strongest_pattern}"] = pattern_strength
            confidence_factors.append(0.6 * pattern_strength)
            
            log(f"   🎯 Bearish reversal pattern: {strongest_pattern} (strength: {pattern_strength:.2f})")
    
    # Check for pattern clusters (multiple patterns confirming)
    pattern_cluster = detect_pattern_cluster(candles)
    if len(pattern_cluster) >= 2:
        # Multiple patterns increase confidence
        cluster_patterns = [p['pattern'] for p in pattern_cluster]
        aligned_patterns = 0
        
        for p in pattern_cluster:
            p_direction = get_pattern_direction(p['pattern'])
            if (direction == "Long" and p_direction == "bullish") or \
               (direction == "Short" and p_direction == "bearish"):
                aligned_patterns += 1
        
        if aligned_patterns >= 2:
            score += 0.7
            reasons[f"{tf}m_pattern_cluster"] = aligned_patterns
            confidence_factors.append(0.8)
            
            log(f"   📊 Pattern cluster detected: {aligned_patterns} aligned patterns")
    
    return score, reasons, confidence_factors

def score_mean_reversion(symbol: str, candles_by_tf: Dict[str, List[Dict]], regime: str) -> Tuple[float, str, float, Dict]:
    """
    Enhanced mean reversion scoring with advanced pattern detection
    
    Args:
        symbol: Trading pair symbol
        candles_by_tf: Dictionary of candles by timeframe
        regime: Market regime (should be 'ranging' for this strategy)
        
    Returns:
        score, direction, confidence, reasons dictionary
    """
    # Early exit if not in ranging regime
    if regime != "ranging":
        return 0, None, 0, {"not_ranging": True}
    
    # Check cache first
    cache_key = f"{symbol}_mr_{regime}"
    if cache_key in _mr_cache:
        cached_time, cached_result = _mr_cache[cache_key]
        if time.time() - cached_time < _cache_ttl:
            return cached_result
    
    tf_to_check = ["5", "15"]  # Focus on these timeframes for mean reversion
    score = 0
    reasons = {}
    direction = None
    confidence_factors = []
    
    try:
        for tf in tf_to_check:
            candles = candles_by_tf.get(tf)
            if not candles or len(candles) < 30:
                continue
                
            # Current price and basic calculations
            close = float(candles[-1]["close"])
            
            # Calculate RSI with bands
            rsi_data = calculate_rsi_with_bands(candles)
            if not rsi_data:
                continue
                
            rsi = rsi_data["rsi"]
            rsi_values = rsi_data.get("values", [])
            
            # Calculate Bollinger Bands with advanced features
            bb = calculate_bollinger_bands_advanced(candles)
            if not bb or not bb[-1]:
                continue
                
            lower = bb[-1]["lower"]
            upper = bb[-1]["upper"]
            middle = bb[-1]["middle"]
            bandwidth = bb[-1]["bandwidth"]
            percent_b = bb[-1]["percent_b"]
            
            # Pattern detection with enhanced pattern detector
            pattern = detect_pattern(candles)
            
            # Volume analysis
            volume_analysis = analyze_volume_trend(candles)
            avg_vol = get_average_volume(candles)
            volume_momentum = get_volume_momentum(candles)
            
            # Calculate mean reversion probability
            mr_probability = calculate_mean_reversion_probability(candles)
            
            # Detect extreme conditions
            extreme_conditions = detect_extreme_conditions(candles, rsi_values, bb)
            
            # Calculate support/resistance levels
            sr_levels = calculate_support_resistance_levels(candles)
            
            # Enhanced scoring logic
            
            # Strong oversold conditions
            if close < lower and rsi < RSI_OVERSOLD:
                if percent_b < -0.1:  # Well below lower band
                    score += 2.5
                    reasons[f"{tf}m_extreme_oversold"] = True
                else:
                    score += 2
                    reasons[f"{tf}m_boll_rsi_long"] = True
                direction = "Long"
                confidence_factors.append(0.8)
                
                # Bonus for extreme conditions
                if extreme_conditions["extreme_rsi"]:
                    score += 0.5
                    reasons[f"{tf}m_extreme_rsi"] = True
                    
            # Strong overbought conditions
            elif close > upper and rsi > RSI_OVERBOUGHT:
                if percent_b > 1.1:  # Well above upper band
                    score += 2.5
                    reasons[f"{tf}m_extreme_overbought"] = True
                else:
                    score += 2
                    reasons[f"{tf}m_boll_rsi_short"] = True
                direction = "Short"
                confidence_factors.append(0.8)
                
                # Bonus for extreme conditions
                if extreme_conditions["extreme_rsi"]:
                    score += 0.5
                    reasons[f"{tf}m_extreme_rsi"] = True
            
            # ===== ENHANCED PATTERN DETECTION =====
            score, reasons, confidence_factors = enhanced_pattern_check_for_mean_reversion(
                candles, tf, direction, score, reasons, confidence_factors
            )
            
            # ===== EXISTING ADVANCED INDICATOR INTEGRATIONS =====
            
            # 1. Stochastic RSI
            stoch_rsi = calculate_stoch_rsi(candles)
            if stoch_rsi:
                if stoch_rsi['oversold'] and direction == "Long":
                    score += 0.6
                    reasons[f"{tf}m_stoch_rsi_oversold"] = True
                    confidence_factors.append(0.7)
                elif stoch_rsi['overbought'] and direction == "Short":
                    score += 0.6
                    reasons[f"{tf}m_stoch_rsi_overbought"] = True
                    confidence_factors.append(0.7)
                
                # Stoch RSI Cross
                if stoch_rsi.get('cross') == 'bullish_cross' and direction == "Long":
                    score += 0.5
                    reasons[f"{tf}m_stoch_rsi_bullish_cross"] = True
                elif stoch_rsi.get('cross') == 'bearish_cross' and direction == "Short":
                    score += 0.5
                    reasons[f"{tf}m_stoch_rsi_bearish_cross"] = True
            
            # 2. DEMA/TEMA for faster response
            dema = calculate_dema(candles, period=20)
            if dema and len(dema) >= 2:
                if direction == "Long" and dema[-1] > dema[-2]:
                    score += 0.5
                    reasons[f"{tf}m_dema_support"] = True
                    confidence_factors.append(0.6)
                elif direction == "Short" and dema[-1] < dema[-2]:
                    score += 0.5
                    reasons[f"{tf}m_dema_resistance"] = True
                    confidence_factors.append(0.6)
            
            # 3. EMA Ribbon Analysis
            ribbon = calculate_ema_ribbon(candles)
            ribbon_analysis = analyze_ema_ribbon(ribbon)
            if ribbon_analysis['compression']:  # Compression often precedes expansion
                score += 0.4
                reasons[f"{tf}m_ema_compression"] = True
                confidence_factors.append(0.5)
            
            # 4. Volume Profile Analysis
            vol_profile = get_volume_profile(candles)
            if vol_profile and vol_profile.get('poc'):
                poc = vol_profile['poc']
                if direction == "Long" and close < poc * 0.98:
                    score += 0.5
                    reasons[f"{tf}m_below_poc"] = True
                    confidence_factors.append(0.6)
                elif direction == "Short" and close > poc * 1.02:
                    score += 0.5
                    reasons[f"{tf}m_above_poc"] = True
                    confidence_factors.append(0.6)
            
            # 5. Enhanced Bollinger Signal
            bb_signal = get_bollinger_signal(candles)
            if bb_signal['signal'] == 'oversold' and direction == "Long":
                score += 0.5 * bb_signal['strength']
                reasons[f"{tf}m_bb_oversold_signal"] = True
                confidence_factors.append(bb_signal['strength'])
            elif bb_signal['signal'] == 'overbought' and direction == "Short":
                score += 0.5 * bb_signal['strength']
                reasons[f"{tf}m_bb_overbought_signal"] = True
                confidence_factors.append(bb_signal['strength'])
            
            # 6. MACD Divergence for mean reversion
            macd_div = get_macd_divergence(candles)
            if macd_div:
                if macd_div['type'] == 'bullish_divergence' and direction == "Long":
                    score += 0.8
                    reasons[f"{tf}m_macd_bullish_div"] = True
                    confidence_factors.append(0.8)
                elif macd_div['type'] == 'bearish_divergence' and direction == "Short":
                    score += 0.8
                    reasons[f"{tf}m_macd_bearish_div"] = True
                    confidence_factors.append(0.8)
            
            # 7. RSI Signal Analysis
            rsi_signal, rsi_strength = get_rsi_signal(rsi_data, price_trend="ranging")
            if rsi_signal == "buy" and direction == "Long":
                score += 0.6 * rsi_strength
                reasons[f"{tf}m_rsi_buy_signal"] = True
                confidence_factors.append(rsi_strength)
            elif rsi_signal == "sell" and direction == "Short":
                score += 0.6 * rsi_strength
                reasons[f"{tf}m_rsi_sell_signal"] = True
                confidence_factors.append(rsi_strength)
            
            # 8. Advanced Whale Detection
            whale_advanced = detect_whale_activity_advanced(candles, symbol)
            if whale_advanced['detected']:
                if whale_advanced['recommendation'] == 'potential_long' and direction == "Long":
                    score += 0.7 * whale_advanced['strength']
                    reasons[f"{tf}m_whale_accumulation"] = True
                    confidence_factors.append(0.8)
                elif whale_advanced['recommendation'] == 'potential_short' and direction == "Short":
                    score += 0.7 * whale_advanced['strength']
                    reasons[f"{tf}m_whale_distribution"] = True
                    confidence_factors.append(0.8)

            stealth_data = detect_stealth_accumulation_advanced(candles, symbol)
            if stealth_data['detected']:
                if direction == "Long" and stealth_data['recommendation'] in ['strong_accumulation', 'moderate_accumulation']:
                    score += 1.0 * stealth_data['strength']
                    reasons[f"{tf}m_stealth_accumulation"] = stealth_data['strength']
                    confidence_factors.append(0.8)
                    log(f"   🕵️ Stealth accumulation detected: {stealth_data['patterns']}")
                elif direction == "Short" and 'distribution' in stealth_data['patterns']:
                    score += 0.8
                    reasons[f"{tf}m_stealth_distribution"] = True
                    confidence_factors.append(0.7)
            
            # ===== END EXISTING ADVANCED INDICATORS =====
            
            # Bollinger squeeze bonus (coiled spring effect)
            if extreme_conditions["bb_squeeze"]:
                score += 0.5
                reasons[f"{tf}m_bb_squeeze"] = True
                confidence_factors.append(0.7)
                
            # Price exhaustion bonus
            if extreme_conditions["price_exhaustion"]:
                score += 0.5
                reasons[f"{tf}m_exhaustion"] = True
                confidence_factors.append(0.6)
                
            # Volume climax bonus
            if extreme_conditions["volume_climax"]:
                score += 0.5
                reasons[f"{tf}m_volume_climax"] = True
                confidence_factors.append(0.7)
                
            # Momentum divergence bonus
            if extreme_conditions["momentum_divergence"]:
                score += 0.8
                reasons[f"{tf}m_divergence"] = True
                confidence_factors.append(0.8)
                
            # Support/Resistance proximity bonus
            if sr_levels:
                if direction == "Long" and close <= sr_levels.get("support", close) * 1.01:
                    score += 0.5
                    reasons[f"{tf}m_near_support"] = True
                    confidence_factors.append(0.7)
                elif direction == "Short" and close >= sr_levels.get("resistance", close) * 0.99:
                    score += 0.5
                    reasons[f"{tf}m_near_resistance"] = True
                    confidence_factors.append(0.7)
            
            # Volume confirmation
            if avg_vol and avg_vol > VOLUME_THRESHOLD:
                if volume_momentum > 1.2:  # Increasing volume
                    score += 0.3
                    reasons[f"{tf}m_volume_increasing"] = True
                    confidence_factors.append(0.5)
            else:
                score -= 1
                reasons[f"{tf}m_low_vol"] = True
                confidence_factors.append(0.3)
                
            # Whale activity
            if detect_whale_activity(candles):
                score += 1
                reasons[f"{tf}m_whale"] = True
                confidence_factors.append(0.8)
                
            # Mean reversion probability bonus
            if mr_probability > 0.7:
                score += mr_probability
                reasons[f"{tf}m_high_mr_probability"] = round(mr_probability, 2)
                confidence_factors.append(mr_probability)
    
        # Validate minimum requirements
        if score < MIN_MEAN_REVERSION_SCORE:
            log(f"⚠️ Mean reversion score for {symbol} too low: {score:.2f} < {MIN_MEAN_REVERSION_SCORE}")
            result = (0, None, 0, {"score_too_low": score})
            _mr_cache[cache_key] = (time.time(), result)
            return result
        
        # Require at least 3 confirmation signals
        if len(reasons) < 3:
            log(f"⚠️ Mean reversion for {symbol} has insufficient indicators: {len(reasons)} < 3")
            result = (0, None, 0, {"insufficient_indicators": len(reasons)})
            _mr_cache[cache_key] = (time.time(), result)
            return result
            
        # Ensure we have a direction
        if not direction:
            log(f"⚠️ Mean reversion for {symbol} has no clear direction")
            result = (0, None, 0, {"no_direction": True})
            _mr_cache[cache_key] = (time.time(), result)
            return result
        
        # Calculate confidence based on multiple factors
        base_confidence = (score / 8) * 100  # Base confidence from score
        
        # Adjust confidence based on confirmation factors
        if confidence_factors:
            avg_factor = np.mean(confidence_factors)
            confidence = base_confidence * avg_factor
        else:
            confidence = base_confidence
            
        # Boost confidence if multiple extreme conditions are met
        extreme_count = sum(extreme_conditions.values())
        if extreme_count >= 3:
            confidence = min(confidence * 1.2, 100)
            
        # Apply analyzer's historical performance
        if _analyzer.success_rate > 0:
            confidence = confidence * (0.5 + _analyzer.success_rate * 0.5)
            
        confidence = round(min(confidence, 100), 1)
        
        log(f"✅ Valid mean reversion setup for {symbol}: Score {score:.2f}, Dir: {direction}, Conf: {confidence}%")
        log(f"   Reasons: {list(reasons.keys())}")
        log(f"   Extreme conditions: {[k for k, v in extreme_conditions.items() if v]}")
        
        # Cache the result
        result = (score, direction, confidence, reasons)
        _mr_cache[cache_key] = (time.time(), result)
        
        return result
        
    except Exception as e:
        log(f"❌ Error in mean reversion scoring for {symbol}: {e}", level="ERROR")
        import traceback
        log(f"Stack trace: {traceback.format_exc()}", level="ERROR")
        return 0, None, 0, {"error": str(e)}

def clear_cache():
    """Clear the mean reversion cache"""
    global _mr_cache
    _mr_cache.clear()
    log("🧹 Cleared mean reversion cache")

# Periodic cache cleanup
async def cache_cleanup_task():
    """Periodically clean up old cache entries"""
    import asyncio
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        current_time = time.time()
        expired_keys = [k for k, (t, _) in _mr_cache.items() if current_time - t > _cache_ttl]
        for key in expired_keys:
            del _mr_cache[key]
        if expired_keys:
            log(f"🧹 Cleaned {len(expired_keys)} expired cache entries from mean reversion")

# Export analyzer for performance tracking
def get_mean_reversion_stats() -> Dict:
    """Get mean reversion strategy statistics"""
    return {
        "total_trades": _analyzer.total_trades,
        "successful_trades": _analyzer.successful_trades,
        "success_rate": _analyzer.success_rate,
        "cache_size": len(_mr_cache)
    }

def update_mean_reversion_performance(symbol: str, success: bool):
    """Update performance metrics for a mean reversion trade"""
    _analyzer.update_performance(symbol, success)
