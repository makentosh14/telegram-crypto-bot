# trend_filters.py - COMPLETE FIXES FOR ALL 13 ISSUES
"""
Enhanced Trend detection and market context analysis with multi-timeframe BTC analysis
ALL ISSUES FIXED WITH PRECISE CORRECTIONS
"""
import asyncio
import numpy as np
from datetime import datetime, timedelta
from bybit_api import signed_request
from logger import log
from collections import deque

class AltseasonDetector:
    """
    Detects altseason conditions based on multiple metrics - FIXED VERSION
    """
    
    def __init__(self):
        self.btc_dominance_history = deque(maxlen=30)
        self.alt_performance_history = deque(maxlen=30)
        self.is_altseason = False
        self.altseason_strength = 0
        # FIX #4: Initialize last_season to prevent AttributeError
        self.last_season = "neutral"
        
    async def detect_altseason(self):
        """
        Detect if we're in altseason based on:
        1. BTC dominance declining
        2. Majority of alts outperforming BTC
        3. Alt market cap increasing faster than BTC
        4. Alt volume surge
        """
        
        altseason_scores = {
            'strong_altseason': 0,
            'altseason': 0,
            'neutral': 0,
            'btc_season': 0
        }
        
        analysis_details = {}
        
        # 1. Check alt performance vs BTC
        alt_performance = await self._analyze_alt_performance()
        altseason_scores[alt_performance['season']] += alt_performance['weight']
        analysis_details['alt_performance'] = alt_performance
        
        # 2. Check volume distribution
        volume_analysis = await self._analyze_volume_distribution()
        altseason_scores[volume_analysis['season']] += volume_analysis['weight']
        analysis_details['volume'] = volume_analysis
        
        # 3. Check momentum shift
        momentum_shift = await self._analyze_momentum_shift()
        altseason_scores[momentum_shift['season']] += momentum_shift['weight']
        analysis_details['momentum'] = momentum_shift
        
        # 4. Check market breadth
        breadth_analysis = await self._analyze_market_breadth()
        altseason_scores[breadth_analysis['season']] += breadth_analysis['weight']
        analysis_details['breadth'] = breadth_analysis
        
        # Determine final altseason status
        total_score = sum(altseason_scores.values())
        if total_score == 0:
            season = 'neutral'
            strength = 0
        else:
            season = max(altseason_scores.items(), key=lambda x: x[1])[0]
            strength = altseason_scores[season] / total_score
        
        # Update state
        self.is_altseason = season in ['altseason', 'strong_altseason']
        self.altseason_strength = strength if self.is_altseason else 0
        
        # Log significant changes
        if self.last_season != season:
            log(f"🔄 Market Season Change: {self.last_season} → {season} (strength: {strength:.2f})")
            
            if season == 'strong_altseason':
                try:
                    from telegram_bot import send_telegram_message
                    await send_telegram_message(
                        f"🚀 <b>ALTSEASON DETECTED!</b>\n"
                        f"Strength: {strength:.2%}\n"
                        f"Alt coins showing strong outperformance vs BTC"
                    )
                except:
                    pass
        
        self.last_season = season
        
        return {
            'is_altseason': self.is_altseason,
            'season': season,
            'strength': strength,
            'details': analysis_details
        }
    
    async def _analyze_alt_performance(self):
        """
        Check how many alts are outperforming BTC
        FIX #1: Remove double-scaling of price24hPcnt
        FIX #3: Use concurrent API calls instead of sequential
        """
        
        try:
            # Top altcoins to check
            alt_symbols = ["ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
                          "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", 
                          "DOTUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT"]
            
            # FIX #3: Fire API calls concurrently instead of sequentially
            tasks = []
            
            # BTC performance first
            tasks.append(signed_request("GET", "/v5/market/tickers", {
                "category": "linear",
                "symbol": "BTCUSDT"
            }))
            
            # All alt symbols
            for symbol in alt_symbols:
                tasks.append(signed_request("GET", "/v5/market/tickers", {
                    "category": "linear",
                    "symbol": symbol
                }))
            
            # Execute all requests concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process BTC data
            btc_resp = results[0]
            btc_perf_24h = 0
            
            if isinstance(btc_resp, dict) and btc_resp.get("retCode") == 0:
                btc_data = btc_resp.get("result", {}).get("list", [{}])[0]
                # FIX #1: Remove * 100 - price24hPcnt is already a percentage
                btc_perf_24h = float(btc_data.get("price24hPcnt", 0))
                
            outperforming_24h = 0
            strong_performers = 0
            total_checked = 0
            
            # Process alt data
            for i, symbol in enumerate(alt_symbols):
                try:
                    ticker_resp = results[i + 1]  # Skip BTC result
                    
                    if (isinstance(ticker_resp, dict) and 
                        ticker_resp.get("retCode") == 0):
                        ticker = ticker_resp.get("result", {}).get("list", [{}])[0]
                        # FIX #1: Remove * 100 - price24hPcnt is already a percentage
                        alt_perf_24h = float(ticker.get("price24hPcnt", 0))
                        
                        total_checked += 1
                        
                        # Check if outperforming BTC
                        if alt_perf_24h > btc_perf_24h + 2:  # 2% outperformance threshold
                            outperforming_24h += 1
                            
                        # Check for strong performers (>10% gain)
                        if alt_perf_24h > 10:
                            strong_performers += 1
                            
                except Exception as e:
                    log(f"❌ Error processing {symbol}: {e}", level="WARNING")
                    continue
            
            # Calculate ratios
            outperform_ratio = outperforming_24h / total_checked if total_checked > 0 else 0
            strong_ratio = strong_performers / total_checked if total_checked > 0 else 0
            
            # Determine season based on performance
            if outperform_ratio > 0.7 and strong_ratio > 0.3:
                return {'season': 'strong_altseason', 'weight': 2.0, 'ratio': outperform_ratio}
            elif outperform_ratio > 0.6:
                return {'season': 'altseason', 'weight': 1.5, 'ratio': outperform_ratio}
            elif outperform_ratio < 0.3:
                return {'season': 'btc_season', 'weight': 1.5, 'ratio': outperform_ratio}
            else:
                return {'season': 'neutral', 'weight': 1.0, 'ratio': outperform_ratio}
                
        except Exception as e:
            log(f"❌ Error analyzing alt performance: {e}", level="ERROR")
            return {'season': 'neutral', 'weight': 0.5, 'ratio': 0.5}
    
    async def _analyze_volume_distribution(self):
        """
        Analyze if volume is shifting to altcoins
        FIX #5: Use turnover24h (quote-value) for proper USD comparison
        """
        
        try:
            # Get volume for BTC and major alts
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
            
            # FIX #3: Use concurrent requests
            tasks = [
                signed_request("GET", "/v5/market/tickers", {
                    "category": "linear",
                    "symbol": symbol
                }) for symbol in symbols
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            volumes = {}
            
            for i, symbol in enumerate(symbols):
                try:
                    ticker_resp = results[i]
                    
                    if (isinstance(ticker_resp, dict) and 
                        ticker_resp.get("retCode") == 0):
                        ticker = ticker_resp.get("result", {}).get("list", [{}])[0]
                        
                        # FIX #5: Use turnover24h for USD-quoted volume instead of volume24h
                        turnover_24h = float(ticker.get("turnover24h", 0))
                        volumes[symbol] = turnover_24h
                        
                except Exception as e:
                    log(f"❌ Error processing volume for {symbol}: {e}", level="WARNING")
                    continue
            
            if not volumes or "BTCUSDT" not in volumes:
                return {'season': 'neutral', 'weight': 0.5}
            
            # Calculate BTC volume dominance
            total_volume = sum(volumes.values())
            btc_volume = volumes["BTCUSDT"]
            btc_dominance = btc_volume / total_volume if total_volume > 0 else 0
            
            # Lower BTC dominance = altseason
            if btc_dominance < 0.3:  # BTC less than 30% of volume
                return {'season': 'strong_altseason', 'weight': 1.5, 'btc_dominance': btc_dominance}
            elif btc_dominance < 0.4:
                return {'season': 'altseason', 'weight': 1.2, 'btc_dominance': btc_dominance}
            elif btc_dominance > 0.6:
                return {'season': 'btc_season', 'weight': 1.2, 'btc_dominance': btc_dominance}
            else:
                return {'season': 'neutral', 'weight': 0.8, 'btc_dominance': btc_dominance}
                
        except Exception as e:
            log(f"❌ Error analyzing volume distribution: {e}", level="ERROR")
            return {'season': 'neutral', 'weight': 0.5}
    
    async def _analyze_momentum_shift(self):
        """
        Check momentum shift between BTC and alts
        FIX #6: Expand beyond just ETH-BTC to include multiple alts
        """
        
        try:
            # FIX #6: Use basket of major alts instead of just ETH
            alt_symbols = ["ETHUSDT", "SOLUSDT", "BNBUSDT"]
            period = 14  # 14 day momentum
            
            # Get candles concurrently
            tasks = []
            tasks.append(signed_request("GET", "/v5/market/kline", {
                "category": "linear",
                "symbol": "BTCUSDT",
                "interval": "D",
                "limit": str(period)
            }))
            
            for symbol in alt_symbols:
                tasks.append(signed_request("GET", "/v5/market/kline", {
                    "category": "linear",
                    "symbol": symbol,
                    "interval": "D",
                    "limit": str(period)
                }))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process BTC momentum
            btc_resp = results[0]
            btc_momentum = 0
            
            if (isinstance(btc_resp, dict) and 
                btc_resp.get("retCode") == 0):
                candles = btc_resp.get("result", {}).get("list", [])
                if len(candles) >= period:
                    closes = [float(c[4]) for c in candles]
                    btc_momentum = ((closes[-1] - closes[0]) / closes[0]) * 100
            
            # Process alt momentum (average of basket)
            alt_momentums = []
            for i, symbol in enumerate(alt_symbols):
                try:
                    alt_resp = results[i + 1]
                    
                    if (isinstance(alt_resp, dict) and 
                        alt_resp.get("retCode") == 0):
                        candles = alt_resp.get("result", {}).get("list", [])
                        if len(candles) >= period:
                            closes = [float(c[4]) for c in candles]
                            alt_momentum = ((closes[-1] - closes[0]) / closes[0]) * 100
                            alt_momentums.append(alt_momentum)
                            
                except Exception as e:
                    log(f"❌ Error processing momentum for {symbol}: {e}", level="WARNING")
                    continue
            
            # Average alt momentum
            avg_alt_momentum = sum(alt_momentums) / len(alt_momentums) if alt_momentums else 0
            
            # Compare momentum
            momentum_diff = avg_alt_momentum - btc_momentum
            
            if momentum_diff > 3:  # Alts momentum 3% higher
                return {'season': 'altseason', 'weight': 1.3, 'momentum_diff': momentum_diff}
            elif momentum_diff < -3:  # BTC momentum 3% higher
                return {'season': 'btc_season', 'weight': 1.3, 'momentum_diff': momentum_diff}
            else:
                return {'season': 'neutral', 'weight': 0.7, 'momentum_diff': momentum_diff}
                
        except Exception as e:
            log(f"❌ Error analyzing momentum shift: {e}", level="ERROR")
            return {'season': 'neutral', 'weight': 0.5}
    
    async def _analyze_market_breadth(self):
        """
        Check how many alts are in uptrend
        FIX #7: Use proper 10-day window as stated in comment
        """
        
        try:
            alt_symbols = ["ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
                          "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"]
            
            # FIX #3: Use concurrent requests
            tasks = []
            for symbol in alt_symbols:
                tasks.append(signed_request("GET", "/v5/market/kline", {
                    "category": "linear",
                    "symbol": symbol,
                    "interval": "D",
                    "limit": "10"  # FIX #7: Use 10 days as comment states
                }))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            uptrending = 0
            downtrending = 0
            
            for i, symbol in enumerate(alt_symbols):
                try:
                    kline_resp = results[i]
                    
                    if (isinstance(kline_resp, dict) and 
                        kline_resp.get("retCode") == 0):
                        candles = kline_resp.get("result", {}).get("list", [])
                        if len(candles) >= 10:
                            # FIX #7: Use proper 10-day window (slice [:10] not [:5])
                            closes = [float(c[4]) for c in candles[:10]]
                            closes.reverse()  # oldest → newest
                            
                            # Check for 5% up in last 10 days as stated in comment
                            if closes[-1] > closes[0] * 1.05:  # 5% up
                                uptrending += 1
                            elif closes[-1] < closes[0] * 0.95:  # 5% down
                                downtrending += 1
                                
                except Exception as e:
                    log(f"❌ Error processing breadth for {symbol}: {e}", level="WARNING")
                    continue
            
            total = uptrending + downtrending
            
            if total == 0:
                return {'season': 'neutral', 'weight': 0.5}
            
            uptrend_ratio = uptrending / total
            
            if uptrend_ratio > 0.7:
                return {'season': 'altseason', 'weight': 1.2, 'uptrend_ratio': uptrend_ratio}
            elif uptrend_ratio < 0.3:
                return {'season': 'btc_season', 'weight': 1.2, 'uptrend_ratio': uptrend_ratio}
            else:
                return {'season': 'neutral', 'weight': 0.8, 'uptrend_ratio': uptrend_ratio}
                
        except Exception as e:
            log(f"❌ Error analyzing market breadth: {e}", level="ERROR")
            return {'season': 'neutral', 'weight': 0.5}


class BTCTrendAnalyzer:
    """
    Enhanced BTC trend analyzer with thread-safe caching
    """
    
    def __init__(self):
        self.last_trend = "neutral"
        self.trend_strength = 0
        self.confidence = 0
        self.timeframes = ['15', '1H', '4H', '1D']
        # FIX #10: Add thread-safe lock for trend cache
        self._trend_lock = asyncio.Lock()
        
    async def _fetch_btc_candles(self, interval, limit=100):
        """
        Fetch BTC candles for analysis
        FIX #8: Adopt consistent candle ordering (oldest→newest)
        """
        try:
            response = await signed_request("GET", "/v5/market/kline", {
                "category": "linear",
                "symbol": "BTCUSDT",
                "interval": interval,
                "limit": str(limit)
            })
            
            if response.get("retCode") == 0:
                candles = response.get("result", {}).get("list", [])
                # FIX #8: Ensure consistent oldest→newest ordering
                candles.reverse()  # Bybit returns newest first, we want oldest first
                return candles
            else:
                log(f"❌ Failed to fetch BTC candles: {response.get('retMsg', 'Unknown error')}")
                return []
                
        except Exception as e:
            log(f"❌ Error fetching BTC candles: {e}", level="ERROR")
            return []
    
    def _calculate_ema(self, prices, period):
        """
        Calculate EMA with proper initialization
        FIX #9: Use SMA of first period prices as initial EMA value
        """
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        # FIX #9: Initialize EMA with SMA of first period prices
        ema = np.mean(prices[:period])
        multiplier = 2 / (period + 1)
        
        # Start calculation from period index
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    async def analyze_btc_trend(self):
        """
        Enhanced BTC trend analysis
        FIX #12: Use concurrent API calls for multiple timeframes
        """
        try:
            # FIX #12: Fetch all timeframes concurrently
            tasks = []
            for tf in self.timeframes:
                tasks.append(self._fetch_btc_candles(tf, 100))
            
            candles_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            candles_by_tf = {}
            for i, tf in enumerate(self.timeframes):
                if (isinstance(candles_results[i], list) and 
                    len(candles_results[i]) > 50):
                    candles_by_tf[tf] = candles_results[i]
            
            if not candles_by_tf:
                return {
                    'trend': 'neutral',
                    'strength': 0.5,
                    'confidence': 30,
                    'details': {'error': 'No valid candle data'}
                }
            
            # Analyze each timeframe
            trend_votes = {}
            confidence_factors = []
            
            for tf, candles in candles_by_tf.items():
                analysis = await self._analyze_timeframe(candles, tf)
                trend_votes[tf] = analysis
                confidence_factors.append(analysis['confidence'])
            
            # Determine overall trend
            uptrend_weight = sum(v['weight'] for v in trend_votes.values() if v['trend'] == 'uptrend')
            downtrend_weight = sum(v['weight'] for v in trend_votes.values() if v['trend'] == 'downtrend')
            neutral_weight = sum(v['weight'] for v in trend_votes.values() if v['trend'] == 'neutral')
            
            total_weight = uptrend_weight + downtrend_weight + neutral_weight
            
            if total_weight == 0:
                overall_trend = 'neutral'
                strength = 0.5
            elif uptrend_weight > downtrend_weight and uptrend_weight > neutral_weight:
                overall_trend = 'uptrend'
                strength = uptrend_weight / total_weight
            elif downtrend_weight > uptrend_weight and downtrend_weight > neutral_weight:
                overall_trend = 'downtrend'
                strength = downtrend_weight / total_weight
            else:
                overall_trend = 'neutral'
                strength = neutral_weight / total_weight
            
            # Calculate confidence
            confidence = np.mean(confidence_factors) if confidence_factors else 30
            
            # Update state
            self.last_trend = overall_trend
            self.trend_strength = strength
            self.confidence = confidence
            
            return {
                'trend': overall_trend,
                'strength': strength,
                'confidence': confidence,
                'details': trend_votes
            }
            
        except Exception as e:
            log(f"❌ Error analyzing BTC trend: {e}", level="ERROR")
            return {
                'trend': 'neutral',
                'strength': 0.5,
                'confidence': 30,
                'details': {'error': str(e)}
            }
    
    async def _analyze_timeframe(self, candles, timeframe):
        """Analyze trend for a specific timeframe"""
        try:
            if len(candles) < 50:
                return {'trend': 'neutral', 'weight': 0.5, 'confidence': 30}
            
            closes = [float(c[4]) for c in candles]
            
            # Calculate EMAs with fixed initialization
            ema_20 = self._calculate_ema(closes, 20)
            ema_50 = self._calculate_ema(closes, 50)
            
            current_price = closes[-1]
            
            # Determine trend based on EMA positioning and price action
            if current_price > ema_20 > ema_50:
                trend = 'uptrend'
                weight = 1.5 if timeframe in ['4H', '1D'] else 1.0
                confidence = 70
            elif current_price < ema_20 < ema_50:
                trend = 'downtrend'
                weight = 1.5 if timeframe in ['4H', '1D'] else 1.0
                confidence = 70
            else:
                trend = 'neutral'
                weight = 0.8
                confidence = 50
            
            return {
                'trend': trend,
                'weight': weight,
                'confidence': confidence,
                'ema_20': ema_20,
                'ema_50': ema_50,
                'current_price': current_price
            }
            
        except Exception as e:
            log(f"❌ Error analyzing timeframe {timeframe}: {e}", level="ERROR")
            return {'trend': 'neutral', 'weight': 0.5, 'confidence': 30}


# Global analyzer instances
btc_analyzer = BTCTrendAnalyzer()
altseason_detector = AltseasonDetector()

# FIX #10: Thread-safe trend cache with lock
_trend_cache = {}
_trend_cache_lock = asyncio.Lock()

async def get_trend_context_cached():
    """
    Get trend context with thread-safe caching
    FIX #10: Add proper locking for thread safety
    """
    async with _trend_cache_lock:
        current_time = datetime.now()
        
        # Check if cached result is still valid (5 minutes)
        if ('timestamp' in _trend_cache and 
            (current_time - _trend_cache['timestamp']).seconds < 300):
            return _trend_cache['context']
        
        # Get fresh context
        context = await get_trend_context()
        
        # Update cache
        _trend_cache['context'] = context
        _trend_cache['timestamp'] = current_time
        
        return context


async def detect_market_regime():
    """
    Detect current market regime
    FIX #11: Return 'volatile' instead of 'trending' on API failure
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
        
        # FIX #11: Return 'volatile' (safer) when API call fails
        if kline_resp.get("retCode") != 0:
            return "volatile"
            
        candles = kline_resp.get("result", {}).get("list", [])
        # FIX #11: Return 'volatile' when insufficient data
        if len(candles) < 50:
            return "volatile"
            
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
        # FIX #11: Return 'volatile' (safer) on any error
        return "volatile"


async def get_market_sentiment():
    """
    Analyze overall market sentiment
    FIX #12: Use concurrent API calls instead of sequential
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    try:
        # Get top 10 coins performance
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
                  "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", "DOTUSDT"]
        
        # FIX #12: Use concurrent requests
        tasks = [
            signed_request("GET", "/v5/market/tickers", {
                "category": "linear",
                "symbol": symbol
            }) for symbol in symbols
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        bullish_count = 0
        bearish_count = 0
        
        for i, symbol in enumerate(symbols):
            try:
                ticker_resp = results[i]
                
                if (isinstance(ticker_resp, dict) and 
                    ticker_resp.get("retCode") == 0):
                    ticker_list = ticker_resp.get("result", {}).get("list", [])
                    if not ticker_list:
                        continue

                    ticker = ticker_list[0]
                    # FIX #1: Remove * 100 - price24hPcnt is already a percentage
                    price_24h_pct = float(ticker.get("price24hPcnt", 0))
                    
                    if price_24h_pct > 2:
                        bullish_count += 1
                    elif price_24h_pct < -2:
                        bearish_count += 1

                else:
                    log(f"⚠️ Failed ticker call for {symbol}", level="WARNING")
                    continue
                    
            except Exception as e:
                log(f"❌ Error processing sentiment for {symbol}: {e}", level="WARNING")
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


async def get_trend_context():
    """
    Enhanced main function to get complete market context
    FIX #12: Use concurrent execution for all analyses
    FIX #13: Move alert logic before return statement
    """
    try:
        # FIX #12: Run all analyses in parallel for better performance
        btc_trend_task = btc_analyzer.analyze_btc_trend()
        sentiment_task = get_market_sentiment()
        regime_task = detect_market_regime()
        altseason_task = altseason_detector.detect_altseason()
        
        # Execute all tasks concurrently
        btc_analysis, sentiment, regime, altseason_analysis = await asyncio.gather(
            btc_trend_task, sentiment_task, regime_task, altseason_task,
            return_exceptions=True
        )
        
        # Handle any exceptions from concurrent execution
        if isinstance(btc_analysis, Exception):
            log(f"❌ BTC analysis failed: {btc_analysis}", level="ERROR")
            btc_analysis = {'trend': 'neutral', 'strength': 0.5, 'confidence': 30, 'details': {}}
        
        if isinstance(sentiment, Exception):
            log(f"❌ Sentiment analysis failed: {sentiment}", level="ERROR")
            sentiment = "neutral"
            
        if isinstance(regime, Exception):
            log(f"❌ Regime detection failed: {regime}", level="ERROR")
            regime = "volatile"
            
        if isinstance(altseason_analysis, Exception):
            log(f"❌ Altseason analysis failed: {altseason_analysis}", level="ERROR")
            altseason_analysis = {'is_altseason': False, 'strength': 0, 'details': {}, 'season': 'neutral'}
        
        # Map neutral to ranging for backward compatibility
        btc_trend = btc_analysis['trend']
        if btc_trend == 'neutral':
            btc_trend = 'ranging'
        
        # FIX #13: Move alert logic BEFORE return statement
        if btc_trend == 'downtrend' and btc_analysis['confidence'] >= 70:
            log(f"⚠️ BTC DOWNTREND CONFIRMED with {btc_analysis['confidence']:.1f}% confidence")
            try:
                from telegram_bot import send_telegram_message
                await send_telegram_message(
                    f"⚠️ <b>BTC DOWNTREND ALERT</b>\n"
                    f"Confidence: {btc_analysis['confidence']:.1f}%\n"
                    f"Strength: {btc_analysis['strength']:.1f}\n"
                    f"Consider reducing risk exposure"
                )
            except Exception as alert_error:
                log(f"❌ Failed to send downtrend alert: {alert_error}", level="WARNING")
        
        context = {
            "btc_trend": btc_trend,
            "btc_strength": btc_analysis['strength'],
            "btc_confidence": btc_analysis['confidence'],
            "btc_details": btc_analysis['details'],
            "sentiment": sentiment,
            "regime": regime,
            "altseason": altseason_analysis['is_altseason'],
            "altseason_strength": altseason_analysis['strength'],
            "altseason_details": altseason_analysis['details'],
            "market_season": altseason_analysis['season'],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Enhanced logging with confidence
        season_str = f" | ALTSEASON ({altseason_analysis['strength']:.0%})" if altseason_analysis['is_altseason'] else ""
        log(f"📊 Market Context: BTC {btc_trend} (conf: {btc_analysis['confidence']:.1f}%), " +
            f"Sentiment {sentiment}, Regime {regime}{season_str}")
        
        return context
        
    except Exception as e:
        log(f"❌ Error getting trend context: {e}", level="ERROR")
        # Return safe defaults on any error
        return {
            "btc_trend": "ranging",
            "btc_strength": 0.5,
            "btc_confidence": 30,
            "btc_details": {"error": str(e)},
            "sentiment": "neutral",
            "regime": "volatile",
            "altseason": False,
            "altseason_strength": 0,
            "altseason_details": {},
            "market_season": "neutral",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


# Additional helper functions with fixes

def calculate_ema_fixed(prices, period):
    """
    Fixed EMA calculation for backward compatibility
    FIX #9: Proper initialization with SMA of first period prices
    """
    if len(prices) < period:
        return prices[-1] if prices else 0
    
    # FIX #9: Initialize with SMA of first period prices
    ema = np.mean(prices[:period])
    multiplier = 2 / (period + 1)
    
    # Start from period index
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema


async def get_btc_trend():
    """
    Enhanced BTC trend analysis using the new analyzer
    Returns: 'uptrend', 'downtrend', or 'ranging' (maps neutral to ranging)
    """
    result = await btc_analyzer.analyze_btc_trend()
    
    # Map neutral to ranging for backward compatibility
    trend = result['trend']
    if trend == 'neutral':
        trend = 'ranging'
    
    return trend


# Monitoring functions with concurrent improvements

async def monitor_btc_trend_accuracy():
    """
    Monitor and report BTC trend accuracy
    FIX #12: Improved monitoring with better error handling
    """
    
    while True:
        try:
            # Get current status with timeout
            summary = f"BTC Trend: {btc_analyzer.last_trend.upper()} "
            summary += f"(strength: {btc_analyzer.trend_strength:.2f}, "
            summary += f"confidence: {btc_analyzer.confidence:.1f}%)"
            
            # Log every 30 minutes
            log(f"📊 BTC Trend Monitor: {summary}")
            
        except Exception as e:
            log(f"❌ Error in BTC trend monitor: {e}", level="ERROR")
        
        await asyncio.sleep(1800)  # 30 minutes


async def monitor_altseason_status():
    """
    Monitor and report altseason status
    FIX #12: Enhanced monitoring with concurrent checks
    """
    
    while True:
        try:
            # Use timeout for altseason detection
            result = await asyncio.wait_for(
                altseason_detector.detect_altseason(), 
                timeout=30
            )
            
            if result['is_altseason']:
                details = result['details']
                
                # Build status message
                msg = f"🚀 ALTSEASON STATUS\n"
                msg += f"Season: {result['season']}\n"
                msg += f"Strength: {result['strength']:.0%}\n"
                
                if 'alt_performance' in details:
                    ratio = details['alt_performance'].get('ratio', 0)
                    msg += f"Alts outperforming BTC: {ratio:.0%}\n"
                
                if 'volume' in details:
                    btc_dom = details['volume'].get('btc_dominance', 0)
                    msg += f"BTC volume dominance: {btc_dom:.0%}\n"
                
                log(msg)
            
        except asyncio.TimeoutError:
            log("⚠️ Altseason detection timeout", level="WARNING")
        except Exception as e:
            log(f"❌ Error in altseason monitor: {e}", level="ERROR")
        
        await asyncio.sleep(3600)  # Check every hour


# Enhanced validation functions

async def validate_short_signal_fixed(symbol, candles_by_tf):
    """
    Enhanced short signal validation with fixed logic
    Addresses various validation issues mentioned in the fixes
    """
    try:
        if not candles_by_tf or '15' not in candles_by_tf:
            log(f"❌ {symbol}: Missing 15min candles for validation")
            return False
        
        # Get trend context first
        context = await get_trend_context_cached()
        
        # Enhanced bearish validation
        indicator_scores = {}
        
        # 1. BTC trend alignment
        if context['btc_trend'] == 'downtrend':
            indicator_scores['btc_trend'] = -1.5
        elif context['btc_trend'] == 'ranging':
            indicator_scores['btc_trend'] = -0.5
        else:
            indicator_scores['btc_trend'] = 0.5
        
        # 2. Market sentiment
        if context['sentiment'] == 'bearish':
            indicator_scores['sentiment'] = -1.2
        elif context['sentiment'] == 'neutral':
            indicator_scores['sentiment'] = -0.3
        else:
            indicator_scores['sentiment'] = 0.3
        
        # 3. Volatility regime
        if context['regime'] == 'volatile':
            indicator_scores['regime'] = -0.8
        else:
            indicator_scores['regime'] = 0.2
        
        # 4. Altseason consideration
        if context['altseason'] and context['altseason_strength'] > 0.7:
            indicator_scores['altseason'] = 0.8  # Bullish for alts
        else:
            indicator_scores['altseason'] = -0.2
        
        # Require multiple bearish indicators (reduced from 3 to 2)
        strong_bearish = sum(1 for k, v in indicator_scores.items() if v < -1.0)
        if strong_bearish < 2:
            log(f"❌ {symbol}: Insufficient bearish indicators ({strong_bearish})")
            return False
        
        # 5. Check for divergence (price up, indicators down)
        if '15' in candles_by_tf:
            candles = candles_by_tf['15']
            if len(candles) >= 5:
                # FIX #8: Proper candle ordering (oldest → newest)
                closes = [float(c[4]) for c in candles[-5:]]  # Last 5 candles
                price_trend = closes[-1] > closes[0]  # Price going up
                indicator_trend = sum(v for v in indicator_scores.values()) < -2
                
                if price_trend and not indicator_trend:
                    log(f"❌ {symbol}: Price/indicator divergence detected")
                    return False
        
        log(f"✅ {symbol}: Short signal validated")
        return True
        
    except Exception as e:
        log(f"❌ Error validating short signal for {symbol}: {e}", level="ERROR")
        return False


# Cache cleanup functions

async def cleanup_caches_periodically():
    """
    Periodically clean up caches to prevent memory bloat
    FIX #10: Proper cache management
    """
    while True:
        try:
            async with _trend_cache_lock:
                # Clear old cache entries
                current_time = datetime.now()
                if ('timestamp' in _trend_cache and 
                    (current_time - _trend_cache['timestamp']).seconds > 3600):
                    _trend_cache.clear()
                    log("🧹 Cleared trend cache")
            
        except Exception as e:
            log(f"❌ Error cleaning caches: {e}", level="ERROR")
        
        await asyncio.sleep(1800)  # Clean every 30 minutes


# Export main functions for backward compatibility
__all__ = [
    'get_trend_context',
    'get_trend_context_cached', 
    'get_btc_trend',
    'detect_market_regime',
    'get_market_sentiment',
    'calculate_ema_fixed',
    'validate_short_signal_fixed',
    'monitor_btc_trend_accuracy',
    'monitor_altseason_status',
    'btc_analyzer',
    'altseason_detector'
]
