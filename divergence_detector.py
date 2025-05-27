# divergence_detector.py - Detect price/indicator divergences

from typing import Optional, Tuple, List, Dict
import numpy as np
from logger import log

class DivergenceDetector:
    """Detect divergences between price and indicators"""
    
    def detect_rsi_divergence(self, candles: List[Dict], rsi_values: List[float], 
                             lookback: int = 14) -> Optional[Dict]:
        """Detect RSI divergence"""
        
        if len(candles) < lookback or len(rsi_values) < lookback:
            return None
            
        # Find price peaks and troughs
        price_peaks, price_troughs = self._find_peaks_and_troughs(
            [float(c['close']) for c in candles[-lookback:]]
        )
        
        # Find RSI peaks and troughs
        rsi_peaks, rsi_troughs = self._find_peaks_and_troughs(rsi_values[-lookback:])
        
        # Check for divergences
        divergence = None
        
        # Bearish divergence: price higher high, RSI lower high
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            if (price_peaks[-1][1] > price_peaks[-2][1] and 
                rsi_peaks[-1][1] < rsi_peaks[-2][1]):
                divergence = {
                    "type": "bearish",
                    "strength": self._calculate_divergence_strength(
                        price_peaks[-2:], rsi_peaks[-2:]
                    ),
                    "indicator": "RSI"
                }
        
        # Bullish divergence: price lower low, RSI higher low
        if not divergence and len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
            if (price_troughs[-1][1] < price_troughs[-2][1] and 
                rsi_troughs[-1][1] > rsi_troughs[-2][1]):
                divergence = {
                    "type": "bullish",
                    "strength": self._calculate_divergence_strength(
                        price_troughs[-2:], rsi_troughs[-2:]
                    ),
                    "indicator": "RSI"
                }
                
        return divergence
    
    def detect_volume_divergence(self, candles: List[Dict], lookback: int = 10) -> Optional[Dict]:
        """Detect price/volume divergence"""
        
        if len(candles) < lookback:
            return None
            
        prices = [float(c['close']) for c in candles[-lookback:]]
        volumes = [float(c['volume']) for c in candles[-lookback:]]
        
        # Calculate trends
        price_trend = np.polyfit(range(len(prices)), prices, 1)[0]
        volume_trend = np.polyfit(range(len(volumes)), volumes, 1)[0]
        
        # Normalize trends
        avg_price = np.mean(prices)
        avg_volume = np.mean(volumes)
        
        price_trend_pct = (price_trend / avg_price) * 100
        volume_trend_pct = (volume_trend / avg_volume) * 100
        
        # Check for divergence
        if abs(price_trend_pct) > 0.5:  # Significant price move
            # Price up, volume down = bearish divergence
            if price_trend_pct > 0.5 and volume_trend_pct < -0.3:
                return {
                    "type": "bearish",
                    "strength": abs(price_trend_pct + volume_trend_pct) / 10,
                    "indicator": "Volume",
                    "details": "Price rising on falling volume"
                }
            # Price down, volume down = bullish divergence
            elif price_trend_pct < -0.5 and volume_trend_pct < -0.3:
                return {
                    "type": "bullish",
                    "strength": abs(price_trend_pct) / 10,
                    "indicator": "Volume",
                    "details": "Price falling on low volume"
                }
                
        return None
    
    def _find_peaks_and_troughs(self, values: List[float]) -> Tuple[List, List]:
        """Find local peaks and troughs in values"""
        
        peaks = []
        troughs = []
        
        for i in range(1, len(values) - 1):
            # Peak
            if values[i] > values[i-1] and values[i] > values[i+1]:
                peaks.append((i, values[i]))
            # Trough
            elif values[i] < values[i-1] and values[i] < values[i+1]:
                troughs.append((i, values[i]))
                
        return peaks, troughs
    
    def _calculate_divergence_strength(self, price_points: List[Tuple], 
                                     indicator_points: List[Tuple]) -> float:
        """Calculate divergence strength (0-1)"""
        
        # Calculate the magnitude of divergence
        price_change = abs(price_points[1][1] - price_points[0][1]) / price_points[0][1]
        indicator_change = abs(indicator_points[1][1] - indicator_points[0][1]) / max(indicator_points[0][1], 1)
        
        # Stronger divergence = larger difference
        divergence_magnitude = abs(price_change - indicator_change)
        
        # Normalize to 0-1 range
        return min(divergence_magnitude * 2, 1.0)

# Global instance
divergence_detector = DivergenceDetector()
