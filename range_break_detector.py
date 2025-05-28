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

# New configurations
MIN_BODY_SIZE_PCT = 1.0  # Minimum body size as percentage of price
BREAKOUT_CONFIRMATION_CANDLES = 2  # Wait for 2 candles after breakout
STEALTH_DIVERGENCE_LOOKBACK = 20  # Candles to look back for stealth/divergence

class BreakoutCandidate:
    """Track potential breakouts awaiting confirmation"""
    def __init__(self, symbol: str, direction: str, level: float, initial_candle: Dict, reasons: Dict):
        self.symbol = symbol
        self.direction = direction
        self.breakout_level = level
        self.initial_candle = initial_candle
        self.initial_time = datetime.now()
        self.confirmation_candles = []
        self.reasons = reasons
        self.stealth_detected = False
        self.divergence_detected = False

class RangeBreakDetector:
    """Detects range breaks AND pre-pump signals BEFORE they fully develop"""
    
    def __init__(self):
        self.level_tests = {}  # Track how many times levels are tested
        self.failed_breakouts = {}  # Track failed breakout attempts
        self.compression_history = deque(maxlen=50)
        self.accumulation_zones = {}  # Track accumulation activity
        self.pump_history = {}  # Track successful pump predictions
        self.breakout_candidates = {}  # Track breakouts awaiting confirmation
        self.recent_stealth_signals = {}  # Track recent stealth/divergence detections
        
    def detect_imminent_break(self, symbol: str, candles_by_tf: Dict, 
                             current_regime: str) -> Tuple[bool, str, float, Dict]:
        """
        Enhanced detection with stealth/divergence requirements and delayed entry
        
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
        
        # First check for pre-pump signals (they often have different characteristics)
        pump_imminent, pump_confidence, pump_reasons = self._detect_pre_pump_signals(
            symbol, candles_by_tf
        )
        
        if pump_imminent:
            return True, "Long", pump_confidence, pump_reasons
        
        # Continue with regular break detection (includes dumps)
        
        # 1. Find key support/resistance levels
        support, resistance, levels_data = self._find_key_levels(candles)
        if not support or not resistance:
            return False, None, 0, {}
            
        current_price = float(candles[-1]['close'])
        range_size = resistance - support
        position_in_range = (current_price - support) / range_size if range_size > 0 else 0.5
        
        # Check if we have a pending breakout candidate
        if symbol in self.breakout_candidates:
            candidate = self.breakout_candidates[symbol]
            confirmed, conf_direction, conf_confidence, conf_reasons = self._check_breakout_confirmation(
                symbol, candles, candidate
            )
            if confirmed:
                return True, conf_direction, conf_confidence, conf_reasons
        
        # 2. Check for range compression
        is_compressing, compression_data = self._detect_range_compression(candles, support, resistance)
        if is_compressing:
            confidence += 0.2
            reasons['range_compression'] = compression_data
            log(f"📊 {symbol}: Range compression detected - {compression_data['compression_pct']:.1f}% tighter")
            
        # 3. Check for failed bounces
        failed_bounce, bounce_direction, bounce_data = self._detect_failed_bounces(
            candles, support, resistance
        )
        if failed_bounce:
            confidence += 0.3
            direction = bounce_direction
            reasons['failed_bounce'] = bounce_data
            log(f"📊 {symbol}: Failed bounce at {bounce_direction} - strength: {bounce_data['weakness']:.2f}")
            
        # 4. Check momentum shift
        momentum_shifting, momentum_dir, momentum_data = self._detect_momentum_shift(
            candles, current_regime
        )
        if momentum_shifting:
            confidence += 0.25
            if not direction:
                direction = momentum_dir
            elif direction == momentum_dir:
                confidence += 0.1  # Extra confidence if directions align
            reasons['momentum_shift'] = momentum_data
            log(f"📊 {symbol}: Momentum shifting {momentum_dir} - strength: {momentum_data['strength']:.2f}")
            
        # 5. Check volume building at extremes
        volume_building, vol_direction, vol_data = self._detect_volume_at_extremes(
            candles, support, resistance, current_price
        )
        if volume_building:
            confidence += 0.2
            if not direction:
                direction = vol_direction
            reasons['volume_building'] = vol_data
            
        # 6. Check for multiple tests of levels
        tests_data = self._check_level_tests(symbol, candles, support, resistance)
        if tests_data['multiple_tests']:
            confidence += 0.15
            reasons['level_tests'] = tests_data
        
        # NEW: Require stealth or divergence for breakout signals
        if not has_stealth_or_divergence:
            log(f"📊 {symbol}: Breakout potential detected but no recent stealth/divergence - waiting")
            return False, None, 0, {}
        else:
            confidence += 0.2  # Bonus for having stealth/divergence
            reasons['stealth_or_divergence'] = True
        
        # Check for actual breakout with body size filter
        breakout_detected, breakout_direction, breakout_data = self._detect_breakout_with_body_filter(
            candles[-1], support, resistance
        )
        
        if breakout_detected:
            # Instead of immediate signal, create a candidate for confirmation
            self.breakout_candidates[symbol] = BreakoutCandidate(
                symbol=symbol,
                direction=breakout_direction,
                level=breakout_data['level'],
                initial_candle=candles[-1],
                reasons=reasons
            )
            log(f"🎯 {symbol}: Breakout candidate detected at {breakout_data['level']:.6f} - awaiting confirmation")
            return False, None, 0, {}  # Don't signal yet
        
        # Determine if break is imminent (but not yet occurred)
        break_imminent = confidence >= 0.8 and direction is not None
        
        if break_imminent:
            log(f"🚨 {symbol}: Range break imminent! Direction: {direction}, Confidence: {confidence:.2f}")
            log(f"   Reasons: {list(reasons.keys())}")
            
        return break_imminent, direction, confidence, reasons
    
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
        """Check if breakout candidate has been confirmed after 1-2 candles"""
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
        
        if candidate.direction == "Long":
            # For long breakout, check if price stays above level
            all_above = all(float(c['low']) > candidate.breakout_level * 0.998 for c in candles_since_breakout)
            trend_up = float(candles_since_breakout[-1]['close']) > float(candles_since_breakout[0]['open'])
            
            if all_above and trend_up:
                confirmed = True
                confidence += 0.2
                
                # Check for retest
                retested = any(float(c['low']) < candidate.breakout_level * 1.005 for c in candles_since_breakout)
                if retested:
                    confidence += 0.1
                    candidate.reasons['retest_confirmed'] = True
                    
        else:  # Short
            # For short breakout, check if price stays below level
            all_below = all(float(c['high']) < candidate.breakout_level * 1.002 for c in candles_since_breakout)
            trend_down = float(candles_since_breakout[-1]['close']) < float(candles_since_breakout[0]['open'])
            
            if all_below and trend_down:
                confirmed = True
                confidence += 0.2
                
                # Check for retest
                retested = any(float(c['high']) > candidate.breakout_level * 0.995 for c in candles_since_breakout)
                if retested:
                    confidence += 0.1
                    candidate.reasons['retest_confirmed'] = True
        
        if confirmed:
            # Check volume confirmation
            avg_volume = get_average_volume(candles[:-BREAKOUT_CONFIRMATION_CANDLES])
            confirmation_volume = np.mean([float(c['volume']) for c in candles_since_breakout])
            
            if confirmation_volume > avg_volume * 1.2:
                confidence += 0.1
                candidate.reasons['volume_confirmed'] = True
            
            # Clean up candidate
            del self.breakout_candidates[symbol]
            
            log(f"✅ {symbol}: Breakout confirmed after {len(candles_since_breakout)} candles")
            return True, candidate.direction, confidence, candidate.reasons
        
        # Check if breakout failed
        time_elapsed = (datetime.now() - candidate.initial_time).seconds / 60
        if time_elapsed > 15:  # 15 minutes timeout
            log(f"❌ {symbol}: Breakout candidate expired without confirmation")
            del self.breakout_candidates[symbol]
        
        return False, None, 0, {}
    
    def _find_key_levels(self, candles: List[Dict]) -> Tuple[Optional[float], Optional[float], Dict]:
        """Find key support and resistance levels"""
        if len(candles) < 20:
            return None, None, {}
            
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        # Method 1: Recent high/low
        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])
        
        # Method 2: Find levels with multiple touches
        price_levels = {}
        
        # Group prices into bins (0.1% ranges)
        for i, candle in enumerate(candles[-50:]):
            high = float(candle['high'])
            low = float(candle['low'])
            
            # Round to nearest 0.1%
            high_level = round(high / 0.001) * 0.001
            low_level = round(low / 0.001) * 0.001
            
            # Count touches
            for level in [high_level, low_level]:
                if level not in price_levels:
                    price_levels[level] = 0
                price_levels[level] += 1
        
        # Find most tested levels
        sorted_levels = sorted(price_levels.items(), key=lambda x: x[1], reverse=True)
        
        # Find strongest support and resistance from tested levels
        current_price = closes[-1]
        
        support_candidates = [level for level, count in sorted_levels if level < current_price and count >= MIN_TESTS_FOR_KEY_LEVEL]
        resistance_candidates = [level for level, count in sorted_levels if level > current_price and count >= MIN_TESTS_FOR_KEY_LEVEL]
        
        support = max(support_candidates) if support_candidates else recent_low
        resistance = min(resistance_candidates) if resistance_candidates else recent_high
        
        levels_data = {
            'support': support,
            'resistance': resistance,
            'range_size': resistance - support,
            'support_tests': price_levels.get(round(support / 0.001) * 0.001, 0),
            'resistance_tests': price_levels.get(round(resistance / 0.001) * 0.001, 0)
        }
        
        return support, resistance, levels_data
    
    def _detect_range_compression(self, candles: List[Dict], support: float, resistance: float) -> Tuple[bool, Dict]:
        """Detect if range is compressing (volatility squeeze)"""
        if len(candles) < 30:
            return False, {}
            
        # Calculate range size over time
        range_sizes = []
        
        for i in range(10, len(candles)):
            period_candles = candles[i-10:i]
            period_high = max(float(c['high']) for c in period_candles)
            period_low = min(float(c['low']) for c in period_candles)
            range_size = (period_high - period_low) / period_low * 100  # Percentage
            range_sizes.append(range_size)
        
        if len(range_sizes) < 10:
            return False, {}
            
        # Check if range is compressing
        recent_avg = np.mean(range_sizes[-5:])
        older_avg = np.mean(range_sizes[-20:-10])
        
        compression_pct = ((older_avg - recent_avg) / older_avg * 100) if older_avg > 0 else 0
        is_compressing = compression_pct > 20  # 20% compression
        
        compression_data = {
            'recent_range': recent_avg,
            'older_range': older_avg,
            'compression_pct': compression_pct,
            'current_range': resistance - support
        }
        
        return is_compressing, compression_data
    
    def _detect_failed_bounces(self, candles: List[Dict], support: float, resistance: float) -> Tuple[bool, str, Dict]:
        """Detect failed bounces from support/resistance"""
        if len(candles) < 10:
            return False, None, {}
            
        # Check last 10 candles for bounce attempts
        for i in range(-10, -1):
            candle = candles[i]
            high = float(candle['high'])
            low = float(candle['low'])
            close = float(candle['close'])
            open_price = float(candle['open'])
            
            # Check for failed bounce at resistance
            if high >= resistance * 0.998:  # Got close to resistance
                # Check if it was rejected (bearish close)
                if close < open_price and close < resistance * 0.995:
                    # Check subsequent candles for continuation down
                    if i < -2:
                        next_candles = candles[i+1:]
                        if all(float(c['close']) < resistance * 0.995 for c in next_candles):
                            bounce_data = {
                                'level': 'resistance',
                                'bounce_price': high,
                                'rejection_strength': (high - close) / high,
                                'weakness': 0.8
                            }
                            return True, "Short", bounce_data
                            
            # Check for failed bounce at support
            if low <= support * 1.002:  # Got close to support
                # Check if it was rejected (bullish close)
                if close > open_price and close > support * 1.005:
                    # Check subsequent candles for continuation up
                    if i < -2:
                        next_candles = candles[i+1:]
                        if all(float(c['close']) > support * 1.005 for c in next_candles):
                            bounce_data = {
                                'level': 'support',
                                'bounce_price': low,
                                'rejection_strength': (close - low) / low,
                                'weakness': 0.8
                            }
                            return True, "Long", bounce_data
                            
        return False, None, {}
    
    def _detect_momentum_shift(self, candles: List[Dict], regime: str) -> Tuple[bool, str, Dict]:
        """Detect momentum shifts that precede breaks"""
        if len(candles) < 20:
            return False, None, {}
            
        # Calculate momentum using price and volume
        closes = [float(c['close']) for c in candles[-20:]]
        volumes = [float(c['volume']) for c in candles[-20:]]
        
        # Price momentum
        price_momentum = (closes[-1] - closes[-10]) / closes[-10]
        
        # Volume momentum
        recent_vol = np.mean(volumes[-5:])
        older_vol = np.mean(volumes[-20:-10])
        vol_momentum = recent_vol / older_vol if older_vol > 0 else 1
        
        # RSI momentum
        rsi_data = calculate_rsi_with_bands(candles)
        rsi_momentum = 0
        if rsi_data and 'momentum' in rsi_data:
            rsi_momentum = rsi_data['momentum'] / 50  # Normalize
            
        # MACD momentum
        macd_momentum = get_macd_momentum(candles)
        
        # Combine momentum indicators
        total_momentum = (abs(price_momentum) * 0.3 + 
                         (vol_momentum - 1) * 0.3 + 
                         abs(rsi_momentum) * 0.2 + 
                         abs(macd_momentum) * 0.2)
        
        direction = "Long" if price_momentum > 0 else "Short"
        
        momentum_data = {
            'price_momentum': price_momentum,
            'volume_momentum': vol_momentum,
            'rsi_momentum': rsi_momentum,
            'macd_momentum': macd_momentum,
            'strength': total_momentum
        }
        
        # Momentum shift detected if strong enough
        is_shifting = total_momentum >= MOMENTUM_SHIFT_THRESHOLD
        
        return is_shifting, direction, momentum_data
    
    def _detect_volume_at_extremes(self, candles: List[Dict], support: float, resistance: float, 
                                  current_price: float) -> Tuple[bool, str, Dict]:
        """Detect volume building at range extremes"""
        if len(candles) < 20:
            return False, None, {}
            
        # Determine position in range
        range_size = resistance - support
        position = (current_price - support) / range_size if range_size > 0 else 0.5
        
        # Check if near extremes
        near_resistance = position > 0.8
        near_support = position < 0.2
        
        if not (near_resistance or near_support):
            return False, None, {}
            
        # Analyze volume at extremes
        recent_volumes = [float(c['volume']) for c in candles[-10:]]
        older_volumes = [float(c['volume']) for c in candles[-30:-10]]
        
        recent_avg = np.mean(recent_volumes)
        older_avg = np.mean(older_volumes)
        
        volume_increase = recent_avg / older_avg if older_avg > 0 else 1
        
        # Look for volume surge at extremes
        if volume_increase > VOLUME_SURGE_MULTIPLIER:
            direction = "Short" if near_resistance else "Long"
            
            vol_data = {
                'position': 'resistance' if near_resistance else 'support',
                'volume_increase': volume_increase,
                'recent_volume': recent_avg,
                'position_in_range': position
            }
            
            return True, direction, vol_data
            
        return False, None, {}
    
    def _check_level_tests(self, symbol: str, candles: List[Dict], support: float, resistance: float) -> Dict:
        """Track how many times levels have been tested"""
        
        # Initialize tracking for this symbol if needed
        if symbol not in self.level_tests:
            self.level_tests[symbol] = {
                'support_tests': 0,
                'resistance_tests': 0,
                'last_support_test': None,
                'last_resistance_test': None
            }
            
        tests = self.level_tests[symbol]
        
        # Count recent tests
        recent_support_tests = 0
        recent_resistance_tests = 0
        
        for candle in candles[-20:]:
            low = float(candle['low'])
            high = float(candle['high'])
            
            # Support test
            if low <= support * 1.002 and low >= support * 0.998:
                recent_support_tests += 1
                
            # Resistance test
            if high >= resistance * 0.998 and high <= resistance * 1.002:
                recent_resistance_tests += 1
        
        # Update tracking
        tests['support_tests'] = recent_support_tests
        tests['resistance_tests'] = recent_resistance_tests
        
        # Multiple tests indicate level strength and potential break
        multiple_tests = (recent_support_tests >= 3 or recent_resistance_tests >= 3)
        
        return {
            'multiple_tests': multiple_tests,
            'support_tests': recent_support_tests,
            'resistance_tests': recent_resistance_tests,
            'stronger_level': 'support' if recent_support_tests > recent_resistance_tests else 'resistance'
        }
    
    def _detect_pre_pump_signals(self, symbol: str, candles_by_tf: Dict) -> Tuple[bool, float, Dict]:
        """
        Detect pre-pump signals using multiple advanced indicators
        
        Returns:
            Tuple of (pump_imminent, confidence, reasons)
        """
        reasons = {}
        confidence = 0
        
        candles_5m = candles_by_tf.get('5', [])
        if candles_5m:
            avg_volume = get_average_volume(candles_5m)
            if avg_volume < 1000:  # Minimum volume threshold
                return False, 0, {}
        candles_15m = candles_by_tf.get('15', [])
        
        if not candles_5m or len(candles_5m) < 50:
            return False, 0, {}
        
        # 1. Stealth Accumulation Detection
        stealth_result = detect_stealth_accumulation_advanced(candles_5m, symbol)
        if stealth_result['detected'] and stealth_result['strength'] > 0.7:
            confidence += 0.25
            reasons['stealth_accumulation'] = stealth_result
            log(f"🕵️ {symbol}: Stealth accumulation detected - patterns: {stealth_result['patterns']}")
            
        # 2. Smart Money Analysis
        smart_money_signal, smart_data = self._detect_smart_money_accumulation(candles_5m, candles_15m)
        if smart_money_signal:
            confidence += 0.3
            reasons['smart_money'] = smart_data
            log(f"🐋 {symbol}: Smart money accumulation - strength: {smart_data['strength']:.2f}")
            
        # 3. Accumulation Zone Analysis
        in_accumulation, accum_data = self._analyze_accumulation_zone(symbol, candles_5m)
        if in_accumulation:
            confidence += 0.2
            reasons['accumulation_zone'] = accum_data
            
        # 4. Volume Pattern Analysis for Pumps
        pump_volume_pattern, vol_data = self._detect_pump_volume_pattern(candles_5m)
        if pump_volume_pattern:
            confidence += 0.25
            reasons['pump_volume_pattern'] = vol_data
            
        # 5. Technical Setup for Pumps
        technical_ready, tech_data = self._check_pump_technical_setup(candles_by_tf)
        if technical_ready:
            confidence += 0.2
            reasons['technical_setup'] = tech_data
            
        # 6. Whale Activity Analysis
        whale_data = self._analyze_whale_activity_for_pumps(candles_5m, symbol)
        if whale_data['signal']:
            confidence += 0.25
            reasons['whale_activity'] = whale_data
            
        # 7. Social Volume Spike (unusual small trades)
        social_spike, social_data = self._detect_social_volume_spike(candles_5m)
        if social_spike:
            confidence += 0.15
            reasons['social_volume'] = social_data
            
        # 8. Check for pump-specific patterns
        pump_pattern, pattern_data = self._detect_pump_patterns(candles_5m)
        if pump_pattern:
            confidence += 0.2
            reasons['pump_pattern'] = pattern_data
            
        # Require minimum confidence for pump signal
        min_required_signals = 4  # Increase from implicit 2-3
        if len(reasons) < min_required_signals:
            return False, 0, {}
    
        pump_imminent = confidence >= 0.85 and len(reasons) >= min_required_signals
        
        if pump_imminent:
            log(f"🚀 {symbol}: Pre-pump signals detected! Confidence: {confidence:.2f}")
            log(f"   Indicators: {list(reasons.keys())}")
            
        return pump_imminent, confidence, reasons
    
    def _detect_smart_money_accumulation(self, candles_5m: List[Dict], 
                                       candles_15m: List[Dict]) -> Tuple[bool, Dict]:
        """Detect smart money accumulation patterns"""
        if len(candles_5m) < 30:
            return False, {}
            
        # Analyze order flow patterns
        large_orders = 0
        small_orders = 0
        accumulation_score = 0
        
        for i in range(-30, -1):
            candle = candles_5m[i]
            volume = float(candle['volume'])
            close = float(candle['close'])
            open_price = float(candle['open'])
            high = float(candle['high'])
            low = float(candle['low'])
            
            # Estimate order size based on volume and price action
            range_size = high - low
            body_size = abs(close - open_price)
            
            if range_size > 0:
                # Large volume with small range = accumulation
                if volume > get_average_volume(candles_5m) * 1.5 and body_size / range_size < 0.3:
                    large_orders += 1
                    accumulation_score += 0.3
                    
                # Bullish close with volume
                if close > open_price and volume > get_average_volume(candles_5m):
                    accumulation_score += 0.1
                    
        # Check 15m timeframe for confirmation
        if candles_15m and len(candles_15m) >= 10:
            # Look for higher lows on 15m
            lows_15m = [float(c['low']) for c in candles_15m[-10:]]
            if all(lows_15m[i] <= lows_15m[i+1] for i in range(len(lows_15m)-1)):
                accumulation_score += 0.5
                
        smart_data = {
            'large_orders': large_orders,
            'accumulation_score': accumulation_score,
            'strength': min(accumulation_score / 3, 1.0)  # Normalize to 0-1
        }
        
        return accumulation_score >= 2.0, smart_data
    
    def _analyze_accumulation_zone(self, symbol: str, candles: List[Dict]) -> Tuple[bool, Dict]:
        """Track and analyze accumulation zones"""
        if symbol not in self.accumulation_zones:
            self.accumulation_zones[symbol] = {
                'start_price': None,
                'touches': 0,
                'volume_total': 0,
                'start_time': None
            }
            
        zone = self.accumulation_zones[symbol]
        current_price = float(candles[-1]['close'])
        
        # Find recent support level
        lows = [float(c['low']) for c in candles[-20:]]
        support = min(lows)
        
        # Check if we're in accumulation zone (within 2% of support)
        if current_price <= support * 1.02:
            if zone['start_price'] is None:
                zone['start_price'] = current_price
                zone['start_time'] = datetime.now()
                
            zone['touches'] += 1
            zone['volume_total'] += float(candles[-1]['volume'])
            
            # Accumulation confirmed after multiple touches with volume
            if zone['touches'] >= 3:
                time_in_zone = (datetime.now() - zone['start_time']).seconds / 3600  # hours
                
                accum_data = {
                    'touches': zone['touches'],
                    'time_hours': time_in_zone,
                    'avg_volume': zone['volume_total'] / zone['touches'],
                    'support_level': support
                }
                
                return True, accum_data
        else:
            # Reset if price moves away from zone
            if zone['start_price'] and current_price > zone['start_price'] * 1.03:
                zone['start_price'] = None
                zone['touches'] = 0
                zone['volume_total'] = 0
                
        return False, {}
    
    def _detect_pump_volume_pattern(self, candles: List[Dict]) -> Tuple[bool, Dict]:
        """Detect volume patterns that precede pumps"""
        if len(candles) < 20:
            return False, {}
            
        volumes = [float(c['volume']) for c in candles[-20:]]
        avg_volume = np.mean(volumes)
        
        # Pattern 1: Gradual volume increase
        volume_trend = np.polyfit(range(20), volumes, 1)[0]
        volume_increasing = volume_trend > avg_volume * 0.05  # 5% increase per candle
        
        # Pattern 2: Volume spikes with pullbacks
        spike_count = 0
        for i in range(len(volumes)-1):
            if volumes[i] > avg_volume * 2 and volumes[i+1] < volumes[i] * 0.7:
                spike_count += 1
                
        # Pattern 3: Consistent above-average volume
        above_avg_count = sum(1 for v in volumes[-10:] if v > avg_volume)
        
        vol_data = {
            'volume_trend': volume_trend / avg_volume if avg_volume > 0 else 0,
            'spike_count': spike_count,
            'above_avg_ratio': above_avg_count / 10,
            'pattern_detected': False
        }
        
        # Pump likely if we see volume patterns
        if volume_increasing and above_avg_count >= 7:
            vol_data['pattern_detected'] = True
            vol_data['pattern_type'] = 'gradual_accumulation'
            return True, vol_data
            
        elif spike_count >= 2 and above_avg_count >= 5:
            vol_data['pattern_detected'] = True
            vol_data['pattern_type'] = 'spike_accumulation'
            return True, vol_data
            
        return False, vol_data
    
    def _check_pump_technical_setup(self, candles_by_tf: Dict) -> Tuple[bool, Dict]:
        """Check if technical indicators are aligned for a pump"""
        score = 0
        tech_data = {}
        
        # Check multiple timeframes
        for tf in ['5', '15', '30']:
            if tf not in candles_by_tf or len(candles_by_tf[tf]) < 30:
                continue
                
            candles = candles_by_tf[tf]
            
            # 1. EMA alignment
            ema_20 = calculate_ema(candles, 20)
            ema_50 = calculate_ema(candles, 50)
            
            if ema_20 and ema_50 and len(ema_20) > 0 and len(ema_50) > 0:
                if ema_20[-1] > ema_50[-1]:
                    score += 1
                    tech_data[f'ema_aligned_{tf}'] = True
                    
            # 2. RSI not overbought
            rsi_data = calculate_rsi_with_bands(candles)
            if rsi_data and 40 < rsi_data['rsi'] < 65:
                score += 1
                tech_data[f'rsi_favorable_{tf}'] = rsi_data['rsi']
                
            # 3. MACD momentum
            macd_momentum = get_macd_momentum(candles)
            if macd_momentum > 0.3:
                score += 1
                tech_data[f'macd_momentum_{tf}'] = macd_momentum
                
        tech_data['score'] = score
        tech_data['aligned'] = score >= 4  # Need 4+ positive signals
        
        return tech_data['aligned'], tech_data
    
    def _analyze_whale_activity_for_pumps(self, candles: List[Dict], symbol: str) -> Dict:
        """Analyze whale activity specifically for pump detection"""
        whale_result = detect_whale_activity_advanced(candles, symbol)
        whale_stats = get_whale_statistics(symbol)
        
        whale_data = {
            'signal': False,
            'type': None,
            'strength': 0
        }
        
        if whale_result['detected']:
            # Look for accumulation patterns
            if whale_result['recommendation'] == 'potential_long':
                whale_data['signal'] = True
                whale_data['type'] = 'accumulation'
                whale_data['strength'] = whale_result['strength']
                
            # Check whale statistics for patterns
            if whale_stats['status'] == 'active':
                if whale_stats.get('most_common') == 'accumulation':
                    whale_data['signal'] = True
                    whale_data['accumulation_events'] = whale_stats['total_events']
                    
        return whale_data
    
    def _detect_social_volume_spike(self, candles: List[Dict]) -> Tuple[bool, Dict]:
        """Detect unusual small order activity (retail FOMO building)"""
        if len(candles) < 20:
            return False, {}
            
        # Analyze trade patterns
        small_trade_increase = 0
        
        for i in range(-10, -1):
            candle = candles[i]
            volume = float(candle['volume'])
            price_range = float(candle['high']) - float(candle['low'])
            
            # High volume with tight range = many small trades
            if volume > 0 and price_range > 0:
                trade_density = volume / price_range
                avg_density = np.mean([float(c['volume']) / (float(c['high']) - float(c['low'])) 
                                     for c in candles[-20:-10] 
                                     if float(c['high']) > float(c['low'])])
                
                if trade_density > avg_density * 1.5:
                    small_trade_increase += 1
                    
        social_data = {
            'small_trade_spikes': small_trade_increase,
            'fomo_building': small_trade_increase >= 3
        }
        
        return social_data['fomo_building'], social_data
    
    def _detect_pump_patterns(self, candles: List[Dict]) -> Tuple[bool, Dict]:
        """Detect specific candlestick patterns that often precede pumps"""
        pattern = detect_pattern(candles)
        
        pump_patterns = [
            'hammer', 'bullish_engulfing', 'morning_star', 
            'three_white_soldiers', 'bullish_kicker', 'marubozu'
        ]
        
        if pattern in pump_patterns:
            pattern_strength = analyze_pattern_strength(pattern, candles)
            
            pattern_data = {
                'pattern': pattern,
                'strength': pattern_strength,
                'type': 'bullish_reversal' if pattern in ['hammer', 'morning_star'] else 'bullish_continuation'
            }
            
            return pattern_strength > 0.7, pattern_data
            
        return False, {}
    
    def get_pump_success_rate(self, symbol: str = None) -> Dict:
        """Track and return pump prediction success rate"""
        if symbol and symbol in self.pump_history:
            history = self.pump_history[symbol]
            total = len(history)
            successful = sum(1 for h in history if h['successful'])
            
            return {
                'symbol': symbol,
                'total_predictions': total,
                'successful': successful,
                'success_rate': successful / total if total > 0 else 0
            }
        
        # Overall statistics
        all_predictions = []
        for sym_history in self.pump_history.values():
            all_predictions.extend(sym_history)
            
        total = len(all_predictions)
        successful = sum(1 for p in all_predictions if p['successful'])
        
        return {
            'total_predictions': total,
            'successful': successful,
            'success_rate': successful / total if total > 0 else 0
        }

# Global instance
range_break_detector = RangeBreakDetector()
