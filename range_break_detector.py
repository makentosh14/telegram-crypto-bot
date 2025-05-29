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

# Enhanced configuration for better pre-breakout detection
PRE_BREAKOUT_LOOKBACK = 30  # Candles to analyze for pre-breakout patterns
VOLUME_COMPRESSION_THRESHOLD = 0.6  # 60% volume reduction for compression signal
PRICE_COMPRESSION_THRESHOLD = 0.7  # 70% price range reduction
MIN_COMPRESSION_DURATION = 10  # Minimum candles in compression phase

# Enhanced volume configuration
VOLUME_SURGE_MULTIPLIER = 2.5  # Strong volume surge on breakout
VOLUME_CONSISTENCY_LOOKBACK = 5  # Check volume consistency post-breakout
MIN_VOLUME_PERCENTILE = 0.7  # Breakout volume should be in top 30% of recent volumes

RANGE_BREAK_CONFIG = {
    'min_confidence': {
        'trending': 0.7,
        'ranging': 0.65,
        'volatile': 0.6
    },
    'score_multipliers': {
        'pump_signal': 2.0,
        'pre_breakout': 1.5,
        'stealth_accumulation': 1.3
    },
    'exit_strategies': {
        'pump': {
            'tp1_mult': 1.3,
            'trailing_mult': 1.5,
            'tranches': [0.25, 0.35, 0.40]
        },
        'break': {
            'tp1_mult': 1.2,
            'trailing_mult': 1.2,
            'tranches': [0.33, 0.33, 0.34]
        }
    }
}

