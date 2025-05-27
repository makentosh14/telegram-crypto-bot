# enhanced_entry_validator.py - New module for better entry timing

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from logger import log
from volume import get_average_volume

class EntryValidator:
    """Enhanced entry validation to prevent late entries and improve timing"""
    
    def __init__(self):
        self.key_levels_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    def validate_entry(self, symbol: str, candles_by_tf: Dict, direction: str, 
                      entry_price: float, trade_type: str, score: float) -> Tuple[bool, str]:
        """
        Master validation function that checks all entry criteria
        
        Returns:
            Tuple of (is_valid, reason)
        """
        # 1. Check momentum alignment
        momentum_valid, momentum_reason = self.check_momentum_alignment(
            candles_by_tf, direction, trade_type
        )
        if not momentum_valid:
            return False, momentum_reason
            
        # 2. Check key levels
        levels_valid, levels_reason = self.check_key_levels(
            symbol, candles_by_tf, entry_price, direction
        )
        if not levels_valid:
            return False, levels_reason
            
        # 3. Check timeframe alignment
        tf_valid, tf_reason = self.check_timeframe_alignment(
            candles_by_tf, direction, trade_type
        )
        if not tf_valid:
            return False, tf_reason
            
        # 4. Check market structure
        structure_valid, structure_reason = self.check_market_structure(
            candles_by_tf, trade_type
        )
        if not structure_valid:
            return False, structure_reason
            
        # 5. Check for exhaustion
        exhaustion = self.detect_exhaustion(candles_by_tf, direction)
        if exhaustion:
            return False, "Price exhaustion detected"
            
        return True, "All validations passed"
    
    def check_momentum_alignment(self, candles_by_tf: Dict, direction: str, 
                               trade_type: str) -> Tuple[bool, str]:
        """Check if current momentum aligns with trade direction"""
        
        # Get relevant timeframe based on trade type
        if trade_type == "Scalp":
            check_tfs = ["1", "3"]
            momentum_threshold = 0.3  # 0.3% move
        elif trade_type == "Intraday":
            check_tfs = ["5", "15"]
            momentum_threshold = 0.5  # 0.5% move
        else:  # Swing
            check_tfs = ["15", "30"]
            momentum_threshold = 0.8  # 0.8% move
            
        # Check recent momentum
        for tf in check_tfs:
            if tf not in candles_by_tf:
                continue
                
            candles = candles_by_tf[tf]
            if len(candles) < 5:
                continue
                
            # Check last 3 candles for adverse movement
            recent_candles = candles[-3:]
            first_open = float(recent_candles[0]['open'])
            last_close = float(recent_candles[-1]['close'])
            
            move_pct = ((last_close - first_open) / first_open) * 100
            
            # Check if move is against our direction
            if direction == "Long" and move_pct < -momentum_threshold:
                return False, f"Adverse momentum on {tf}m: {move_pct:.2f}%"
            elif direction == "Short" and move_pct > momentum_threshold:
                return False, f"Adverse momentum on {tf}m: {move_pct:.2f}%"
                
        # Check for momentum exhaustion
        if self._is_momentum_exhausted(candles_by_tf, direction):
            return False, "Momentum appears exhausted"
            
        return True, "Momentum aligned"
    
    def _is_momentum_exhausted(self, candles_by_tf: Dict, direction: str) -> bool:
        """Check if momentum is exhausted (consecutive candles in same direction)"""
        
        candles_1m = candles_by_tf.get("1", [])
        if len(candles_1m) < 7:
            return False
            
        # Count consecutive candles in same direction
        consecutive = 0
        for i in range(-7, -1):
            candle = candles_1m[i]
            close = float(candle['close'])
            open_price = float(candle['open'])
            
            if direction == "Long":
                if close > open_price:
                    consecutive += 1
                else:
                    consecutive = 0
            else:  # Short
                if close < open_price:
                    consecutive += 1
                else:
                    consecutive = 0
                    
        # If 5+ consecutive candles in opposite direction, momentum is exhausted
        return consecutive >= 7
    
    def check_key_levels(self, symbol: str, candles_by_tf: Dict, 
                        entry_price: float, direction: str) -> Tuple[bool, str]:
        """Check if entry price is near key support/resistance levels"""
        
        # Get key levels
        levels = self.calculate_key_levels(symbol, candles_by_tf)
        
        if not levels:
            return True, "No key levels detected"
            
        # Check proximity to each level
        min_distance_pct = 0.3  # Minimum 0.3% distance from key levels
        
        for level_type, level_price in levels.items():
            distance_pct = abs((entry_price - level_price) / level_price) * 100
            
            if distance_pct < min_distance_pct:
                # Check if we're on the wrong side of the level
                if direction == "Long" and entry_price > level_price and "resistance" in level_type:
                    return False, f"Too close to {level_type} at {level_price:.6f}"
                elif direction == "Short" and entry_price < level_price and "support" in level_type:
                    return False, f"Too close to {level_type} at {level_price:.6f}"
                    
        return True, "Safe distance from key levels"
    
    def calculate_key_levels(self, symbol: str, candles_by_tf: Dict) -> Dict[str, float]:
        """Calculate support and resistance levels"""
        
        # Check cache first
        cache_key = f"{symbol}_levels"
        if cache_key in self.key_levels_cache:
            cached_time, cached_levels = self.key_levels_cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_levels
                
        levels = {}
        
        # Use 15m candles for key levels
        candles = candles_by_tf.get("15", [])
        if len(candles) < 50:
            return levels
            
        # Get highs and lows
        highs = [float(c['high']) for c in candles[-50:]]
        lows = [float(c['low']) for c in candles[-50:]]
        closes = [float(c['close']) for c in candles[-50:]]
        
        # Recent high/low
        levels["recent_high"] = max(highs[-20:])
        levels["recent_low"] = min(lows[-20:])
        
        # Find local peaks and troughs
        for i in range(10, len(highs) - 10):
            # Local high
            if highs[i] == max(highs[i-5:i+5]):
                levels[f"resistance_{i}"] = highs[i]
                
            # Local low
            if lows[i] == min(lows[i-5:i+5]):
                levels[f"support_{i}"] = lows[i]
                
        # VWAP as key level
        if len(candles) >= 20:
            volumes = [float(c['volume']) for c in candles[-20:]]
            vwap = sum(closes[i] * volumes[i] for i in range(-20, 0)) / sum(volumes)
            levels["vwap"] = vwap
            
        # Cache the results
        self.key_levels_cache[cache_key] = (datetime.now(), levels)
        
        return levels
    
    def check_timeframe_alignment(self, candles_by_tf: Dict, direction: str, 
                                 trade_type: str) -> Tuple[bool, str]:
        """Ensure multiple timeframes agree with the direction"""
        
        # Define required timeframes by trade type
        required_alignment = {
            "Scalp": {"timeframes": ["1", "3", "5"], "min_agree": 2},
            "Intraday": {"timeframes": ["5", "15", "30"], "min_agree": 2},
            "Swing": {"timeframes": ["15", "30", "60"], "min_agree": 3}
        }
        
        config = required_alignment.get(trade_type, required_alignment["Intraday"])
        timeframes = config["timeframes"]
        min_agree = config["min_agree"]
        
        # Check each timeframe
        agreeing_tfs = 0
        disagreeing_tfs = []
        
        for tf in timeframes:
            if tf not in candles_by_tf or len(candles_by_tf[tf]) < 20:
                continue
                
            # Simple trend check using SMA
            candles = candles_by_tf[tf]
            closes = [float(c['close']) for c in candles[-20:]]
            sma_short = np.mean(closes[-5:])
            sma_long = np.mean(closes[-20:])
            
            tf_direction = "Long" if sma_short > sma_long else "Short"
            
            if tf_direction == direction:
                agreeing_tfs += 1
            else:
                disagreeing_tfs.append(f"{tf}m")
                
        if agreeing_tfs < min_agree:
            return False, f"Insufficient TF alignment. Disagreeing: {', '.join(disagreeing_tfs)}"
            
        return True, f"{agreeing_tfs}/{len(timeframes)} timeframes agree"
    
    def check_market_structure(self, candles_by_tf: Dict, trade_type: str) -> Tuple[bool, str]:
        """Check if market structure is suitable for trading"""
        
        # Use appropriate timeframe
        tf = "5" if trade_type == "Scalp" else "15" if trade_type == "Intraday" else "30"
        
        candles = candles_by_tf.get(tf, [])
        if len(candles) < 30:
            return True, "Insufficient data for structure analysis"
            
        # Calculate ATR for volatility check
        atr = self._calculate_atr(candles[-20:])
        if not atr:
            return True, "Could not calculate ATR"
            
        # Check for choppy/ranging conditions
        closes = [float(c['close']) for c in candles[-30:]]
        highest = max(closes)
        lowest = min(closes)
        range_pct = ((highest - lowest) / lowest) * 100
        
        # Calculate average candle size
        avg_candle_size = np.mean([abs(float(c['close']) - float(c['open'])) for c in candles[-20:]])
        avg_candle_pct = (avg_candle_size / closes[-1]) * 100
        
        # Detect choppy market
        if range_pct < 1.0 and avg_candle_pct < 0.1:
            return False, "Market too choppy/tight range"
            
        # Check for clear structure (trending or clean ranges)
        structure_score = self._analyze_structure(candles[-30:])
        
        if structure_score < 0.4:
            return False, "Poor market structure"
            
        return True, "Good market structure"
    
    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> Optional[float]:
        """Calculate ATR"""
        if len(candles) < period + 1:
            return None
            
        true_ranges = []
        for i in range(1, len(candles)):
            high = float(candles[i]['high'])
            low = float(candles[i]['low'])
            prev_close = float(candles[i-1]['close'])
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
            
        return np.mean(true_ranges[-period:]) if true_ranges else None
    
    def _analyze_structure(self, candles: List[Dict]) -> float:
        """Analyze market structure quality (0-1 score)"""
        
        # Check for clear swings
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        
        # Count higher highs/lows and lower highs/lows
        hh_count = 0
        ll_count = 0
        lh_count = 0
        hl_count = 0
        
        for i in range(2, len(candles)):
            # Higher high
            if highs[i] > highs[i-2]:
                hh_count += 1
            else:
                lh_count += 1
                
            # Higher low
            if lows[i] > lows[i-2]:
                hl_count += 1
            else:
                ll_count += 1
                
        # Good structure has consistent patterns
        uptrend_score = min(hh_count, hl_count) / len(candles)
        downtrend_score = min(lh_count, ll_count) / len(candles)
        
        return max(uptrend_score, downtrend_score)
    
    def detect_exhaustion(self, candles_by_tf: Dict, direction: str) -> bool:
        """Detect if price movement is exhausted"""
        
        candles_5m = candles_by_tf.get("5", [])
        if len(candles_5m) < 10:
            return False
            
        # Check for decreasing momentum
        recent_candles = candles_5m[-5:]
        candle_sizes = []
        
        for candle in recent_candles:
            size = abs(float(candle['close']) - float(candle['open']))
            candle_sizes.append(size)
            
        # If candle sizes are decreasing, momentum is slowing
        if all(candle_sizes[i] > candle_sizes[i+1] for i in range(len(candle_sizes)-1)):
            return True
            
        # Check for long wicks indicating rejection
        last_candle = recent_candles[-1]
        high = float(last_candle['high'])
        low = float(last_candle['low'])
        close = float(last_candle['close'])
        open_price = float(last_candle['open'])
        
        body_size = abs(close - open_price)
        total_range = high - low
        
        if total_range > 0:
            body_ratio = body_size / total_range
            
            # Small body with long wicks = exhaustion
            if body_ratio < 0.3:
                return True
                
        return False

# Global validator instance
entry_validator = EntryValidator()
