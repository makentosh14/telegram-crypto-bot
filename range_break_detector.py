import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import asyncio
from collections import deque

from logger import log, write_log
from volume import get_average_volume, is_volume_spike, get_volume_momentum, analyze_volume_trend
from rsi import calculate_rsi_with_bands, calculate_stoch_rsi
from ema import calculate_ema, get_ema_slope, calculate_ema_ribbon, analyze_ema_ribbon
from pattern_detector import detect_pattern, get_pattern_direction, analyze_pattern_strength
from whale_detector import detect_whale_activity_advanced, get_whale_statistics
from stealth_detector import detect_stealth_accumulation_advanced, calculate_accumulation_score, detect_volume_divergence
from macd import get_macd_momentum, get_macd_divergence
from bollinger import calculate_bollinger_bands_advanced, detect_bollinger_squeeze
from error_handler import send_error_to_telegram

# Configuration
SUPPORT_BREAK_THRESHOLD = 0.995  # 0.5% below support
RESISTANCE_BREAK_THRESHOLD = 1.005  # 0.5% above resistance
VOLUME_SURGE_MULTIPLIER = 1.3  # Lower threshold for early detection
MIN_TESTS_FOR_KEY_LEVEL = 2  # Minimum touches to confirm S/R level
MOMENTUM_SHIFT_THRESHOLD = 0.7  # Strength required for momentum shift

# Pre-pump specific settings
ACCUMULATION_THRESHOLD = 0.6  # Minimum accumulation score
SMART_MONEY_CONFIDENCE = 0.7  # Confidence threshold for smart money detection
PUMP_VOLUME_THRESHOLD = 1.5  # Volume increase for pump signals

# New configurations for enhanced detection
MIN_BODY_SIZE_PCT = 1.0  # Minimum body size as percentage of price
BREAKOUT_CONFIRMATION_CANDLES = 2  # Wait for 2 candles after breakout
STEALTH_DIVERGENCE_LOOKBACK = 20  # Candles to look back for stealth/divergence
PRE_BREAKOUT_ZONE_PCT = 0.003  # 0.3% zone before breakout level
WICK_REJECTION_THRESHOLD = 0.7  # 70% of candle range must be wick for rejection
BUILDUP_LOOKBACK = 30  # Candles to analyze for buildup patterns
COMPRESSION_THRESHOLD = 0.005  # 0.5% range for compression detection

class BreakoutCandidate:
    """Track potential breakouts awaiting confirmation"""
    def __init__(self, symbol: str, direction: str, level: float, initial_candle: Dict, 
                 reasons: Dict, is_pre_breakout: bool = False):
        self.symbol = symbol
        self.direction = direction
        self.breakout_level = level
        self.initial_candle = initial_candle
        self.initial_time = datetime.now()
        self.confirmation_candles = []
        self.reasons = reasons
        self.stealth_detected = False
        self.divergence_detected = False
        self.is_pre_breakout = is_pre_breakout
        self.wick_tests = 0
        self.buildup_score = 0