class RangeBreakoutStrategy:
    """Enhanced range breakout strategy with advanced pre-breakout detection and volume analysis"""
    
    def __init__(self):
        self.compression_history = {}
        self.breakout_candidates = {}
        self.failed_breakouts = {}
        self.stealth_activity = {}
        self.volume_tightening_history = {}
        self.pre_breakout_alerts = {}  # Track pre-breakout alerts
        self.volume_profiles = {}  # Store volume profiles for analysis
        
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
        
        # 3. Enhanced volume analysis including profile
        volume_analysis = self._analyze_volume_comprehensively(
            symbol, candles, high_boundary, low_boundary
        )
        details['volume_analysis'] = volume_analysis
        
        # 4. Enhanced pre-breakout detection with buildup patterns
        pre_breakout_data = self._detect_comprehensive_pre_breakout(
            symbol, candles, high_boundary, low_boundary,
            stealth_score, stealth_direction, trend_score, trend_bias,
            volume_analysis
        )
        
        if pre_breakout_data['detected']:
            details['pre_breakout'] = True
            details['pre_breakout_confidence'] = pre_breakout_data['confidence']
            details['pre_breakout_direction'] = pre_breakout_data['direction']
            details['buildup_patterns'] = pre_breakout_data['patterns']
            
            # If pre-breakout confidence is high enough, signal early entry
            if pre_breakout_data['confidence'] >= PRE_BREAKOUT_THRESHOLD:
                log(f"🎯 {symbol}: Strong pre-breakout signal! Direction: {pre_breakout_data['direction']}, Confidence: {pre_breakout_data['confidence']:.2f}")
                log(f"   Buildup patterns: {pre_breakout_data['patterns']}")
                return True, pre_breakout_data['direction'], pre_breakout_data['confidence'], details
        
        # 5. Check for actual breakout with enhanced volume validation
        breakout_data = self._check_breakout_with_enhanced_volume(
            candles, high_boundary, low_boundary, current_price, volume_analysis
        )
        
        if breakout_data['detected']:
            # Additional validation with integrated factors
            if self._validate_breakout_comprehensively(
                symbol, candles, breakout_data['direction'], high_boundary, low_boundary,
                stealth_score, trend_score, volume_analysis, breakout_data
            ):
                # Calculate final confidence incorporating all factors
                final_confidence = self._calculate_integrated_confidence(
                    breakout_data['confidence'], pre_breakout_data.get('confidence', 0),
                    stealth_score, trend_score, volume_analysis, candles, breakout_data['direction']
                )
                
                details['breakout_type'] = 'confirmed'
                details['volume_confirmation'] = breakout_data['volume_metrics']
                details['integrated_factors'] = {
                    'stealth': stealth_score,
                    'trend': trend_score,
                    'volume_profile': volume_analysis['profile_score'],
                    'volume_trend': volume_analysis['trend_score']
                }
                
                log(f"✅ {symbol}: Range breakout confirmed! Direction: {breakout_data['direction']}, Confidence: {final_confidence:.2f}")
                log(f"   Volume confirmation: {breakout_data['volume_metrics']}")
                return True, breakout_data['direction'], final_confidence, details
            else:
                log(f"⚠️ {symbol}: Breakout failed comprehensive validation")
                self.failed_breakouts[symbol] = {
                    'time': datetime.now(),
                    'direction': breakout_data['direction'],
                    'level': high_boundary if breakout_data['direction'] == "Long" else low_boundary,
                    'reason': breakout_data.get('failure_reason', 'validation_failed')
                }
                return False, None, 0, details
            
        return False, None, 0, details
    
    def _analyze_volume_comprehensively(self, symbol: str, candles: List[Dict],
                                      resistance: float, support: float) -> Dict:
        """Comprehensive volume analysis including profile and patterns"""
        
        # 1. Volume tightening analysis
        tightening_data = self._detect_volume_tightening(symbol, candles, resistance, support)
        
        # 2. Volume profile analysis
        profile_data = self._analyze_volume_profile(candles, resistance, support)
        
        # 3. Volume trend analysis
        trend_data = self._analyze_volume_trend(candles)
        
        # 4. Volume buildup detection
        buildup_data = self._detect_volume_buildup(candles)
        
        # Calculate composite volume score
        volume_score = 0
        if tightening_data['detected']:
            volume_score += tightening_data['score'] * 0.25
        volume_score += profile_data['score'] * 0.25
        volume_score += trend_data['score'] * 0.25
        volume_score += buildup_data['score'] * 0.25
        
        return {
            'tightening': tightening_data,
            'profile': profile_data,
            'trend': trend_data,
            'buildup': buildup_data,
            'composite_score': min(volume_score, 1.0),
            'profile_score': profile_data['score'],
            'trend_score': trend_data['score']
        }
    
    def _analyze_volume_profile(self, candles: List[Dict], resistance: float, support: float) -> Dict:
        """Analyze volume distribution across price levels"""
        if len(candles) < 20:
            return {'score': 0, 'high_volume_node': None}
    
        # Check if resistance and support are too close (avoid division by zero)
        if abs(resistance - support) < 0.00001:  # Very tight range
            log(f"⚠️ Range too tight for volume profile analysis: {resistance:.8f} - {support:.8f}")
            return {'score': 0, 'high_volume_node': None, 'error': 'range_too_tight'}
    
        # Create price bins
        price_bins = {}
        bin_size = (resistance - support) / 10  # 10 bins across range
    
        # Additional safety check
        if bin_size <= 0:
            log(f"⚠️ Invalid bin size: {bin_size} (resistance: {resistance}, support: {support})")
            return {'score': 0, 'high_volume_node': None, 'error': 'invalid_range'}
    
        for candle in candles[-50:]:  # Last 50 candles
            high = float(candle['high'])
            low = float(candle['low'])
            volume = float(candle['volume'])
            avg_price = (high + low) / 2
        
            # Determine which bin this candle belongs to
            bin_index = int((avg_price - support) / bin_size)
            bin_index = max(0, min(9, bin_index))  # Ensure within bounds
        
            if bin_index not in price_bins:
                price_bins[bin_index] = 0
            price_bins[bin_index] += volume
    
        # Find high volume nodes
        if price_bins:
            max_volume_bin = max(price_bins.items(), key=lambda x: x[1])
            total_volume = sum(price_bins.values())
        
            # Calculate score based on volume concentration
            concentration = max_volume_bin[1] / total_volume if total_volume > 0 else 0
        
            # High volume node position
            node_position = max_volume_bin[0] / 10  # Normalize to 0-1
        
            score = 0
            # Score higher if high volume node is at extremes (potential breakout)
            if node_position < 0.3 or node_position > 0.7:
                score = concentration * 0.8
            else:
                score = concentration * 0.4
        
            return {
                'score': score,
                'high_volume_node': max_volume_bin[0],
                'concentration': concentration,
                'distribution': price_bins
            }
    
        return {'score': 0, 'high_volume_node': None}
    
    def _analyze_volume_trend(self, candles: List[Dict]) -> Dict:
        """Analyze volume trend patterns"""
        if len(candles) < 20:
            return {'score': 0, 'trend': 'neutral'}
        
        volumes = [float(c['volume']) for c in candles[-20:]]
        
        # Calculate trend
        x = np.arange(len(volumes))
        slope = np.polyfit(x, volumes, 1)[0]
        avg_volume = np.mean(volumes)
        
        # Normalize slope
        normalized_slope = slope / avg_volume if avg_volume > 0 else 0
        
        # Determine trend and score
        if normalized_slope > 0.05:  # Increasing volume
            trend = 'increasing'
            score = min(normalized_slope * 5, 0.8)
        elif normalized_slope < -0.05:  # Decreasing volume
            trend = 'decreasing'
            score = 0.3  # Less favorable
        else:
            trend = 'neutral'
            score = 0.5
        
        return {
            'score': score,
            'trend': trend,
            'slope': normalized_slope
        }
    
    def _detect_volume_buildup(self, candles: List[Dict]) -> Dict:
        """Detect volume buildup patterns before breakout"""
        if len(candles) < 10:
            return {'detected': False, 'score': 0}
        
        recent_volumes = [float(c['volume']) for c in candles[-10:]]
        older_volumes = [float(c['volume']) for c in candles[-30:-10]] if len(candles) >= 30 else []
        
        if not older_volumes:
            return {'detected': False, 'score': 0}
        
        # Check for gradual volume increase
        recent_avg = np.mean(recent_volumes[-5:])
        older_avg = np.mean(older_volumes)
        
        buildup_ratio = recent_avg / older_avg if older_avg > 0 else 1
        
        # Check for volume spikes within recent candles
        spike_count = sum(1 for v in recent_volumes if v > older_avg * 1.5)
        
        detected = buildup_ratio > 1.2 and spike_count >= 2
        score = 0
        
        if detected:
            score = min((buildup_ratio - 1) * 2, 0.8)  # Cap at 0.8
            if spike_count >= 3:
                score = min(score * 1.2, 1.0)
        
        return {
            'detected': detected,
            'score': score,
            'buildup_ratio': buildup_ratio,
            'spike_count': spike_count
        }
    
    def _detect_comprehensive_pre_breakout(self, symbol: str, candles: List[Dict],
                                         resistance: float, support: float,
                                         stealth_score: float, stealth_direction: Optional[str],
                                         trend_score: float, trend_bias: Optional[str],
                                         volume_analysis: Dict) -> Dict:
        """Comprehensive pre-breakout detection with multiple buildup patterns"""
        
        patterns = []
        confidence = 0
        direction = None
        
        # 1. Price compression pattern
        compression_data = self._detect_advanced_compression(candles, resistance, support)
        if compression_data['detected']:
            patterns.append('price_compression')
            confidence += compression_data['score'] * 0.2
            if compression_data['bias']:
                direction = compression_data['bias']
        
        # 2. Volume compression/tightening
        if volume_analysis['tightening']['detected']:
            patterns.append('volume_tightening')
            confidence += volume_analysis['tightening']['score'] * 0.15
        
        # 3. Bollinger Band squeeze
        bb_squeeze_data = self._detect_bb_squeeze_buildup(candles)
        if bb_squeeze_data['detected']:
            patterns.append('bb_squeeze')
            confidence += bb_squeeze_data['score'] * 0.15
        
        # 4. Triangle/Wedge patterns
        triangle_data = self._detect_triangle_pattern(candles, resistance, support)
        if triangle_data['detected']:
            patterns.append(f"{triangle_data['type']}_triangle")
            confidence += triangle_data['score'] * 0.15
            if triangle_data['bias'] and not direction:
                direction = triangle_data['bias']
        
        # 5. Stealth accumulation contribution
        if stealth_score > 0.3:
            patterns.append('stealth_accumulation')
            confidence += stealth_score * 0.15
            if not direction and stealth_direction:
                direction = stealth_direction
        
        # 6. Multiple timeframe confluence
        mtf_data = self._check_mtf_compression(symbol, candles)
        if mtf_data['detected']:
            patterns.append('mtf_confluence')
            confidence += mtf_data['score'] * 0.1
        
        # 7. RSI compression
        rsi_compression = self._detect_rsi_compression(candles)
        if rsi_compression['detected']:
            patterns.append('rsi_compression')
            confidence += rsi_compression['score'] * 0.1
        
        # Direction determination with multiple factors
        if not direction:
            # Use trend bias if available
            if trend_bias and trend_score > 0.6:
                direction = trend_bias
            # Use volume profile bias
            elif volume_analysis['profile']['high_volume_node'] is not None:
                node = volume_analysis['profile']['high_volume_node']
                if node < 3:  # Lower third of range
                    direction = "Long"
                elif node > 7:  # Upper third of range
                    direction = "Short"
        
        # Boost confidence for multiple pattern confluence
        if len(patterns) >= 4:
            confidence *= 1.2
            patterns.append('multiple_confluence')
        
        # Store pre-breakout alert
        if confidence >= 0.6 and direction:
            self.pre_breakout_alerts[symbol] = {
                'time': datetime.now(),
                'patterns': patterns,
                'direction': direction,
                'confidence': confidence
            }
        
        return {
            'detected': confidence >= 0.6 and direction is not None,
            'confidence': min(confidence, 1.0),
            'direction': direction,
            'patterns': patterns,
            'compression_data': compression_data,
            'triangle_data': triangle_data
        }
    
    def _detect_advanced_compression(self, candles: List[Dict], resistance: float, support: float) -> Dict:
        """Detect advanced price compression patterns"""
        if len(candles) < PRE_BREAKOUT_LOOKBACK:
            return {'detected': False, 'score': 0}
        
        # Analyze range compression over time
        compression_periods = []
        for i in range(PRE_BREAKOUT_LOOKBACK, len(candles), 5):
            period_candles = candles[i-10:i]
            period_high = max(float(c['high']) for c in period_candles)
            period_low = min(float(c['low']) for c in period_candles)
            period_range = period_high - period_low
            compression_periods.append({
                'range': period_range,
                'high': period_high,
                'low': period_low,
                'index': i
            })
        
        if len(compression_periods) < 3:
            return {'detected': False, 'score': 0}
        
        # Check for decreasing range
        initial_range = compression_periods[0]['range']
        current_range = compression_periods[-1]['range']
        compression_ratio = current_range / initial_range if initial_range > 0 else 1
        
        # Check for consistent compression
        decreasing_count = 0
        for i in range(1, len(compression_periods)):
            if compression_periods[i]['range'] < compression_periods[i-1]['range']:
                decreasing_count += 1
        
        compression_consistency = decreasing_count / (len(compression_periods) - 1)
        
        # Determine compression quality
        is_compressing = (compression_ratio < PRICE_COMPRESSION_THRESHOLD and 
                         compression_consistency > 0.6)
        
        # Calculate compression duration
        if is_compressing:
            compression_candles = len(candles) - compression_periods[0]['index']
            duration_score = min(compression_candles / 50, 1.0)  # Normalize to 0-1
        else:
            duration_score = 0
        
        # Determine bias based on price position and trend during compression
        bias = None
        if is_compressing:
            # Check price position
            current_price = float(candles[-1]['close'])
            position = (current_price - support) / (resistance - support) if (resistance - support) > 0 else 0.5
            
            # Check micro-trend within compression
            recent_closes = [float(c['close']) for c in candles[-10:]]
            micro_slope = np.polyfit(range(len(recent_closes)), recent_closes, 1)[0]
            
            if position > 0.65 and micro_slope > 0:
                bias = "Long"
            elif position < 0.35 and micro_slope < 0:
                bias = "Short"
            elif micro_slope > 0:
                bias = "Long"
            elif micro_slope < 0:
                bias = "Short"
        
        score = 0
        if is_compressing:
            score = (1 - compression_ratio) * 0.5 + compression_consistency * 0.3 + duration_score * 0.2
        
        return {
            'detected': is_compressing,
            'score': score,
            'compression_ratio': compression_ratio,
            'consistency': compression_consistency,
            'duration_candles': compression_candles if is_compressing else 0,
            'bias': bias,
            'periods': compression_periods
        }
    
    def _detect_bb_squeeze_buildup(self, candles: List[Dict]) -> Dict:
        """Detect Bollinger Band squeeze as pre-breakout signal"""
        bb_data = calculate_bollinger_bands_advanced(candles)
        if not bb_data or len(bb_data) < 20:
            return {'detected': False, 'score': 0}
        
        # Check for sustained squeeze
        squeeze_count = 0
        min_bandwidth = float('inf')
        
        for i in range(-20, 0):
            if bb_data[i] and bb_data[i].get('squeeze'):
                squeeze_count += 1
                min_bandwidth = min(min_bandwidth, bb_data[i]['bandwidth'])
        
        # Calculate squeeze intensity
        squeeze_ratio = squeeze_count / 20
        is_squeezing = squeeze_ratio > 0.5  # At least 50% of recent candles in squeeze
        
        score = 0
        if is_squeezing:
            # Higher score for tighter and longer squeezes
            tightness_score = (1 - min(min_bandwidth / 0.02, 1.0)) * 0.5
            duration_score = squeeze_ratio * 0.5
            score = tightness_score + duration_score
        
        return {
            'detected': is_squeezing,
            'score': score,
            'squeeze_ratio': squeeze_ratio,
            'min_bandwidth': min_bandwidth
        }
    
    def _detect_triangle_pattern(self, candles: List[Dict], resistance: float, support: float) -> Dict:
        """Detect triangle/wedge consolidation patterns"""
        if len(candles) < 20:
            return {'detected': False, 'type': None, 'score': 0}
        
        # Get highs and lows
        highs = [float(c['high']) for c in candles[-20:]]
        lows = [float(c['low']) for c in candles[-20:]]
        
        # Fit trend lines
        x = np.arange(len(highs))
        high_slope = np.polyfit(x, highs, 1)[0]
        low_slope = np.polyfit(x, lows, 1)[0]
        
        # Normalize slopes
        avg_price = np.mean(highs + lows) / 2
        high_slope_norm = high_slope / avg_price if avg_price > 0 else 0
        low_slope_norm = low_slope / avg_price if avg_price > 0 else 0
        
        # Detect pattern type
        pattern_type = None
        bias = None
        score = 0
        
        # Symmetrical triangle (converging)
        if high_slope_norm < -0.001 and low_slope_norm > 0.001:
            pattern_type = 'symmetrical'
            # Bias based on trend before triangle
            earlier_closes = [float(c['close']) for c in candles[-40:-20]]
            if len(earlier_closes) >= 10:
                trend_slope = np.polyfit(range(len(earlier_closes)), earlier_closes, 1)[0]
                bias = "Long" if trend_slope > 0 else "Short"
            score = 0.7
        
        # Ascending triangle (bullish)
        elif abs(high_slope_norm) < 0.0005 and low_slope_norm > 0.001:
            pattern_type = 'ascending'
            bias = "Long"
            score = 0.8
        
        # Descending triangle (bearish)
        elif high_slope_norm < -0.001 and abs(low_slope_norm) < 0.0005:
            pattern_type = 'descending'
            bias = "Short"
            score = 0.8
        
        # Check if we're near apex (higher urgency)
        if pattern_type:
            current_range = highs[-1] - lows[-1]
            initial_range = highs[0] - lows[0]
            compression = current_range / initial_range if initial_range > 0 else 1
            
            if compression < 0.5:  # Near apex
                score *= 1.2
                score = min(score, 1.0)
        
        return {
            'detected': pattern_type is not None,
            'type': pattern_type,
            'bias': bias,
            'score': score,
            'high_slope': high_slope_norm,
            'low_slope': low_slope_norm
        }
    
    def _check_mtf_compression(self, symbol: str, candles: List[Dict]) -> Dict:
        """Check for compression across multiple timeframes"""
        # This would typically check multiple timeframes
        # For now, simulate with different lookback periods
        compressions = []
        
        for lookback in [10, 20, 30]:
            if len(candles) >= lookback:
                period_candles = candles[-lookback:]
                high = max(float(c['high']) for c in period_candles)
                low = min(float(c['low']) for c in period_candles)
                range_pct = ((high - low) / low) * 100 if low > 0 else 0
                
                if range_pct < 2.0:  # Less than 2% range
                    compressions.append(lookback)
        
        detected = len(compressions) >= 2
        score = len(compressions) / 3 if detected else 0
        
        return {
            'detected': detected,
            'score': score,
            'compressed_timeframes': compressions
        }
    
    def _detect_rsi_compression(self, candles: List[Dict]) -> Dict:
        """Detect RSI compression/coiling"""
        rsi_data = calculate_rsi_with_bands(candles)
        if not rsi_data or not rsi_data.get('values'):
            return {'detected': False, 'score': 0}
        
        rsi_values = rsi_data['values'][-20:] if len(rsi_data['values']) >= 20 else rsi_data['values']
        
        if len(rsi_values) < 10:
            return {'detected': False, 'score': 0}
        
        # Check if RSI is coiling (decreasing volatility)
        rsi_std = np.std(rsi_values)
        rsi_mean = np.mean(rsi_values)
        
        # RSI compression: low volatility around 50
        is_compressed = rsi_std < 10 and 45 <= rsi_mean <= 55
        
        score = 0
        if is_compressed:
            # Tighter compression = higher score
            score = (1 - rsi_std / 10) * 0.7
            # Closer to 50 = higher score
            score += (1 - abs(rsi_mean - 50) / 10) * 0.3
        
        return {
            'detected': is_compressed,
            'score': score,
            'rsi_std': rsi_std,
            'rsi_mean': rsi_mean
        }
    
    def _check_breakout_with_enhanced_volume(self, candles: List[Dict], resistance: float, 
                                           support: float, current_price: float,
                                           volume_analysis: Dict) -> Dict:
        """Enhanced breakout detection with comprehensive volume validation"""
        if len(candles) < 2:
            return {'detected': False}
            
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
        
        # Volume analysis
        recent_volumes = [float(c['volume']) for c in candles[-30:]]
        avg_volume = np.mean(recent_volumes[:-1])
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1
        
        # Volume percentile
        volume_percentile = sum(v < volume for v in recent_volumes) / len(recent_volumes)
        
        # Check for volume surge
        is_volume_surge = volume_ratio >= VOLUME_SURGE_MULTIPLIER
        
        breakout_detected = False
        direction = None
        confidence = 0
        volume_metrics = {}
        
        # Check for resistance breakout
        if close > resistance and close > open_price:
            # Basic validation
            if prev_candle and float(prev_candle['close']) < resistance:
                # Enhanced volume requirements
                volume_valid = (
                    volume_ratio >= BREAKOUT_MULTIPLIER and
                    volume_percentile >= MIN_VOLUME_PERCENTILE
                )
                
                if volume_valid:
                    breakout_detected = True
                    direction = "Long"
                    confidence = 0.6
                    
                    # Confidence adjustments based on volume
                    if is_volume_surge:
                        confidence += 0.2
                    if volume_percentile > 0.9:  # Top 10% volume
                        confidence += 0.1
                    if volume_analysis['buildup']['detected']:
                        confidence += 0.1
                    
                    # Strong breakout candle
                    if body_size_pct >= MIN_BODY_SIZE_PCT and body_size / total_range > 0.7:
                        confidence += 0.1
                    
                    volume_metrics = {
                        'ratio': volume_ratio,
                        'percentile': volume_percentile,
                        'surge': is_volume_surge,
                        'buildup': volume_analysis['buildup']['detected']
                    }
        
        # Check for support breakdown
        elif close < support and close < open_price:
            # Basic validation
            if prev_candle and float(prev_candle['close']) > support:
                # Enhanced volume requirements
                volume_valid = (
                    volume_ratio >= BREAKOUT_MULTIPLIER and
                    volume_percentile >= MIN_VOLUME_PERCENTILE
                )
                
                if volume_valid:
                    breakout_detected = True
                    direction = "Short"
                    confidence = 0.6
                    
                    # Confidence adjustments based on volume
                    if is_volume_surge:
                        confidence += 0.2
                    if volume_percentile > 0.9:
                        confidence += 0.1
                    if volume_analysis['buildup']['detected']:
                        confidence += 0.1
                    
                    # Strong breakout candle
                    if body_size_pct >= MIN_BODY_SIZE_PCT and body_size / total_range > 0.7:
                        confidence += 0.1
                    
                    volume_metrics = {
                        'ratio': volume_ratio,
                        'percentile': volume_percentile,
                        'surge': is_volume_surge,
                        'buildup': volume_analysis['buildup']['detected']
                    }
        
        return {
            'detected': breakout_detected,
            'direction': direction,
            'confidence': min(confidence, 1.0),
            'volume_metrics': volume_metrics,
            'body_size_pct': body_size_pct,
            'volume_ratio': volume_ratio
        }
    
    def _validate_breakout_comprehensively(self, symbol: str, candles: List[Dict],
                                         direction: str, resistance: float, support: float,
                                         stealth_score: float, trend_score: float,
                                         volume_analysis: Dict, breakout_data: Dict) -> bool:
        """Comprehensive breakout validation with enhanced volume checks"""
        
        # 1. Volume validation
        volume_valid = self._validate_volume_consistency(candles, breakout_data)
        if not volume_valid:
            log(f"⚠️ {symbol}: Breakout failed volume consistency check")
            return False
        
        # 2. False breakout detection
        if self._is_false_breakout_enhanced(symbol, candles, direction, resistance, support, breakout_data):
            return False
        
        # 3. Require supporting factors
        supporting_factors = 0
        
        if stealth_score > 0.3:
            supporting_factors += 1
        if trend_score > 0.6:
            supporting_factors += 1
        if volume_analysis['composite_score'] > 0.5:
            supporting_factors += 1
        if breakout_data['volume_metrics'].get('surge', False):
            supporting_factors += 1
        if volume_analysis['buildup']['detected']:
            supporting_factors += 1
        
        # Need at least 3 supporting factors for validation
        if supporting_factors < 3:
            log(f"⚠️ {symbol}: Insufficient supporting factors ({supporting_factors}/5)")
            return False
        
        # 4. Check if we had pre-breakout alert
        if symbol in self.pre_breakout_alerts:
            alert = self.pre_breakout_alerts[symbol]
            time_since_alert = (datetime.now() - alert['time']).seconds / 60
            
            # Bonus validation if pre-breakout was detected
            if time_since_alert < 30 and alert['direction'] == direction:
                log(f"✅ {symbol}: Breakout confirmed pre-breakout alert")
                return True
        
        return True
    
    def _validate_volume_consistency(self, candles: List[Dict], breakout_data: Dict) -> bool:
        """Validate volume consistency post-breakout"""
        if len(candles) < VOLUME_CONSISTENCY_LOOKBACK:
            return True  # Not enough data, allow
        
        # Get volumes after breakout candle
        post_breakout_volumes = [float(c['volume']) for c in candles[-VOLUME_CONSISTENCY_LOOKBACK:]]
        breakout_volume = float(candles[-1]['volume'])
        
        # Check if volume remains elevated
        avg_post_volume = np.mean(post_breakout_volumes[:-1]) if len(post_breakout_volumes) > 1 else 0
        
        # Volume should not immediately dry up after breakout
        if avg_post_volume > 0:
            consistency_ratio = avg_post_volume / breakout_volume
            
            # If volume drops too much, it's suspicious
            if consistency_ratio < 0.3:  # Less than 30% of breakout volume
                return False
        
        return True
    
    def _is_false_breakout_enhanced(self, symbol: str, candles: List[Dict], direction: str,
                                   resistance: float, support: float, breakout_data: Dict) -> bool:
        """Enhanced false breakout detection with volume analysis"""
        if len(candles) < 5:
            return False
            
        # Check previous failed breakouts
        if symbol in self.failed_breakouts:
            failed_data = self.failed_breakouts[symbol]
            time_since_failure = (datetime.now() - failed_data['time']).seconds / 60
            
            # If same direction failed recently with similar conditions
            if time_since_failure < 30 and failed_data['direction'] == direction:
                return True
        
        last_candle = candles[-1]
        
        # Volume-based false breakout detection
        if breakout_data.get('volume_metrics'):
            metrics = breakout_data['volume_metrics']
            
            # Low volume percentile despite meeting ratio (could be thin market)
            if metrics['percentile'] < 0.5 and not metrics.get('surge', False):
                return True
            
            # No volume buildup and sudden spike (potential fake)
            if not metrics.get('buildup', False) and metrics['ratio'] > 5:
                # Check if it's sustained
                if len(candles) >= 3:
                    next_volumes = [float(c['volume']) for c in candles[-3:-1]]
                    if all(v < float(candles[-1]['volume']) * 0.3 for v in next_volumes):
                        return True
        
        # Wick analysis
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
                
                # Large upper wick with small body suggests rejection
                if wick_ratio > 0.6 and body_size / total_range < 0.3:
                    return True
                    
            else:  # Short
                lower_wick = min(close, open_price) - low
                wick_ratio = lower_wick / total_range
                
                # Large lower wick with small body suggests rejection
                if wick_ratio > 0.6 and body_size / total_range < 0.3:
                    return True
        
        # Immediate reversal check
        if len(candles) >= 3:
            # Check if price immediately reverses
            if direction == "Long":
                if close < resistance * 0.995:  # Back below resistance
                    return True
            else:  # Short
                if close > support * 1.005:  # Back above support
                    return True
        
        return False
    
    # Keep other methods unchanged...
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
    
    def _calculate_integrated_confidence(self, breakout_confidence: float,
                                       pre_confidence: float, stealth_score: float,
                                       trend_score: float, volume_analysis: Dict,
                                       candles: List[Dict], direction: str) -> float:
        """Calculate final confidence incorporating all integrated factors"""
        # Base confidence from breakout
        final_confidence = breakout_confidence * 0.3  # 30% weight
        
        # Add pre-breakout confidence
        if pre_confidence > 0:
            final_confidence += pre_confidence * 0.25  # 25% weight
        
        # Add integrated factors
        final_confidence += stealth_score * 0.15  # 15% weight
        final_confidence += trend_score * 0.15    # 15% weight
        
        # Volume analysis contribution (15% total)
        final_confidence += volume_analysis['composite_score'] * 0.15
        
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
            if details.get('volume_analysis', {}).get('tightening', {}).get('detected'):
                pump_score += 0.2
                reasons['volume_coiling'] = {'strength': details['volume_analysis']['tightening']['score']}
            
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
    
        # Check if range is valid (not zero or too small)
        if range_high <= range_low or (range_high - range_low) < 0.00001:
            return {'is_ranging': False, 'reason': 'invalid_range'}
    
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
