# range_breakout_strategy.py - Enhanced Range Breakout Strategy with Full Integration

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
VOLUME_TIGHTENING_LOOKBACK = 20  # Candles to check for volume tightening
VOLUME_TIGHTENING_THRESHOLD = 0.7  # 70% reduction for tightening signal

class RangeBreakoutStrategy:
    """Enhanced range breakout strategy with stealth accumulation, trend alignment, and volume tightening"""
    
    def __init__(self):
        self.compression_history = {}
        self.breakout_candidates = {}
        self.failed_breakouts = {}
        self.stealth_activity = {}
        self.volume_tightening_history = {}
        
    def detect_range_breakout(self, symbol: str, candles: List[Dict], 
                            timeframe: str = "5", trend_context: Dict = None) -> Tuple[bool, Optional[str], float, Dict]:
        """
        Enhanced range breakout detection with full integration
        
        Args:
            symbol: Trading symbol
            candles: List of candle data
            timeframe: Timeframe for analysis
            trend_context: Market trend context (btc_trend, regime, etc.)
            
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
        
        # 1. Check stealth accumulation patterns
        stealth_score, stealth_direction = self._analyze_stealth_accumulation(
            symbol, candles, high_boundary, low_boundary
        )
        details['stealth_score'] = stealth_score
        details['stealth_direction'] = stealth_direction
        
        # 2. Check trend alignment
        trend_score, trend_bias = self._check_trend_alignment(
            candles, trend_context, stealth_direction
        )
        details['trend_score'] = trend_score
        details['trend_bias'] = trend_bias
        
        # 3. Check volume tightening patterns
        volume_tightening_data = self._detect_volume_tightening(
            symbol, candles, high_boundary, low_boundary
        )
        details['volume_tightening'] = volume_tightening_data
        
        # 4. Check for pre-breakout conditions with all factors
        pre_breakout, pre_direction, pre_confidence = self._detect_enhanced_pre_breakout(
            symbol, candles, high_boundary, low_boundary,
            stealth_score, stealth_direction, trend_score, trend_bias,
            volume_tightening_data
        )
        
        if pre_breakout:
            details['pre_breakout'] = True
            details['pre_breakout_confidence'] = pre_confidence
            details['pre_breakout_direction'] = pre_direction
            
            # If pre-breakout confidence is high enough, signal early entry
            if pre_confidence >= PRE_BREAKOUT_THRESHOLD:
                log(f"🎯 {symbol}: Pre-breakout signal detected! Direction: {pre_direction}, Confidence: {pre_confidence:.2f}")
                return True, pre_direction, pre_confidence, details
        
        # 5. Check for actual breakout with enhanced validation
        breakout, direction, breakout_confidence = self._check_breakout_with_validation(
            candles, high_boundary, low_boundary, current_price
        )
        
        if breakout:
            # Additional validation with integrated factors
            if self._validate_breakout_with_context(
                symbol, candles, direction, high_boundary, low_boundary,
                stealth_score, trend_score, volume_tightening_data
            ):
                # Calculate final confidence incorporating all factors
                final_confidence = self._calculate_integrated_confidence(
                    breakout_confidence, pre_confidence, stealth_score,
                    trend_score, volume_tightening_data, candles, direction
                )
                
                details['breakout_type'] = 'confirmed'
                details['volume_confirmation'] = self._check_volume_confirmation(candles)
                details['integrated_factors'] = {
                    'stealth': stealth_score,
                    'trend': trend_score,
                    'volume_tightening': volume_tightening_data['score']
                }
                
                log(f"✅ {symbol}: Range breakout confirmed! Direction: {direction}, Confidence: {final_confidence:.2f}")
                return True, direction, final_confidence, details
            else:
                log(f"⚠️ {symbol}: Breakout failed validation checks")
                self.failed_breakouts[symbol] = {
                    'time': datetime.now(),
                    'direction': direction,
                    'level': high_boundary if direction == "Long" else low_boundary
                }
                return False, None, 0, details
            
        return False, None, 0, details
    
    def _analyze_stealth_accumulation(self, symbol: str, candles: List[Dict],
                                    resistance: float, support: float) -> Tuple[float, Optional[str]]:
        """Enhanced stealth accumulation analysis for range breakouts"""
        # Get stealth detection results
        stealth_result = detect_stealth_accumulation_advanced(candles[-30:], symbol)
        
        score = 0
        direction = None
        
        if stealth_result['detected']:
            base_score = stealth_result['strength'] * 0.4
            
            # Adjust score based on recommendation type
            if stealth_result['recommendation'] == 'strong_accumulation':
                score = base_score * 1.5
                direction = "Long"
            elif stealth_result['recommendation'] == 'moderate_accumulation':
                score = base_score * 1.2
                direction = "Long"
            elif 'distribution' in stealth_result.get('patterns', []):
                score = base_score * 1.2
                direction = "Short"
            
            # Check where accumulation is happening relative to range
            if direction == "Long":
                # Accumulation near support is stronger signal
                current_price = float(candles[-1]['close'])
                position_in_range = (current_price - support) / (resistance - support)
                if position_in_range < 0.4:  # Lower 40% of range
                    score *= 1.3
            elif direction == "Short":
                # Distribution near resistance is stronger signal
                current_price = float(candles[-1]['close'])
                position_in_range = (current_price - support) / (resistance - support)
                if position_in_range > 0.6:  # Upper 40% of range
                    score *= 1.3
        
        # Store stealth activity for this symbol
        if score > 0:
            self.stealth_activity[symbol] = {
                'time': datetime.now(),
                'score': score,
                'direction': direction,
                'patterns': stealth_result.get('patterns', [])
            }
            
            log(f"🕵️ {symbol}: Stealth activity detected - Score: {score:.2f}, Direction: {direction}")
        
        return min(score, 1.0), direction
    
    def _check_trend_alignment(self, candles: List[Dict], trend_context: Dict,
                             stealth_direction: Optional[str]) -> Tuple[float, Optional[str]]:
        """Check alignment with market trends"""
        score = 0
        bias = None
        
        if not trend_context:
            return 0.5, None  # Neutral if no context
        
        # 1. Check BTC trend alignment
        btc_trend = trend_context.get('btc_trend', 'ranging')
        regime = trend_context.get('regime', 'trending')
        
        # Calculate local trend
        ema_9 = calculate_ema(candles, period=9)
        ema_21 = calculate_ema(candles, period=21)
        
        local_trend = None
        if ema_9 and ema_21 and len(ema_9) > 0 and len(ema_21) > 0:
            ema_9_slope = get_ema_slope(ema_9[-10:]) if len(ema_9) >= 10 else 0
            ema_21_slope = get_ema_slope(ema_21[-10:]) if len(ema_21) >= 10 else 0
            
            if ema_9[-1] > ema_21[-1] and ema_9_slope > 0:
                local_trend = "up"
            elif ema_9[-1] < ema_21[-1] and ema_9_slope < 0:
                local_trend = "down"
            else:
                local_trend = "neutral"
        
        # 2. Score based on alignment
        if btc_trend == "uptrend":
            if local_trend == "up":
                score = 0.8
                bias = "Long"
            elif local_trend == "neutral":
                score = 0.6
                bias = "Long"
            else:
                score = 0.3  # Counter-trend
                bias = "Short"
        elif btc_trend == "downtrend":
            if local_trend == "down":
                score = 0.8
                bias = "Short"
            elif local_trend == "neutral":
                score = 0.6
                bias = "Short"
            else:
                score = 0.3  # Counter-trend
                bias = "Long"
        else:  # ranging
            score = 0.5
            # In ranging markets, stealth direction matters more
            if stealth_direction:
                bias = stealth_direction
                score = 0.7
        
        # 3. Adjust for market regime
        if regime == "volatile":
            # In volatile markets, breakouts are more likely
            score *= 1.2
        elif regime == "ranging":
            # In ranging markets, false breakouts are common
            score *= 0.8
        
        # 4. Check for altseason effects
        if trend_context.get('altseason') in ['confirmed', 'strong_altseason']:
            # During altseason, upward breakouts more likely
            if bias == "Long" or local_trend == "up":
                score *= 1.3
                bias = "Long"
        
        return min(score, 1.0), bias
    
    def _detect_volume_tightening(self, symbol: str, candles: List[Dict],
                                resistance: float, support: float) -> Dict:
        """Detect pre-breakout volume tightening patterns"""
        if len(candles) < VOLUME_TIGHTENING_LOOKBACK:
            return {'detected': False, 'score': 0}
        
        # Get volume data
        volumes = [float(c['volume']) for c in candles[-VOLUME_TIGHTENING_LOOKBACK:]]
        
        # Split into periods
        early_period = volumes[:len(volumes)//2]
        late_period = volumes[len(volumes)//2:]
        
        early_avg = np.mean(early_period)
        late_avg = np.mean(late_period)
        
        # Check for volume reduction
        volume_reduction = late_avg / early_avg if early_avg > 0 else 1
        
        # Check for decreasing volatility (tightening price action)
        early_candles = candles[-VOLUME_TIGHTENING_LOOKBACK:-VOLUME_TIGHTENING_LOOKBACK//2]
        late_candles = candles[-VOLUME_TIGHTENING_LOOKBACK//2:]
        
        early_volatility = np.std([float(c['close']) for c in early_candles])
        late_volatility = np.std([float(c['close']) for c in late_candles])
        
        volatility_reduction = late_volatility / early_volatility if early_volatility > 0 else 1
        
        # Combined tightening score
        is_tightening = (volume_reduction < VOLUME_TIGHTENING_THRESHOLD and 
                        volatility_reduction < 0.8)
        
        tightening_score = 0
        if is_tightening:
            # Strong tightening = higher score
            tightening_score = (1 - volume_reduction) * 0.5 + (1 - volatility_reduction) * 0.5
            
            # Check where tightening is occurring
            current_price = float(candles[-1]['close'])
            position = (current_price - support) / (resistance - support) if (resistance - support) > 0 else 0.5
            
            # Store tightening data
            self.volume_tightening_history[symbol] = {
                'time': datetime.now(),
                'volume_reduction': volume_reduction,
                'volatility_reduction': volatility_reduction,
                'position_in_range': position
            }
            
            log(f"📉 {symbol}: Volume tightening detected - Vol reduction: {volume_reduction:.2f}, Volatility reduction: {volatility_reduction:.2f}")
        
        return {
            'detected': is_tightening,
            'score': tightening_score,
            'volume_reduction': volume_reduction,
            'volatility_reduction': volatility_reduction,
            'early_avg_volume': early_avg,
            'late_avg_volume': late_avg
        }
    
    def _detect_enhanced_pre_breakout(self, symbol: str, candles: List[Dict],
                                    resistance: float, support: float,
                                    stealth_score: float, stealth_direction: Optional[str],
                                    trend_score: float, trend_bias: Optional[str],
                                    volume_tightening_data: Dict) -> Tuple[bool, Optional[str], float]:
        """Enhanced pre-breakout detection incorporating all factors"""
        confidence = 0
        direction = None
        signals = []
        
        # 1. Stealth accumulation contribution
        if stealth_score > 0.3:
            confidence += stealth_score * 0.35  # 35% weight
            signals.append(f"stealth_{stealth_direction}")
            if not direction and stealth_direction:
                direction = stealth_direction
        
        # 2. Trend alignment contribution
        if trend_score > 0.6:
            confidence += trend_score * 0.25  # 25% weight
            signals.append(f"trend_{trend_bias}")
            if not direction and trend_bias:
                direction = trend_bias
            elif direction == trend_bias:
                confidence += 0.1  # Bonus for agreement
        
        # 3. Volume tightening contribution
        if volume_tightening_data['detected']:
            confidence += volume_tightening_data['score'] * 0.25  # 25% weight
            signals.append("volume_tightening")
            
            # Volume tightening position can hint at direction
            position = self.volume_tightening_history.get(symbol, {}).get('position_in_range', 0.5)
            if position < 0.35 and not direction:
                direction = "Long"  # Tightening near support
            elif position > 0.65 and not direction:
                direction = "Short"  # Tightening near resistance
        
        # 4. Original pre-breakout checks (15% weight)
        original_confidence = self._calculate_original_pre_breakout_score(candles, resistance, support)
        confidence += original_confidence * 0.15
        
        # 5. Check for confluence of signals
        if len(signals) >= 3:
            confidence += 0.1  # Confluence bonus
            signals.append("confluence")
        
        # Direction validation
        if direction and stealth_direction and trend_bias:
            # All three agree = high confidence
            if direction == stealth_direction == trend_bias:
                confidence = min(confidence * 1.2, 1.0)
                signals.append("full_alignment")
        
        has_pre_breakout = confidence >= 0.6 and direction is not None
        
        if has_pre_breakout:
            log(f"📊 {symbol}: Enhanced pre-breakout detected - Confidence: {confidence:.2f}, Direction: {direction}")
            log(f"   Signals: {signals}")
            log(f"   Stealth: {stealth_score:.2f}, Trend: {trend_score:.2f}, Volume Tightening: {volume_tightening_data['score']:.2f}")
        
        return has_pre_breakout, direction, min(confidence, 1.0)
    
    def _calculate_original_pre_breakout_score(self, candles: List[Dict],
                                             resistance: float, support: float) -> float:
        """Calculate score from original pre-breakout indicators"""
        score = 0
        
        # Bollinger Band squeeze
        bb_data = calculate_bollinger_bands_advanced(candles)
        if bb_data:
            squeeze_info = detect_bollinger_squeeze(bb_data)
            if squeeze_info['squeeze']:
                score += 0.3 * squeeze_info['intensity']
        
        # RSI coiling
        rsi_data = calculate_rsi_with_bands(candles)
        if rsi_data:
            rsi = rsi_data['rsi']
            if 45 <= rsi <= 55:
                score += 0.4
        
        # Range compression
        compression_data = self._detect_range_compression(symbol, candles, resistance, support)
        if compression_data['is_compressing']:
            score += 0.3
        
        return score
    
    def _validate_breakout_with_context(self, symbol: str, candles: List[Dict],
                                      direction: str, resistance: float, support: float,
                                      stealth_score: float, trend_score: float,
                                      volume_tightening_data: Dict) -> bool:
        """Validate breakout using integrated context"""
        # Basic false breakout check
        if self._is_false_breakout(symbol, candles, direction, resistance, support):
            return False
        
        # Require at least one supporting factor
        supporting_factors = 0
        
        if stealth_score > 0.3:
            supporting_factors += 1
        if trend_score > 0.6:
            supporting_factors += 1
        if volume_tightening_data['detected']:
            supporting_factors += 1
        
        # Need at least 2 supporting factors for validation
        if supporting_factors < 2:
            log(f"⚠️ {symbol}: Insufficient supporting factors for breakout ({supporting_factors}/3)")
            return False
        
        return True
    
    def _calculate_integrated_confidence(self, breakout_confidence: float,
                                       pre_confidence: float, stealth_score: float,
                                       trend_score: float, volume_tightening_data: Dict,
                                       candles: List[Dict], direction: str) -> float:
        """Calculate final confidence incorporating all integrated factors"""
        # Base confidence from breakout
        final_confidence = breakout_confidence * 0.4  # 40% weight
        
        # Add pre-breakout confidence
        if pre_confidence > 0:
            final_confidence += pre_confidence * 0.2  # 20% weight
        
        # Add integrated factors
        final_confidence += stealth_score * 0.15  # 15% weight
        final_confidence += trend_score * 0.15    # 15% weight
        
        if volume_tightening_data['detected']:
            final_confidence += volume_tightening_data['score'] * 0.1  # 10% weight
        
        # Pattern confirmation bonus
        pattern = detect_pattern(candles)
        if pattern:
            pattern_strength = analyze_pattern_strength(pattern, candles)
            from pattern_detector import get_pattern_direction
            pattern_dir = get_pattern_direction(pattern)
            
            if (pattern_dir == "bullish" and direction == "Long") or \
               (pattern_dir == "bearish" and direction == "Short"):
                final_confidence = min(final_confidence + (pattern_strength * 0.1), 1.0)
        
        return min(final_confidence, 1.0)
    
    def detect_imminent_break(self, symbol: str, candles_by_tf: Dict[str, List[Dict]], 
                            regime: str) -> Tuple[bool, str, float, Dict]:
        """Detect imminent breakouts including pumps and dumps"""
        # Use 5m timeframe by default
        candles = candles_by_tf.get('5', [])
        if not candles or len(candles) < LOOKBACK_PERIOD:
            return False, None, 0, {}
        
        # Create trend context
        trend_context = {
            'regime': regime,
            'btc_trend': 'ranging',  # Default, should be passed from main
            'altseason': 'no'  # Default, should be passed from main
        }
        
        # Run full breakout detection
        breakout, direction, confidence, details = self.detect_range_breakout(
            symbol, candles, '5', trend_context
        )
        
        # Check for pump-specific patterns
        if breakout and direction == "Long":
            # Additional pump indicators
            pump_score = 0
            reasons = details.copy()
            
            # Strong stealth accumulation = pump potential
            if details.get('stealth_score', 0) > 0.6:
                pump_score += 0.3
                reasons['stealth_accumulation'] = {'strength': details['stealth_score']}
            
            # Volume tightening before pump
            if details.get('volume_tightening', {}).get('detected'):
                pump_score += 0.2
                reasons['volume_coiling'] = {'strength': details['volume_tightening']['score']}
            
            # Smart money patterns
            from whale_detector import detect_whale_activity_advanced
            whale_data = detect_whale_activity_advanced(candles, symbol)
            if whale_data['detected'] and whale_data['recommendation'] == 'potential_long':
                pump_score += 0.3
                reasons['smart_money'] = {'strength': whale_data['strength']}
            
            # If pump score is high, flag as pump
            if pump_score > 0.5:
                confidence = min(confidence * 1.2, 1.0)
                reasons['pump_pattern'] = True
        
        return breakout, direction, confidence, details
    
    # Keep existing helper methods unchanged
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
range_break_detector = RangeBreakoutStrategy()

# Convenience functions for backward compatibility and easier access
def detect_range_breakout(candles: List[Dict], timeframe: str = "5") -> bool:
    """Backward compatible function that returns simple True/False"""
    breakout, _, _, _ = range_break_detector.detect_range_breakout("", candles, timeframe)
    return breakout

def should_override_regime_for_break(break_confidence: float, current_regime: str) -> bool:
    """Determine if break signal should override current regime"""
    if break_confidence >= 0.8:
        return True  # High confidence breaks override any regime
    elif break_confidence >= 0.65 and current_regime == "ranging":
        return True  # Medium confidence sufficient in ranging markets
    return False

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
            
            # Check for imminent break (includes both dumps and pumps)
            break_imminent, direction, confidence, reasons = range_break_detector.detect_imminent_break(
                symbol, candles_by_tf, regime
            )
            
            if break_imminent:
                # Check if it's a pump signal
                if direction == "Long" and any(k in reasons for k in ['stealth_accumulation', 'smart_money', 'pump_pattern']):
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
