# range_breakout_strategy.py - Enhanced Range Breakout Strategy with Pre-Breakout Detection

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from logger import log
from volume import get_average_volume, is_volume_spike, detect_volume_climax, analyze_volume_trend
from stealth_detector import detect_volume_divergence, detect_stealth_accumulation_advanced
from bollinger import calculate_bollinger_bands_advanced, detect_bollinger_squeeze
from atr import calculate_atr
from pattern_detector import detect_pattern, analyze_pattern_strength
from rsi import calculate_rsi_with_bands
from ema import calculate_ema, get_ema_slope

# Configuration constants
LOOKBACK_PERIOD = 50
RANGE_THRESHOLD = 0.02  # 2% range to consider as consolidation
BREAKOUT_MULTIPLIER = 1.5  # Volume multiplier for breakout confirmation
MIN_TOUCHES = 2  # Minimum touches to confirm support/resistance
COMPRESSION_THRESHOLD = 0.5  # 50% compression from initial range
PRE_BREAKOUT_THRESHOLD = 0.8  # 80% confidence for pre-breakout signal
MIN_BODY_SIZE_PCT = 0.5  # Minimum candle body size as % of price for breakout

class RangeBreakoutStrategy:
    """Enhanced range breakout strategy with pre-breakout detection"""
    
    def __init__(self):
        self.compression_history = {}
        self.breakout_candidates = {}
        self.failed_breakouts = {}
        
    def detect_range_breakout(self, symbol: str, candles: List[Dict], 
                            timeframe: str = "5") -> Tuple[bool, Optional[str], float, Dict]:
        """
        Enhanced range breakout detection with pre-breakout signals
        
        Returns:
            Tuple of (breakout_detected, direction, confidence, details)
        """
        if len(candles) < LOOKBACK_PERIOD:
            return False, None, 0, {}
            
        # Find range boundaries
        range_data = self._identify_range(candles)
        if not range_data['is_ranging']:
            return False, None, 0, {}
            
        high_boundary = range_data['resistance']
        low_boundary = range_data['support']
        current_price = float(candles[-1]['close'])
        
        details = {
            'range_high': high_boundary,
            'range_low': low_boundary,
            'range_width_pct': ((high_boundary - low_boundary) / low_boundary) * 100,
            'touches_high': range_data['resistance_touches'],
            'touches_low': range_data['support_touches']
        }
        
        # Check for pre-breakout conditions
        pre_breakout, pre_direction, pre_confidence = self._detect_pre_breakout_conditions(
            symbol, candles, high_boundary, low_boundary
        )
        
        if pre_breakout:
            details['pre_breakout'] = True
            details['pre_breakout_confidence'] = pre_confidence
            
            # If pre-breakout confidence is high enough, signal early entry
            if pre_confidence >= PRE_BREAKOUT_THRESHOLD:
                log(f"🎯 {symbol}: Pre-breakout signal detected! Direction: {pre_direction}, Confidence: {pre_confidence:.2f}")
                return True, pre_direction, pre_confidence, details
        
        # Check for actual breakout with enhanced validation
        breakout, direction, breakout_confidence = self._check_breakout_with_validation(
            candles, high_boundary, low_boundary, current_price
        )
        
        if breakout:
            # Additional false breakout filters
            if self._is_false_breakout(symbol, candles, direction, high_boundary, low_boundary):
                log(f"⚠️ {symbol}: Potential false breakout detected, ignoring signal")
                self.failed_breakouts[symbol] = {
                    'time': datetime.now(),
                    'direction': direction,
                    'level': high_boundary if direction == "Long" else low_boundary
                }
                return False, None, 0, details
                
            # Calculate final confidence
            final_confidence = self._calculate_breakout_confidence(
                breakout_confidence, pre_confidence, candles, direction
            )
            
            details['breakout_type'] = 'confirmed'
            details['volume_confirmation'] = self._check_volume_confirmation(candles)
            
            log(f"✅ {symbol}: Range breakout confirmed! Direction: {direction}, Confidence: {final_confidence:.2f}")
            return True, direction, final_confidence, details
            
        return False, None, 0, details
    
    def _detect_pre_breakout_conditions(self, symbol: str, candles: List[Dict], 
                                      resistance: float, support: float) -> Tuple[bool, Optional[str], float]:
        """Detect conditions that signal an imminent breakout"""
        confidence = 0
        direction = None
        signals = []
        
        # 1. Check for volume divergence
        if detect_volume_divergence(candles[-20:]):
            confidence += 0.25
            signals.append("volume_divergence")
            # Volume divergence often precedes upward breakouts
            direction = "Long"
        
        # 2. Check for stealth accumulation
        stealth_result = detect_stealth_accumulation_advanced(candles[-30:], symbol)
        if stealth_result['detected']:
            strength = stealth_result['strength']
            confidence += 0.3 * strength
            signals.append(f"stealth_{stealth_result['recommendation']}")
            
            if stealth_result['recommendation'] in ['strong_accumulation', 'moderate_accumulation']:
                direction = "Long"
            elif 'distribution' in stealth_result.get('patterns', []):
                direction = "Short"
        
        # 3. Check for range compression
        compression_data = self._detect_range_compression(symbol, candles, resistance, support)
        if compression_data['is_compressing']:
            confidence += 0.25
            signals.append("range_compression")
            
            # Compression direction bias
            if compression_data.get('bias'):
                if not direction:
                    direction = compression_data['bias']
                elif direction == compression_data['bias']:
                    confidence += 0.1
        
        # 4. Check Bollinger Band squeeze
        bb_data = calculate_bollinger_bands_advanced(candles)
        if bb_data:
            squeeze_info = detect_bollinger_squeeze(bb_data)
            if squeeze_info['squeeze']:
                confidence += 0.2 * squeeze_info['intensity']
                signals.append("bb_squeeze")
        
        # 5. Check for momentum building
        momentum_data = self._detect_momentum_buildup(candles, resistance, support)
        if momentum_data['building']:
            confidence += 0.2
            signals.append("momentum_buildup")
            if not direction:
                direction = momentum_data['direction']
        
        # 6. Check RSI coiling
        rsi_data = calculate_rsi_with_bands(candles)
        if rsi_data:
            rsi = rsi_data['rsi']
            if 45 <= rsi <= 55:  # RSI in neutral zone during range
                confidence += 0.15
                signals.append("rsi_coiling")
        
        # Store compression data for later reference
        if confidence > 0.5:
            self.compression_history[symbol] = {
                'time': datetime.now(),
                'confidence': confidence,
                'direction': direction,
                'signals': signals
            }
        
        has_pre_breakout = confidence >= 0.6 and direction is not None
        
        if has_pre_breakout:
            log(f"📊 {symbol}: Pre-breakout conditions detected - Signals: {signals}")
        
        return has_pre_breakout, direction, min(confidence, 1.0)
    
    def _detect_range_compression(self, symbol: str, candles: List[Dict], 
                                resistance: float, support: float) -> Dict:
        """Detect if range is compressing (coiling for breakout)"""
        if len(candles) < 30:
            return {'is_compressing': False}
            
        # Calculate range over time
        range_history = []
        for i in range(10, len(candles), 5):
            period_candles = candles[i-10:i]
            period_high = max(float(c['high']) for c in period_candles)
            period_low = min(float(c['low']) for c in period_candles)
            period_range = period_high - period_low
            range_history.append(period_range)
        
        if len(range_history) < 3:
            return {'is_compressing': False}
        
        # Check if range is decreasing
        initial_range = range_history[0]
        current_range = range_history[-1]
        compression_ratio = current_range / initial_range if initial_range > 0 else 1
        
        is_compressing = compression_ratio < COMPRESSION_THRESHOLD
        
        # Determine bias based on price position
        current_price = float(candles[-1]['close'])
        position_in_range = (current_price - support) / (resistance - support) if (resistance - support) > 0 else 0.5
        
        bias = None
        if is_compressing:
            if position_in_range > 0.6:
                bias = "Long"  # Price in upper part of range
            elif position_in_range < 0.4:
                bias = "Short"  # Price in lower part of range
        
        # Check ATR compression as additional confirmation
        atr_short = calculate_atr(candles[-10:], period=7)
        atr_long = calculate_atr(candles[-30:], period=14)
        
        atr_compressing = False
        if atr_short and atr_long:
            atr_compressing = atr_short < atr_long * 0.7
        
        return {
            'is_compressing': is_compressing,
            'compression_ratio': compression_ratio,
            'position_in_range': position_in_range,
            'bias': bias,
            'atr_compressing': atr_compressing,
            'range_history': range_history
        }
    
    def _detect_momentum_buildup(self, candles: List[Dict], resistance: float, 
                               support: float) -> Dict:
        """Detect if momentum is building before breakout"""
        if len(candles) < 20:
            return {'building': False}
            
        # Check volume trend
        volume_trend = analyze_volume_trend(candles[-20:])
        volume_increasing = volume_trend.get('trend') == 'increasing'
        
        # Check price action near boundaries
        recent_candles = candles[-10:]
        touches_resistance = 0
        touches_support = 0
        
        for candle in recent_candles:
            high = float(candle['high'])
            low = float(candle['low'])
            
            if high >= resistance * 0.99:
                touches_resistance += 1
            if low <= support * 1.01:
                touches_support += 1
        
        # Higher lows or lower highs pattern
        lows = [float(c['low']) for c in recent_candles]
        highs = [float(c['high']) for c in recent_candles]
        
        higher_lows = all(lows[i] >= lows[i-1] * 0.999 for i in range(1, len(lows)))
        lower_highs = all(highs[i] <= highs[i-1] * 1.001 for i in range(1, len(highs)))
        
        # Determine direction and if momentum is building
        direction = None
        building = False
        
        if touches_resistance > touches_support and volume_increasing:
            direction = "Long"
            building = True
        elif touches_support > touches_resistance and volume_increasing:
            direction = "Short"
            building = True
        elif higher_lows and volume_increasing:
            direction = "Long"
            building = True
        elif lower_highs and volume_increasing:
            direction = "Short"
            building = True
        
        return {
            'building': building,
            'direction': direction,
            'volume_increasing': volume_increasing,
            'touches_resistance': touches_resistance,
            'touches_support': touches_support,
            'higher_lows': higher_lows,
            'lower_highs': lower_highs
        }
    
    def _check_breakout_with_validation(self, candles: List[Dict], resistance: float, 
                                      support: float, current_price: float) -> Tuple[bool, Optional[str], float]:
        """Check for breakout with enhanced validation"""
        if len(candles) < 2:
            return False, None, 0
            
        last_candle = candles[-1]
        prev_candle = candles[-2]
        
        close = float(last_candle['close'])
        open_price = float(last_candle['open'])
        high = float(last_candle['high'])
        low = float(last_candle['low'])
        volume = float(last_candle['volume'])
        
        # Calculate candle metrics
        body_size = abs(close - open_price)
        body_size_pct = (body_size / open_price) * 100
        total_range = high - low
        
        # Check minimum body size requirement
        if body_size_pct < MIN_BODY_SIZE_PCT:
            return False, None, 0
        
        # Get average volume
        avg_volume = get_average_volume(candles[:-1])
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1
        
        breakout = False
        direction = None
        confidence = 0
        
        # Check for resistance breakout
        if close > resistance and close > open_price:
            # Additional validation
            if (prev_candle and float(prev_candle['close']) < resistance and
                volume_ratio >= BREAKOUT_MULTIPLIER):
                breakout = True
                direction = "Long"
                confidence = 0.7
                
                # Strong breakout indicators
                if close > resistance * 1.01:  # 1% above resistance
                    confidence += 0.15
                if body_size / total_range > 0.7:  # Strong bullish candle
                    confidence += 0.1
                if volume_ratio > 2.0:  # Very high volume
                    confidence += 0.05
        
        # Check for support breakdown
        elif close < support and close < open_price:
            # Additional validation
            if (prev_candle and float(prev_candle['close']) > support and
                volume_ratio >= BREAKOUT_MULTIPLIER):
                breakout = True
                direction = "Short"
                confidence = 0.7
                
                # Strong breakdown indicators
                if close < support * 0.99:  # 1% below support
                    confidence += 0.15
                if body_size / total_range > 0.7:  # Strong bearish candle
                    confidence += 0.1
                if volume_ratio > 2.0:  # Very high volume
                    confidence += 0.05
        
        return breakout, direction, min(confidence, 1.0)
    
    def _is_false_breakout(self, symbol: str, candles: List[Dict], direction: str,
                         resistance: float, support: float) -> bool:
        """Enhanced false breakout detection"""
        if len(candles) < 5:
            return False
            
        # Check if we've had recent failed breakouts
        if symbol in self.failed_breakouts:
            failed_data = self.failed_breakouts[symbol]
            time_since_failure = (datetime.now() - failed_data['time']).seconds / 60
            
            # If same direction failed recently, be cautious
            if time_since_failure < 30 and failed_data['direction'] == direction:
                return True
        
        last_candle = candles[-1]
        
        # Check for long wicks (potential rejection)
        high = float(last_candle['high'])
        low = float(last_candle['low'])
        close = float(last_candle['close'])
        open_price = float(last_candle['open'])
        
        body_size = abs(close - open_price)
        total_range = high - low
        
        if total_range > 0:
            if direction == "Long":
                upper_wick = high - max(close, open_price)
                wick_ratio = upper_wick / total_range
                
                # Large upper wick suggests rejection
                if wick_ratio > 0.6:
                    return True
                    
            else:  # Short
                lower_wick = min(close, open_price) - low
                wick_ratio = lower_wick / total_range
                
                # Large lower wick suggests rejection
                if wick_ratio > 0.6:
                    return True
        
        # Check if breakout is happening during low volume period
        recent_volumes = [float(c['volume']) for c in candles[-20:]]
        current_volume = float(last_candle['volume'])
        volume_percentile = sum(v < current_volume for v in recent_volumes) / len(recent_volumes)
        
        if volume_percentile < 0.3:  # Volume in bottom 30%
            return True
        
        # Check for immediate reversal pattern
        if len(candles) >= 3:
            # Look for reversal in next candle after breakout
            if direction == "Long" and close < resistance:
                return True
            elif direction == "Short" and close > support:
                return True
        
        return False
    
    def _check_volume_confirmation(self, candles: List[Dict]) -> Dict:
        """Check various volume confirmations"""
        if len(candles) < 20:
            return {}
            
        current_volume = float(candles[-1]['volume'])
        avg_volume = get_average_volume(candles[:-1])
        
        # Volume analysis
        volume_spike = is_volume_spike(candles, multiplier=BREAKOUT_MULTIPLIER)
        climax, climax_type = detect_volume_climax(candles)
        volume_trend = analyze_volume_trend(candles[-10:])
        
        return {
            'volume_ratio': current_volume / avg_volume if avg_volume > 0 else 1,
            'is_spike': volume_spike,
            'is_climax': climax,
            'climax_type': climax_type,
            'trend': volume_trend.get('trend', 'neutral'),
            'momentum': volume_trend.get('momentum', 1.0)
        }
    
    def _calculate_breakout_confidence(self, breakout_confidence: float, 
                                     pre_confidence: float, candles: List[Dict], 
                                     direction: str) -> float:
        """Calculate final breakout confidence score"""
        final_confidence = breakout_confidence
        
        # Boost confidence if we had pre-breakout signals
        if pre_confidence > 0:
            final_confidence = min(final_confidence + (pre_confidence * 0.3), 1.0)
        
        # Check for pattern confirmation
        pattern = detect_pattern(candles)
        if pattern:
            pattern_strength = analyze_pattern_strength(pattern, candles)
            from pattern_detector import get_pattern_direction
            pattern_dir = get_pattern_direction(pattern)
            
            if (pattern_dir == "bullish" and direction == "Long") or \
               (pattern_dir == "bearish" and direction == "Short"):
                final_confidence = min(final_confidence + (pattern_strength * 0.2), 1.0)
        
        # Check momentum indicators
        ema_9 = calculate_ema(candles, period=9)
        ema_21 = calculate_ema(candles, period=21)
        
        if ema_9 and ema_21 and len(ema_9) > 0 and len(ema_21) > 0:
            if direction == "Long" and ema_9[-1] > ema_21[-1]:
                final_confidence = min(final_confidence + 0.1, 1.0)
            elif direction == "Short" and ema_9[-1] < ema_21[-1]:
                final_confidence = min(final_confidence + 0.1, 1.0)
        
        return final_confidence
    
    def _identify_range(self, candles: List[Dict]) -> Dict:
        """Identify if price is in a range and find boundaries"""
        if len(candles) < LOOKBACK_PERIOD:
            return {'is_ranging': False}
            
        # Get price data
        highs = [float(c['high']) for c in candles[-LOOKBACK_PERIOD:]]
        lows = [float(c['low']) for c in candles[-LOOKBACK_PERIOD:]]
        closes = [float(c['close']) for c in candles[-LOOKBACK_PERIOD:]]
        
        # Calculate range
        range_high = max(highs)
        range_low = min(lows)
        range_size = (range_high - range_low) / range_low
        
        # Check if range is tight enough
        if range_size > RANGE_THRESHOLD:
            return {'is_ranging': False}
        
        # Find support and resistance levels with multiple touches
        resistance_touches = 0
        support_touches = 0
        
        for i, candle in enumerate(candles[-LOOKBACK_PERIOD:]):
            high = float(candle['high'])
            low = float(candle['low'])
            
            # Count touches of resistance
            if high >= range_high * 0.99:
                resistance_touches += 1
                
            # Count touches of support
            if low <= range_low * 1.01:
                support_touches += 1
        
        # Require minimum touches to confirm range
        is_ranging = (resistance_touches >= MIN_TOUCHES and 
                     support_touches >= MIN_TOUCHES)
        
        return {
            'is_ranging': is_ranging,
            'resistance': range_high,
            'support': range_low,
            'range_size': range_size,
            'resistance_touches': resistance_touches,
            'support_touches': support_touches
        }

# Global instance
range_breakout_strategy = RangeBreakoutStrategy()

# Convenience function for backward compatibility
def detect_range_breakout(candles: List[Dict], timeframe: str = "5") -> bool:
    """Backward compatible function that returns simple True/False"""
    breakout, _, _, _ = range_breakout_strategy.detect_range_breakout("", candles, timeframe)
    return breakout
