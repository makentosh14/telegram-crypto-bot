"""
Trend detection and market context analysis
"""
import asyncio
from datetime import datetime, timedelta
from bybit_api import signed_request
from logger import log
import numpy as np

async def get_btc_trend():
    """
    Analyze BTC trend across multiple timeframes
    Returns: 'uptrend', 'downtrend', or 'ranging'
    """
    try:
        # Get BTC candles for multiple timeframes
        timeframes = {
            '15': 50,   # 15min candles, 50 periods
            '60': 50,   # 1h candles, 50 periods  
            '240': 30   # 4h candles, 30 periods
        }
        
        trends = {}
        
        for tf, limit in timeframes.items():
            # Fetch BTC candles
            kline_resp = await signed_request("GET", "/v5/market/kline", {
                "category": "linear",
                "symbol": "BTCUSDT",
                "interval": tf,
                "limit": str(limit)
            })
            
            if kline_resp.get("retCode") != 0:
                log(f"❌ Failed to fetch BTC candles for {tf}m", level="ERROR")
                continue
                
            candles = kline_resp.get("result", {}).get("list", [])
            if len(candles) < 20:
                continue
                
            # Calculate trend for this timeframe
            closes = [float(c[4]) for c in candles]  # Close prices
            closes.reverse()  # Order from oldest to newest
            
            # Simple trend detection using EMAs
            ema_short = calculate_ema(closes, 9)
            ema_long = calculate_ema(closes, 21)
            
            if ema_short > ema_long:
                trends[tf] = "uptrend"
            elif ema_short < ema_long:
                trends[tf] = "downtrend"
            else:
                trends[tf] = "ranging"
        
        # Determine overall trend based on multiple timeframes
        uptrend_count = sum(1 for t in trends.values() if t == "uptrend")
        downtrend_count = sum(1 for t in trends.values() if t == "downtrend")
        
        if uptrend_count >= 2:
            return "uptrend"
        elif downtrend_count >= 2:
            return "downtrend"
        else:
            return "ranging"
            
    except Exception as e:
        log(f"❌ Error calculating BTC trend: {e}", level="ERROR")
        return "ranging"  # Default to neutral

def calculate_ema(prices, period):
    """Simple EMA calculation"""
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
                    continue  # Skip this symbol if no data returned

                ticker = ticker_list[0]
                price_24h_pct = float(ticker.get("price24hPcnt", 0)) * 100
                
                if price_24h_pct > 2:
                    bullish_count += 1
                elif price_24h_pct < -2:
                    bearish_count += 1

            else:
                # Optional: log API error and skip
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
    Main function to get complete market context
    """
    try:
        # Run all analyses in parallel
        btc_trend_task = get_btc_trend()
        sentiment_task = get_market_sentiment()
        regime_task = detect_market_regime()
        
        btc_trend = await btc_trend_task
        sentiment = await sentiment_task
        regime = await regime_task
        
        context = {
            "btc_trend": btc_trend,
            "sentiment": sentiment,
            "regime": regime,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        log(f"📊 Market Context: BTC {btc_trend}, Sentiment {sentiment}, Regime {regime}")
        
        return context
        
    except Exception as e:
        log(f"❌ Error getting trend context: {e}", level="ERROR")
        # Return safe defaults
        return {
            "btc_trend": "ranging",
            "sentiment": "neutral", 
            "regime": "trending",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

# Cache for trend context to avoid too many API calls
_trend_cache = None
_cache_timestamp = None
_cache_ttl = 300  # 5 minutes

async def get_trend_context_cached():
    """Get trend context with caching"""
    global _trend_cache, _cache_timestamp
    
    current_time = datetime.now()
    
    # Use cache if valid
    if _trend_cache and _cache_timestamp:
        if (current_time - _cache_timestamp).seconds < _cache_ttl:
            return _trend_cache
    
    # Fetch fresh data
    context = await get_trend_context()
    _trend_cache = context
    _cache_timestamp = current_time
    
    return context
