"""
Enhanced Trend detection and market context analysis with multi-timeframe BTC analysis
"""
import asyncio
from datetime import datetime, timedelta
from bybit_api import signed_request
from logger import log
import numpy as np
from collections import deque

class BTCTrendAnalyzer:
    """
    Multi-timeframe BTC trend analyzer with multiple confirmation methods
    """
    
    def __init__(self):
        self.trend_history = deque(maxlen=100)
        self.last_trend = "neutral"
        self.trend_strength = 0
        self.confidence = 50
        
    async def analyze_btc_trend(self):
        """
        Comprehensive BTC trend analysis using multiple methods
        
        Returns:
            dict: {
                'trend': 'uptrend'|'downtrend'|'neutral',
                'strength': 0-1,
                'confidence': 0-100,
                'details': {}
            }
        """
        
        trend_scores = {
            'uptrend': 0,
            'downtrend': 0,
            'neutral': 0
        }
        
        confidence_factors = []
        analysis_details = {}
        
        # Fetch candles for multiple timeframes
        btc_candles_by_tf = await self._fetch_btc_candles()
        
        if not btc_candles_by_tf:
            log("⚠️ Failed to fetch BTC candles, defaulting to neutral trend")
            return {
                'trend': 'neutral',
                'strength': 0,
                'confidence': 0,
                'details': {}
            }
        
        # 1. Moving Average Analysis
        ma_analysis = self._analyze_moving_averages(btc_candles_by_tf)
        trend_scores[ma_analysis['trend']] += ma_analysis['weight']
        confidence_factors.append(ma_analysis['confidence'])
        analysis_details['ma'] = ma_analysis
        
        # 2. Price Action Structure
        structure_analysis = self._analyze_price_structure(btc_candles_by_tf)
        trend_scores[structure_analysis['trend']] += structure_analysis['weight']
        confidence_factors.append(structure_analysis['confidence'])
        analysis_details['structure'] = structure_analysis
        
        # 3. Momentum Analysis
        momentum_analysis = self._analyze_momentum(btc_candles_by_tf)
        trend_scores[momentum_analysis['trend']] += momentum_analysis['weight']
        confidence_factors.append(momentum_analysis['confidence'])
        analysis_details['momentum'] = momentum_analysis
        
        # 4. Volume Analysis
        volume_analysis = self._analyze_volume_trend(btc_candles_by_tf)
        trend_scores[volume_analysis['trend']] += volume_analysis['weight']
        confidence_factors.append(volume_analysis['confidence'])
        analysis_details['volume'] = volume_analysis
        
        # Determine final trend
        total_score = sum(trend_scores.values())
        if total_score == 0:
            final_trend = "neutral"
            trend_strength = 0
        else:
            # Get trend with highest score
            final_trend = max(trend_scores.items(), key=lambda x: x[1])[0]
            trend_strength = trend_scores[final_trend] / total_score
            
            # Require minimum strength for trend confirmation
            if trend_strength < 0.6:  # Less than 60% agreement
                final_trend = "neutral"
                trend_strength = 0.5
        
        # Calculate confidence
        confidence = np.mean(confidence_factors) * 100 if confidence_factors else 50
        
        # Additional validation for downtrend - CRITICAL
        if final_trend == "downtrend":
            # Require higher confirmation for downtrend
            if confidence < 70 or trend_strength < 0.7:
                log("📊 Downtrend signal not strong enough, defaulting to neutral")
                final_trend = "neutral"
                
            # Check recent price action - prevent false downtrends
            if '5' in btc_candles_by_tf and len(btc_candles_by_tf['5']) >= 5:
                recent_candles = btc_candles_by_tf['5'][-5:]
                bullish_candles = sum(1 for c in recent_candles if float(c[4]) > float(c[1]))
                if bullish_candles >= 3:
                    log("📊 Recent bullish candles override downtrend signal")
                    final_trend = "neutral"
        
        # Update history
        self.trend_history.append({
            'timestamp': datetime.now(),
            'trend': final_trend,
            'strength': trend_strength,
            'confidence': confidence
        })
        
        self.last_trend = final_trend
        self.trend_strength = trend_strength
        self.confidence = confidence
        
        # Log trend changes
        if len(self.trend_history) >= 2:
            if self.trend_history[-1]['trend'] != self.trend_history[-2]['trend']:
                log(f"🔄 BTC Trend Change: {self.trend_history[-2]['trend']} → {final_trend} (confidence: {confidence:.1f}%)")
        
        return {
            'trend': final_trend,
            'strength': trend_strength,
            'confidence': confidence,
            'details': analysis_details
        }
    
    async def _fetch_btc_candles(self):
        """Fetch BTC candles for multiple timeframes"""
        timeframes = {
            '5': 50,    # 5min candles
            '15': 50,   # 15min candles
            '60': 50,   # 1h candles
            '240': 30   # 4h candles
        }
        
        btc_candles = {}
        
        for tf, limit in timeframes.items():
            try:
                kline_resp = await signed_request("GET", "/v5/market/kline", {
                    "category": "linear",
                    "symbol": "BTCUSDT",
                    "interval": tf,
                    "limit": str(limit)
                })
                
                if kline_resp.get("retCode") == 0:
                    candles = kline_resp.get("result", {}).get("list", [])
                    if candles:
                        candles.reverse()  # Order from oldest to newest
                        btc_candles[tf] = candles
                        
            except Exception as e:
                log(f"❌ Error fetching BTC {tf}m candles: {e}", level="ERROR")
                
        return btc_candles
    
    def _analyze_moving_averages(self, candles_by_tf):
        """Analyze trend using multiple MAs across timeframes"""
        
        ma_signals = []
        
        # 5-minute MA analysis
        if '5' in candles_by_tf and len(candles_by_tf['5']) >= 50:
            candles = candles_by_tf['5']
            closes = [float(c[4]) for c in candles]
            
            ma20 = np.mean(closes[-20:])
            ma50 = np.mean(closes[-50:])
            current = closes[-1]
            
            # Check alignment
            if current > ma20 > ma50:
                ma_signals.append(('uptrend', 0.8))
            elif current < ma20 < ma50:
                ma_signals.append(('downtrend', 0.8))
            else:
                ma_signals.append(('neutral', 0.5))
        
        # 15-minute MA analysis
        if '15' in candles_by_tf and len(candles_by_tf['15']) >= 50:
            candles = candles_by_tf['15']
            closes = [float(c[4]) for c in candles]
            
            # Use EMA for more responsive signals
            ema9 = self._calculate_ema(closes, 9)
            ema21 = self._calculate_ema(closes, 21)
            ema50 = self._calculate_ema(closes, 50)
            current = closes[-1]
            
            if current > ema9 > ema21 > ema50:
                ma_signals.append(('uptrend', 1.0))
            elif current < ema9 < ema21 < ema50:
                ma_signals.append(('downtrend', 1.0))
            else:
                ma_signals.append(('neutral', 0.6))
        
        # 1-hour MA analysis (most important)
        if '60' in candles_by_tf and len(candles_by_tf['60']) >= 50:
            candles = candles_by_tf['60']
            closes = [float(c[4]) for c in candles]
            
            ma20 = np.mean(closes[-20:])
            ma50 = np.mean(closes[-50:])
            current = closes[-1]
            
            # Check trend strength
            ma_spread = abs(ma20 - ma50) / ma50 * 100
            
            if current > ma20 > ma50 and ma_spread > 0.5:
                ma_signals.append(('uptrend', 1.2))  # Higher weight for HTF
            elif current < ma20 < ma50 and ma_spread > 0.5:
                ma_signals.append(('downtrend', 1.2))
            else:
                ma_signals.append(('neutral', 0.7))
        
        # Aggregate signals
        if not ma_signals:
            return {'trend': 'neutral', 'weight': 0.5, 'confidence': 0.5}
        
        trend_weights = {'uptrend': 0, 'downtrend': 0, 'neutral': 0}
        total_weight = 0
        
        for trend, weight in ma_signals:
            trend_weights[trend] += weight
            total_weight += weight
        
        final_trend = max(trend_weights.items(), key=lambda x: x[1])[0]
        confidence = trend_weights[final_trend] / total_weight
        
        return {
            'trend': final_trend,
            'weight': 2.0,  # MA analysis weight
            'confidence': confidence,
            'signals': ma_signals
        }
    
    def _analyze_price_structure(self, candles_by_tf):
        """Analyze price structure (HH/HL vs LH/LL)"""
        
        structure_signals = []
        
        # Check 15m structure
        if '15' in candles_by_tf and len(candles_by_tf['15']) >= 20:
            candles = candles_by_tf['15'][-20:]
            
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            
            # Find swing points
            swing_highs = []
            swing_lows = []
            
            for i in range(2, len(highs) - 2):
                # Swing high
                if highs[i] > highs[i-1] and highs[i] > highs[i+1] and \
                   highs[i] > highs[i-2] and highs[i] > highs[i+2]:
                    swing_highs.append((i, highs[i]))
                
                # Swing low
                if lows[i] < lows[i-1] and lows[i] < lows[i+1] and \
                   lows[i] < lows[i-2] and lows[i] < lows[i+2]:
                    swing_lows.append((i, lows[i]))
            
            # Analyze structure
            if len(swing_highs) >= 2 and len(swing_lows) >= 2:
                # Check for higher highs and higher lows (uptrend)
                hh = swing_highs[-1][1] > swing_highs[-2][1]
                hl = swing_lows[-1][1] > swing_lows[-2][1]
                
                # Check for lower highs and lower lows (downtrend)
                lh = swing_highs[-1][1] < swing_highs[-2][1]
                ll = swing_lows[-1][1] < swing_lows[-2][1]
                
                if hh and hl:
                    structure_signals.append(('uptrend', 1.0))
                elif lh and ll:
                    structure_signals.append(('downtrend', 1.0))
                else:
                    structure_signals.append(('neutral', 0.5))
        
        # Check 5m micro-structure
        if '5' in candles_by_tf and len(candles_by_tf['5']) >= 10:
            candles = candles_by_tf['5'][-10:]
            
            # Simple structure check
            first_close = float(candles[0][4])
            last_close = float(candles[-1][4])
            mid_close = float(candles[5][4])
            
            if last_close > mid_close > first_close:
                structure_signals.append(('uptrend', 0.7))
            elif last_close < mid_close < first_close:
                structure_signals.append(('downtrend', 0.7))
            else:
                structure_signals.append(('neutral', 0.4))
        
        # Aggregate
        if not structure_signals:
            return {'trend': 'neutral', 'weight': 0.5, 'confidence': 0.5}
        
        trend_weights = {'uptrend': 0, 'downtrend': 0, 'neutral': 0}
        total_weight = 0
        
        for trend, weight in structure_signals:
            trend_weights[trend] += weight
            total_weight += weight
        
        final_trend = max(trend_weights.items(), key=lambda x: x[1])[0]
        confidence = trend_weights[final_trend] / total_weight
        
        return {
            'trend': final_trend,
            'weight': 1.8,  # Structure weight
            'confidence': confidence
        }
    
    def _analyze_momentum(self, candles_by_tf):
        """Analyze momentum indicators"""
        
        momentum_signals = []
        
        # Price momentum for multiple timeframes
        for tf in ['5', '15', '60']:
            if tf in candles_by_tf and len(candles_by_tf[tf]) >= 10:
                candles = candles_by_tf[tf][-10:]
                
                # Calculate rate of change
                first_close = float(candles[0][4])
                last_close = float(candles[-1][4])
                roc = ((last_close - first_close) / first_close) * 100
                
                # Different thresholds for different timeframes
                threshold = {'5': 0.3, '15': 0.5, '60': 1.0}[tf]
                
                if roc > threshold:
                    momentum_signals.append(('uptrend', 0.9))
                elif roc < -threshold:
                    momentum_signals.append(('downtrend', 0.9))
                else:
                    momentum_signals.append(('neutral', 0.5))
        
        # Aggregate
        if not momentum_signals:
            return {'trend': 'neutral', 'weight': 0.5, 'confidence': 0.5}
        
        trend_weights = {'uptrend': 0, 'downtrend': 0, 'neutral': 0}
        total_weight = 0
        
        for trend, weight in momentum_signals:
            trend_weights[trend] += weight
            total_weight += weight
        
        final_trend = max(trend_weights.items(), key=lambda x: x[1])[0]
        confidence = trend_weights[final_trend] / total_weight
        
        return {
            'trend': final_trend,
            'weight': 1.5,  # Momentum weight
            'confidence': confidence
        }
    
    def _analyze_volume_trend(self, candles_by_tf):
        """Analyze volume patterns"""
        
        if '15' not in candles_by_tf or len(candles_by_tf['15']) < 10:
            return {'trend': 'neutral', 'weight': 0.5, 'confidence': 0.5}
        
        candles = candles_by_tf['15'][-10:]
        
        # Separate up and down volume
        up_volume = []
        down_volume = []
        
        for candle in candles:
            close = float(candle[4])
            open_price = float(candle[1])
            volume = float(candle[5])
            
            if close > open_price:
                up_volume.append(volume)
            else:
                down_volume.append(volume)
        
        # Compare volumes
        avg_up_vol = np.mean(up_volume) if up_volume else 0
        avg_down_vol = np.mean(down_volume) if down_volume else 0
        
        if avg_up_vol > avg_down_vol * 1.3:
            return {'trend': 'uptrend', 'weight': 1.2, 'confidence': 0.7}
        elif avg_down_vol > avg_up_vol * 1.3:
            return {'trend': 'downtrend', 'weight': 1.2, 'confidence': 0.7}
        else:
            return {'trend': 'neutral', 'weight': 0.8, 'confidence': 0.5}
    
    def _calculate_ema(self, prices, period):
        """Calculate EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema

# Global analyzer instance
btc_analyzer = BTCTrendAnalyzer()

async def get_btc_trend():
    """
    Enhanced BTC trend analysis using the new analyzer
    Returns: 'uptrend', 'downtrend', or 'neutral' (replaces 'ranging')
    """
    result = await btc_analyzer.analyze_btc_trend()
    
    # Map neutral to ranging for backward compatibility
    trend = result['trend']
    if trend == 'neutral':
        trend = 'ranging'
    
    return trend

def calculate_ema(prices, period):
    """Simple EMA calculation (kept for backward compatibility)"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    
    multiplier = 2 / (period + 1)
    ema = prices[0]
    
    for price in prices[1:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema

async def get_market_sentiment():
    """
    Analyze overall market sentiment
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    try:
        # Get top 10 coins performance
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
                  "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", "DOTUSDT"]
        
        bullish_count = 0
        bearish_count = 0
        
        for symbol in symbols:
            ticker_resp = await signed_request("GET", "/v5/market/tickers", {
                "category": "linear",
                "symbol": symbol
            })
            
            if ticker_resp.get("retCode") == 0:
                ticker_list = ticker_resp.get("result", {}).get("list", [])
                if not ticker_list:
                    continue

                ticker = ticker_list[0]
                price_24h_pct = float(ticker.get("price24hPcnt", 0)) * 100
                
                if price_24h_pct > 2:
                    bullish_count += 1
                elif price_24h_pct < -2:
                    bearish_count += 1

            else:
                log(f"⚠️ Failed ticker call for {symbol}", level="WARNING")
                continue
        
        # Determine sentiment
        if bullish_count >= 6:
            return "bullish"
        elif bearish_count >= 6:
            return "bearish"
        else:
            return "neutral"
            
    except Exception as e:
        log(f"❌ Error calculating market sentiment: {e}", level="ERROR")
        return "neutral"

async def detect_market_regime():
    """
    Detect current market regime
    Returns: 'trending', 'ranging', or 'volatile'
    """
    try:
        # Get BTC volatility data
        kline_resp = await signed_request("GET", "/v5/market/kline", {
            "category": "linear",
            "symbol": "BTCUSDT",
            "interval": "60",
            "limit": "100"
        })
        
        if kline_resp.get("retCode") != 0:
            return "trending"  # Default
            
        candles = kline_resp.get("result", {}).get("list", [])
        if len(candles) < 50:
            return "trending"
            
        # Calculate ATR for volatility
        highs = [float(c[2]) for c in candles[:50]]
        lows = [float(c[3]) for c in candles[:50]]
        closes = [float(c[4]) for c in candles[:50]]
        
        # Simple ATR calculation
        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)
        
        atr = sum(tr_values[-14:]) / 14 if len(tr_values) >= 14 else 0
        atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0
        
        # Determine regime based on volatility
        if atr_pct > 3:
            return "volatile"
        elif atr_pct < 1:
            return "ranging"
        else:
            return "trending"
            
    except Exception as e:
        log(f"❌ Error detecting market regime: {e}", level="ERROR")
        return "trending"

async def get_trend_context():
    """
    Enhanced main function to get complete market context
    """
    try:
        # Run all analyses in parallel
        btc_trend_task = btc_analyzer.analyze_btc_trend()
        sentiment_task = get_market_sentiment()
        regime_task = detect_market_regime()
        
        # Get BTC trend with full details
        btc_analysis = await btc_trend_task
        sentiment = await sentiment_task
        regime = await regime_task
        
        # Map neutral to ranging for backward compatibility
        btc_trend = btc_analysis['trend']
        if btc_trend == 'neutral':
            btc_trend = 'ranging'
        
        context = {
            "btc_trend": btc_trend,
            "btc_strength": btc_analysis['strength'],
            "btc_confidence": btc_analysis['confidence'],
            "btc_details": btc_analysis['details'],
            "sentiment": sentiment,
            "regime": regime,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Enhanced logging with confidence
        log(f"📊 Market Context: BTC {btc_trend} (conf: {btc_analysis['confidence']:.1f}%), " +
            f"Sentiment {sentiment}, Regime {regime}")
        
        # Alert on downtrend confirmation
        if btc_trend == 'downtrend' and btc_analysis['confidence'] >= 70:
            log(f"⚠️ BTC DOWNTREND CONFIRMED with {btc_analysis['confidence']:.1f}% confidence")
        
        return context
        
    except Exception as e:
        log(f"❌ Error getting trend context: {e}", level="ERROR")
        # Return safe defaults
        return {
            "btc_trend": "ranging",
            "btc_strength": 0,
            "btc_confidence": 0,
            "btc_details": {},
            "sentiment": "neutral", 
            "regime": "trending",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

# Cache for trend context to avoid too many API calls
_trend_cache = None
_cache_timestamp = None
_cache_ttl = 300  # 5 minutes

async def get_trend_context_cached():
    """Enhanced get trend context with caching"""
    global _trend_cache, _cache_timestamp
    
    current_time = datetime.now()
    
    # Use cache if valid
    if _trend_cache and _cache_timestamp:
        if (current_time - _cache_timestamp).seconds < _cache_ttl:
            return _trend_cache
    
    # Fetch fresh data
    context = await get_trend_context()
    
    # Log if trend changed
    if _trend_cache and context['btc_trend'] != _trend_cache.get('btc_trend'):
        old_trend = _trend_cache.get('btc_trend')
        new_trend = context['btc_trend']
        confidence = context.get('btc_confidence', 0)
        
        log(f"🔄 BTC Trend Changed: {old_trend} → {new_trend} (confidence: {confidence:.1f}%)")
        
        # Send alert if changed to downtrend with high confidence
        if new_trend == 'downtrend' and confidence >= 70:
            try:
                from telegram_bot import send_telegram_message
                await send_telegram_message(
                    f"⚠️ BTC Trend Alert: Changed to DOWNTREND\n"
                    f"Confidence: {confidence:.1f}%\n"
                    f"Short trades will be enabled"
                )
            except:
                pass
    
    _trend_cache = context
    _cache_timestamp = current_time
    
    return context

def validate_short_signal(symbol, candles_by_tf, trend_context, indicator_scores):
    """
    Strict validation for short signals to prevent false entries
    """
    
    # Get BTC trend details
    btc_trend = trend_context.get('btc_trend', 'neutral')
    btc_confidence = trend_context.get('btc_confidence', 0)
    
    # 1. BTC must be in confirmed downtrend or ranging
    if btc_trend not in ['downtrend', 'ranging']:
        log(f"❌ {symbol}: BTC in {btc_trend}, not suitable for shorts")
        return False
    
    # 2. If downtrend, check confidence
    if btc_trend == 'downtrend' and btc_confidence < 65:
        log(f"❌ {symbol}: BTC downtrend confidence too low ({btc_confidence:.1f}%)")
        return False
    
    # 3. Check immediate price action (last 5 candles) - this is key!
    if '5' in candles_by_tf:
        recent_candles = candles_by_tf['5'][-5:]
        bullish_candles = sum(1 for c in recent_candles if float(c['close']) > float(c['open']))
        
        if bullish_candles > 2:
            log(f"❌ {symbol}: Too many recent bullish candles ({bullish_candles}/5)")
            return False
    
    # 4. Require multiple bearish indicators
    strong_bearish = sum(1 for k, v in indicator_scores.items() if v < -1.0)
    if strong_bearish < 2:  # Reduced from 3 to 2 for more opportunities
        log(f"❌ {symbol}: Insufficient bearish indicators ({strong_bearish})")
        return False
    
    # 5. Check for divergence (price up, indicators down)
    if '15' in candles_by_tf:
        candles = candles_by_tf['15']
        if len(candles) >= 5:
            price_trend = float(candles[-1]['close']) > float(candles[-5]['close'])
            indicator_trend = sum(v for v in indicator_scores.values()) < -2
            
            if price_trend and not indicator_trend:
                log(f"❌ {symbol}: Price/indicator divergence detected")
                return False
    
    log(f"✅ {symbol}: Short signal validated")
    return True

# Add monitoring function
async def monitor_btc_trend_accuracy():
    """Monitor and report BTC trend accuracy"""
    
    while True:
        try:
            # Get current status
            summary = f"BTC Trend: {btc_analyzer.last_trend.upper()} "
            summary += f"(strength: {btc_analyzer.trend_strength:.2f}, "
            summary += f"confidence: {btc_analyzer.confidence:.1f}%)"
            
            # Log every 30 minutes
            log(f"📊 BTC Trend Monitor: {summary}")
            
        except Exception as e:
            log(f"❌ Error in BTC trend monitor: {e}", level="ERROR")
        
        await asyncio.sleep(1800)  # 30 minutes