class RangeBreakDetector:
    """Enhanced detector for range breaks with pre-breakout and wick handling"""
    
    def __init__(self):
        self.level_tests = {}  # Track how many times levels are tested
        self.failed_breakouts = {}  # Track failed breakout attempts
        self.compression_history = deque(maxlen=50)
        self.accumulation_zones = {}  # Track accumulation activity
        self.pump_history = {}  # Track successful pump predictions
        self.breakout_candidates = {}  # Track breakouts awaiting confirmation
        self.recent_stealth_signals = {}  # Track recent stealth/divergence detections
        self.pre_breakout_zones = {}  # Track pre-breakout buildup zones
        self.wick_rejection_history = {}  # Track wick rejections at levels
        
    def detect_imminent_break(self, symbol: str, candles_by_tf: Dict, 
                             current_regime: str) -> Tuple[bool, str, float, Dict]:
        """
        Enhanced detection with pre-breakout buildup and wick analysis
        
        Returns:
            Tuple of (break_imminent, direction, confidence, reasons)
        """
        # Skip if not in ranging market
        if current_regime not in ["ranging", "neutral"]:
            return False, None, 0, {}
            
        # Use 5m candles for primary analysis
        candles = candles_by_tf.get('5', [])
        if len(candles) < 50:
            return False, None, 0, {}
            
        # First, check for recent stealth accumulation or volume divergence
        has_stealth_or_divergence = self._check_recent_stealth_divergence(symbol, candles)
        
        reasons = {}
        confidence = 0
        direction = None
        
        # First check for pre-pump signals
        pump_imminent, pump_confidence, pump_reasons = self._detect_pre_pump_signals(
            symbol, candles_by_tf
        )
        
        if pump_imminent:
            return True, "Long", pump_confidence, pump_reasons
        
        # Find key support/resistance levels
        support, resistance, levels_data = self._find_key_levels(candles)
        if not support or not resistance:
            return False, None, 0, {}
            
        current_price = float(candles[-1]['close'])
        range_size = resistance - support
        position_in_range = (current_price - support) / range_size if range_size > 0 else 0.5
        
        # NEW: Check for pre-breakout buildup patterns
        pre_breakout_detected, pre_direction, pre_reasons = self._detect_pre_breakout_buildup(
            symbol, candles, support, resistance, current_price
        )
        
        if pre_breakout_detected:
            confidence += 0.4
            direction = pre_direction
            reasons.update(pre_reasons)
            log(f"🎯 {symbol}: Pre-breakout buildup detected for {pre_direction}")
            
            # Create a pre-breakout candidate for early entry
            if symbol not in self.breakout_candidates:
                self.breakout_candidates[symbol] = BreakoutCandidate(
                    symbol=symbol,
                    direction=pre_direction,
                    level=resistance if pre_direction == "Long" else support,
                    initial_candle=candles[-1],
                    reasons=reasons,
                    is_pre_breakout=True
                )
        
        # NEW: Check for wick rejection patterns
        wick_rejection, wick_direction, wick_data = self._analyze_wick_rejections(
            symbol, candles, support, resistance
        )
        
        if wick_rejection:
            confidence += 0.25
            if not direction:
                direction = wick_direction
            reasons['wick_rejection'] = wick_data
            log(f"🎯 {symbol}: Wick rejection pattern at {wick_data['level_type']}")
        
        # Check if we have a pending breakout candidate
        if symbol in self.breakout_candidates:
            candidate = self.breakout_candidates[symbol]
            
            # For pre-breakout candidates, check if ready to enter
            if candidate.is_pre_breakout:
                ready, conf_boost = self._check_pre_breakout_entry(symbol, candles, candidate)
                if ready:
                    confidence += conf_boost
                    return True, candidate.direction, confidence, candidate.reasons
            else:
                # Regular breakout confirmation
                confirmed, conf_direction, conf_confidence, conf_reasons = self._check_breakout_confirmation(
                    symbol, candles, candidate
                )
                if confirmed:
                    return True, conf_direction, conf_confidence, conf_reasons
        
        # Check for range compression with enhanced detection
        is_compressing, compression_data = self._detect_enhanced_range_compression(
            candles, support, resistance
        )
        if is_compressing:
            confidence += 0.2
            reasons['range_compression'] = compression_data
            log(f"📊 {symbol}: Enhanced range compression - {compression_data['type']}")
            
        # Check for failed bounces
        failed_bounce, bounce_direction, bounce_data = self._detect_failed_bounces(
            candles, support, resistance
        )
        if failed_bounce:
            confidence += 0.3
            direction = bounce_direction
            reasons['failed_bounce'] = bounce_data
            
        # Check momentum shift
        momentum_shifting, momentum_dir, momentum_data = self._detect_momentum_shift(
            candles, current_regime
        )
        if momentum_shifting:
            confidence += 0.25
            if not direction:
                direction = momentum_dir
            elif direction == momentum_dir:
                confidence += 0.1
            reasons['momentum_shift'] = momentum_data
            
        # Check volume building at extremes
        volume_building, vol_direction, vol_data = self._detect_volume_at_extremes(
            candles, support, resistance, current_price
        )
        if volume_building:
            confidence += 0.2
            if not direction:
                direction = vol_direction
            reasons['volume_building'] = vol_data
            
        # Check for multiple tests of levels
        tests_data = self._check_level_tests(symbol, candles, support, resistance)
        if tests_data['multiple_tests']:
            confidence += 0.15
            reasons['level_tests'] = tests_data
        
        # Require stealth or divergence for breakout signals (unless pre-breakout)
        if not has_stealth_or_divergence and not pre_breakout_detected:
            log(f"📊 {symbol}: Breakout potential but no stealth/divergence - waiting")
            return False, None, 0, {}
        else:
            confidence += 0.2
            reasons['stealth_or_divergence'] = True
        
        # Check for actual breakout with body size filter
        breakout_detected, breakout_direction, breakout_data = self._detect_breakout_with_body_filter(
            candles[-1], support, resistance
        )
        
        if breakout_detected:
            # Create a candidate for confirmation
            self.breakout_candidates[symbol] = BreakoutCandidate(
                symbol=symbol,
                direction=breakout_direction,
                level=breakout_data['level'],
                initial_candle=candles[-1],
                reasons=reasons
            )
            log(f"🎯 {symbol}: Breakout candidate at {breakout_data['level']:.6f} - awaiting confirmation")
            return False, None, 0, {}
        
        # Determine if break is imminent
        break_imminent = confidence >= 0.8 and direction is not None
        
        if break_imminent:
            log(f"🚨 {symbol}: Range break imminent! Direction: {direction}, Confidence: {confidence:.2f}")
            log(f"   Reasons: {list(reasons.keys())}")
            
        return break_imminent, direction, confidence, reasons
    
    def _detect_pre_breakout_buildup(self, symbol: str, candles: List[Dict], 
                                    support: float, resistance: float, 
                                    current_price: float) -> Tuple[bool, str, Dict]:
        """Detect pre-breakout buildup patterns before the actual break"""
        if len(candles) < BUILDUP_LOOKBACK:
            return False, None, {}
            
        reasons = {}
        buildup_score = 0
        direction = None
        
        # 1. Check for tightening range near levels
        recent_candles = candles[-10:]
        ranges = [(float(c['high']) - float(c['low'])) / float(c['low']) * 100 
                  for c in recent_candles]
        
        avg_range = np.mean(ranges)
        if avg_range < COMPRESSION_THRESHOLD * 100:  # Tight range
            # Check position relative to levels
            if abs(current_price - resistance) / resistance < PRE_BREAKOUT_ZONE_PCT:
                buildup_score += 0.4
                direction = "Long"
                reasons['pre_breakout_compression_resistance'] = {
                    'avg_range_pct': avg_range,
                    'distance_to_level': abs(current_price - resistance) / resistance
                }
            elif abs(current_price - support) / support < PRE_BREAKOUT_ZONE_PCT:
                buildup_score += 0.4
                direction = "Short"
                reasons['pre_breakout_compression_support'] = {
                    'avg_range_pct': avg_range,
                    'distance_to_level': abs(current_price - support) / support
                }
        
        # 2. Check for volume buildup in pre-breakout zone
        if direction:
            recent_volumes = [float(c['volume']) for c in recent_candles]
            older_volumes = [float(c['volume']) for c in candles[-30:-10]]
            
            vol_increase = np.mean(recent_volumes) / np.mean(older_volumes) if np.mean(older_volumes) > 0 else 1
            
            if vol_increase > 1.2:  # 20% volume increase
                buildup_score += 0.3
                reasons['pre_breakout_volume_buildup'] = vol_increase
        
        # 3. Check for higher lows (bullish) or lower highs (bearish)
        if direction == "Long":
            lows = [float(c['low']) for c in candles[-10:]]
            higher_lows = all(lows[i] >= lows[i-1] * 0.999 for i in range(1, len(lows)))
            if higher_lows:
                buildup_score += 0.2
                reasons['higher_lows_pattern'] = True
                
        elif direction == "Short":
            highs = [float(c['high']) for c in candles[-10:]]
            lower_highs = all(highs[i] <= highs[i-1] * 1.001 for i in range(1, len(highs)))
            if lower_highs:
                buildup_score += 0.2
                reasons['lower_highs_pattern'] = True
        
        # 4. Check Bollinger Band squeeze in pre-breakout zone
        bb_data = calculate_bollinger_bands_advanced(candles)
        if bb_data and len(bb_data) > 0:
            squeeze_info = detect_bollinger_squeeze(bb_data)
            if squeeze_info['squeeze'] and direction:
                buildup_score += 0.3
                reasons['bb_squeeze_pre_breakout'] = squeeze_info
        
        # 5. Check for accumulation/distribution patterns
        if direction == "Long":
            # Look for accumulation: high volume on up moves, low volume on down moves
            accumulation_score = self._calculate_accumulation_distribution_score(recent_candles, "accumulation")
            if accumulation_score > 0.6:
                buildup_score += 0.3
                reasons['accumulation_pattern'] = accumulation_score
        else:
            # Look for distribution
            distribution_score = self._calculate_accumulation_distribution_score(recent_candles, "distribution")
            if distribution_score > 0.6:
                buildup_score += 0.3
                reasons['distribution_pattern'] = distribution_score
        
        # Store buildup information
        if buildup_score > 0.8:
            if symbol not in self.pre_breakout_zones:
                self.pre_breakout_zones[symbol] = {
                    'direction': direction,
                    'level': resistance if direction == "Long" else support,
                    'buildup_start': datetime.now(),
                    'buildup_score': buildup_score
                }
            
            return True, direction, reasons
            
        return False, None, {}
    
    def _analyze_wick_rejections(self, symbol: str, candles: List[Dict], 
                                support: float, resistance: float) -> Tuple[bool, str, Dict]:
        """Analyze wick rejection patterns at key levels"""
        if len(candles) < 5:
            return False, None, {}
            
        # Initialize tracking
        if symbol not in self.wick_rejection_history:
            self.wick_rejection_history[symbol] = {
                'resistance_rejections': [],
                'support_rejections': []
            }
            
        # Check last 5 candles for wick rejections
        for i in range(-5, 0):
            candle = candles[i]
            high = float(candle['high'])
            low = float(candle['low'])
            close = float(candle['close'])
            open_price = float(candle['open'])
            
            body_size = abs(close - open_price)
            total_range = high - low
            
            if total_range == 0:
                continue
                
            # Check for resistance rejection (long upper wick)
            if high >= resistance * 0.998:  # Touched resistance
                upper_wick = high - max(close, open_price)
                wick_ratio = upper_wick / total_range
                
                if wick_ratio >= WICK_REJECTION_THRESHOLD:
                    self.wick_rejection_history[symbol]['resistance_rejections'].append({
                        'candle_index': i,
                        'wick_ratio': wick_ratio,
                        'rejection_price': high
                    })
                    
            # Check for support rejection (long lower wick)
            if low <= support * 1.002:  # Touched support
                lower_wick = min(close, open_price) - low
                wick_ratio = lower_wick / total_range
                
                if wick_ratio >= WICK_REJECTION_THRESHOLD:
                    self.wick_rejection_history[symbol]['support_rejections'].append({
                        'candle_index': i,
                        'wick_ratio': wick_ratio,
                        'rejection_price': low
                    })
        
        # Analyze rejection patterns
        resistance_rejections = len(self.wick_rejection_history[symbol]['resistance_rejections'])
        support_rejections = len(self.wick_rejection_history[symbol]['support_rejections'])
        
        # Multiple rejections indicate strong level and potential reversal
        if resistance_rejections >= 2:
            # Resistance holding, likely to break down
            wick_data = {
                'level_type': 'resistance',
                'rejection_count': resistance_rejections,
                'avg_wick_ratio': np.mean([r['wick_ratio'] for r in 
                    self.wick_rejection_history[symbol]['resistance_rejections']]),
                'strength': min(resistance_rejections / 3, 1.0)
            }
            return True, "Short", wick_data
            
        elif support_rejections >= 2:
            # Support holding, likely to break up
            wick_data = {
                'level_type': 'support',
                'rejection_count': support_rejections,
                'avg_wick_ratio': np.mean([r['wick_ratio'] for r in 
                    self.wick_rejection_history[symbol]['support_rejections']]),
                'strength': min(support_rejections / 3, 1.0)
            }
            return True, "Long", wick_data
            
        return False, None, {}
    
    def _check_pre_breakout_entry(self, symbol: str, candles: List[Dict], 
                                 candidate: BreakoutCandidate) -> Tuple[bool, float]:
        """Check if pre-breakout candidate is ready for entry"""
        current_price = float(candles[-1]['close'])
        
        # Time elapsed since detection
        time_elapsed = (datetime.now() - candidate.initial_time).seconds / 60
        
        # Don't wait too long
        if time_elapsed > 30:  # 30 minutes
            del self.breakout_candidates[symbol]
            return False, 0
            
        confidence_boost = 0
        ready_to_enter = False
        
        # 1. Check if price is still in pre-breakout zone
        if candidate.direction == "Long":
            distance_to_level = (candidate.breakout_level - current_price) / current_price
            if 0 < distance_to_level < PRE_BREAKOUT_ZONE_PCT:
                ready_to_enter = True
                confidence_boost = 0.2
        else:  # Short
            distance_to_level = (current_price - candidate.breakout_level) / current_price
            if 0 < distance_to_level < PRE_BREAKOUT_ZONE_PCT:
                ready_to_enter = True
                confidence_boost = 0.2
        
        # 2. Check for additional confirmation signals
        if ready_to_enter:
            # Volume confirmation
            recent_vol = float(candles[-1]['volume'])
            avg_vol = get_average_volume(candles[:-1])
            
            if recent_vol > avg_vol * 1.3:
                confidence_boost += 0.1
                
            # Pattern confirmation
            pattern = detect_pattern(candles)
            if pattern:
                pattern_dir = get_pattern_direction(pattern)
                if (pattern_dir == "bullish" and candidate.direction == "Long") or \
                   (pattern_dir == "bearish" and candidate.direction == "Short"):
                    confidence_boost += 0.15
                    
        return ready_to_enter, confidence_boost
    
    def _detect_enhanced_range_compression(self, candles: List[Dict], support: float, 
                                         resistance: float) -> Tuple[bool, Dict]:
        """Enhanced range compression detection with multiple methods"""
        if len(candles) < 30:
            return False, {}
            
        # Method 1: Traditional range size over time
        range_sizes = []
        for i in range(10, len(candles)):
            period_candles = candles[i-10:i]
            period_high = max(float(c['high']) for c in period_candles)
            period_low = min(float(c['low']) for c in period_candles)
            range_size = (period_high - period_low) / period_low * 100
            range_sizes.append(range_size)
        
        # Method 2: ATR-based compression
        from atr import calculate_atr
        atr_short = calculate_atr(candles, period=7)
        atr_long = calculate_atr(candles, period=21)
        
        atr_compression = False
        if atr_short and atr_long and atr_long > 0:
            atr_ratio = atr_short / atr_long
            atr_compression = atr_ratio < 0.7  # 30% compression
        
        # Method 3: Bollinger Band width
        bb_data = calculate_bollinger_bands_advanced(candles)
        bb_compression = False
        if bb_data and len(bb_data) >= 20:
            recent_bandwidths = [b['bandwidth'] for b in bb_data[-10:] if b]
            older_bandwidths = [b['bandwidth'] for b in bb_data[-30:-10] if b]
            
            if recent_bandwidths and older_bandwidths:
                bb_compression = np.mean(recent_bandwidths) < np.mean(older_bandwidths) * 0.7
        
        # Combine compression signals
        compression_count = sum([
            len(range_sizes) > 0 and np.mean(range_sizes[-5:]) < np.mean(range_sizes[-20:-10]) * 0.8,
            atr_compression,
            bb_compression
        ])
        
        is_compressing = compression_count >= 2  # Need at least 2 methods to confirm
        
        compression_data = {
            'type': 'multi-method',
            'compression_signals': compression_count,
            'current_range': resistance - support,
            'atr_compression': atr_compression,
            'bb_compression': bb_compression
        }
        
        return is_compressing, compression_data
    
    def _calculate_accumulation_distribution_score(self, candles: List[Dict], 
                                                 type_: str) -> float:
        """Calculate accumulation/distribution score based on volume and price action"""
        if len(candles) < 5:
            return 0
            
        score = 0
        for candle in candles:
            close = float(candle['close'])
            open_price = float(candle['open'])
            high = float(candle['high'])
            low = float(candle['low'])
            volume = float(candle['volume'])
            
            # Calculate money flow multiplier
            if high - low > 0:
                mf_multiplier = ((close - low) - (high - close)) / (high - low)
            else:
                mf_multiplier = 0
                
            # Calculate money flow volume
            mf_volume = mf_multiplier * volume
            
            if type_ == "accumulation":
                # Positive MF with increasing close = accumulation
                if mf_volume > 0 and close > open_price:
                    score += 1
                elif mf_volume < 0 and close < open_price:
                    score -= 0.5
            else:  # distribution
                # Negative MF with decreasing close = distribution
                if mf_volume < 0 and close < open_price:
                    score += 1
                elif mf_volume > 0 and close > open_price:
                    score -= 0.5
                    
        return max(0, score / len(candles))
    
    # ... (keep all other existing methods from the original file) ...
    
    def _check_recent_stealth_divergence(self, symbol: str, candles: List[Dict]) -> bool:
        """Check if stealth accumulation or volume divergence was recently detected"""
        # Check recent stealth accumulation
        stealth_result = detect_stealth_accumulation_advanced(candles[-STEALTH_DIVERGENCE_LOOKBACK:], symbol)
        if stealth_result['detected'] and stealth_result['strength'] > 0.6:
            self.recent_stealth_signals[symbol] = {
                'time': datetime.now(),
                'type': 'stealth',
                'strength': stealth_result['strength']
            }
            return True
        
        # Check volume divergence
        if detect_volume_divergence(candles[-STEALTH_DIVERGENCE_LOOKBACK:]):
            self.recent_stealth_signals[symbol] = {
                'time': datetime.now(),
                'type': 'divergence',
                'strength': 0.8
            }
            return True
        
        # Check if we have a recent signal (within last 20 candles ~ 100 minutes on 5m)
        if symbol in self.recent_stealth_signals:
            signal = self.recent_stealth_signals[symbol]
            time_elapsed = (datetime.now() - signal['time']).seconds / 60  # minutes
            if time_elapsed < 100:  # Still valid
                return True
            else:
                # Clean up old signal
                del self.recent_stealth_signals[symbol]
        
        return False
    
    def _detect_breakout_with_body_filter(self, candle: Dict, support: float, resistance: float) -> Tuple[bool, str, Dict]:
        """Detect breakout with minimum body size requirement"""
        high = float(candle['high'])
        low = float(candle['low'])
        close = float(candle['close'])
        open_price = float(candle['open'])
        
        # Calculate body size as percentage
        body_size = abs(close - open_price)
        body_size_pct = (body_size / open_price) * 100
        
        # Check if body size meets minimum requirement
        if body_size_pct < MIN_BODY_SIZE_PCT:
            return False, None, {}
        
        breakout_data = {
            'body_size_pct': body_size_pct,
            'is_bullish': close > open_price
        }
        
        # Check for resistance breakout
        if close > resistance * RESISTANCE_BREAK_THRESHOLD and close > open_price:
            breakout_data['type'] = 'resistance'
            breakout_data['level'] = resistance
            return True, "Long", breakout_data
        
        # Check for support breakdown
        if close < support * SUPPORT_BREAK_THRESHOLD and close < open_price:
            breakout_data['type'] = 'support'
            breakout_data['level'] = support
            return True, "Short", breakout_data
        
        return False, None, {}
    
    def _check_breakout_confirmation(self, symbol: str, candles: List[Dict], 
                                   candidate: BreakoutCandidate) -> Tuple[bool, str, float, Dict]:
        """Enhanced breakout confirmation with wick analysis"""
        # Add new candles since breakout
        candles_since_breakout = []
        for candle in candles[-BREAKOUT_CONFIRMATION_CANDLES:]:
            if candle != candidate.initial_candle:
                candles_since_breakout.append(candle)
        
        if len(candles_since_breakout) < BREAKOUT_CONFIRMATION_CANDLES:
            return False, None, 0, {}
        
        # Check confirmation criteria
        confirmed = False
        confidence = 0.7  # Base confidence for delayed entry
        
        # Track wick tests during confirmation
        wick_test_count = 0
        
        if candidate.direction == "Long":
            # For long breakout, check if price stays above level
            all_above = True
            for candle in candles_since_breakout:
                low = float(candle['low'])
                close = float(candle['close'])
                
                # Check if low wicked below but closed above
                if low < candidate.breakout_level:
                    if close > candidate.breakout_level:
                        wick_test_count += 1
                    else:
                        all_above = False
                        break
            
            trend_up = float(candles_since_breakout[-1]['close']) > float(candles_since_breakout[0]['open'])
            
            # Allow for wick tests as long as closes stay above
            if (all_above or wick_test_count >= 1) and trend_up:
                confirmed = True
                confidence += 0.2
                
                if wick_test_count > 0:
                    confidence += 0.1  # Successful retest adds confidence
                    candidate.reasons['successful_retest'] = wick_test_count
                    
        else:  # Short
            # For short breakout, check if price stays below level
            all_below = True
            for candle in candles_since_breakout:
                high = float(candle['high'])
                close = float(candle['close'])
                
                # Check if high wicked above but closed below
                if high > candidate.breakout_level:
                    if close < candidate.breakout_level:
                        wick_test_count += 1
                    else:
                        all_below = False
                        break
            
            trend_down = float(candles_since_breakout[-1]['close']) < float(candles_since_breakout[0]['open'])
            
            if (all_below or wick_test_count >= 1) and trend_down:
                confirmed = True
                confidence += 0.2
                
                if wick_test_count > 0:
                    confidence += 0.1
                    candidate.reasons['successful_retest'] = wick_test_count
        
        if confirmed:
            # Check volume confirmation
            avg_volume = get_average_volume(candles[:-BREAKOUT_CONFIRMATION_CANDLES])
            confirmation_volume = np.mean([float(c['volume']) for c in candles_since_breakout])
            
            if confirmation_volume > avg_volume * 1.2:
                confidence += 0.1
                candidate.reasons['volume_confirmed'] = True
            
            # Clean up candidate
            del self.breakout_candidates[symbol]
            
            log(f"✅ {symbol}: Breakout confirmed after {len(candles_since_breakout)} candles (wick tests: {wick_test_count})")
            return True, candidate.direction, confidence, candidate.reasons
        
        # Check if breakout failed
        time_elapsed = (datetime.now() - candidate.initial_time).seconds / 60
        if time_elapsed > 15:  # 15 minutes timeout
            log(f"❌ {symbol}: Breakout candidate expired without confirmation")
            del self.breakout_candidates[symbol]
        
        return False, None, 0, {}
    
    # ... (include all other methods from the original file that weren't modified) ...

# Global instance
range_break_detector = RangeBreakDetector()
