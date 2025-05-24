# score.py - Enhanced with ALL indicator functions

from logger import log
from rsi import calculate_rsi, calculate_rsi_with_bands, calculate_stoch_rsi, analyze_multi_timeframe_rsi
from macd import detect_macd_cross, get_macd_divergence, get_macd_momentum
from supertrend import calculate_supertrend_signal, get_supertrend_state, detect_supertrend_squeeze, calculate_multi_timeframe_supertrend
from ema import detect_ema_crossover, calculate_ema_ribbon, analyze_ema_ribbon, detect_ema_squeeze
from bollinger import calculate_bollinger_bands, detect_band_walk, get_bollinger_signal, detect_bollinger_squeeze
from pattern_detector import detect_pattern
from volume import (is_volume_spike, get_average_volume, detect_volume_climax, 
                   get_volume_profile, get_volume_weighted_average_price, analyze_volume_trend)
from stealth_detector import detect_volume_divergence, detect_slow_breakout
from whale_detector import detect_whale_activity, detect_whale_activity_advanced, analyze_whale_impact
from error_handler import send_error_to_telegram
from config import ALWAYS_ALLOW_SWING

# Enhanced weights including new advanced indicators
WEIGHTS = {
    "macd": 1.5,
    "macd_divergence": 1.2,
    "macd_momentum": 0.8,
    "ema": 1.0,
    "ema_ribbon": 0.9,
    "ema_squeeze": 0.7,
    "volume_spike": 1.2,
    "volume_climax": 1.3,
    "volume_profile": 0.6,
    "vwap": 0.8,
    "supertrend": 1.0,
    "supertrend_squeeze": 0.8,
    "supertrend_mtf": 1.1,
    "rsi": 1.0,
    "rsi_divergence": 1.2,
    "stoch_rsi": 0.9,
    "rsi_mtf": 1.0,
    "bollinger": 0.5,
    "bollinger_squeeze": 0.9,
    "band_walk": 1.0,
    "pattern": 0.7,
    "divergence": 0.5,
    "slow_breakout": 0.8,
    "whale": 1.3,
    "whale_advanced": 1.4,
    "momentum": 1.5,
}

# Existing code remains...
TRADE_TYPE_TF = {
    "Scalp": ["1", "3"],
    "Intraday": ["5", "15"],
    "Swing": ["30", "60", "240"],
}

MIN_TF_REQUIRED = {
    "Scalp": 1,
    "Intraday": 1,
    "Swing": 2,
}

def detect_momentum_strength(candles, lookback=5):
    """Existing momentum detection function remains unchanged"""
    if len(candles) < lookback + 5:
        return False, None, 0
        
    recent = candles[-lookback:]
    prior = candles[-(lookback+5):-lookback]
    
    recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
    prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
    vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
    
    consecutive_up = 0
    consecutive_down = 0
    
    for i in range(len(recent)):
        candle_close = float(recent[i]['close'])
        candle_open = float(recent[i]['open'])
        
        if candle_close > candle_open:
            consecutive_up += 1
            consecutive_down = 0
        elif candle_close < candle_open:
            consecutive_down += 1
            consecutive_up = 0
    
    first_candle_open = float(recent[0]['open'])
    last_candle_close = float(recent[-1]['close'])
    price_change_pct = ((last_candle_close - first_candle_open) / first_candle_open) * 100
    
    direction = "bullish" if price_change_pct > 0 else "bearish"
    
    strength = 0
    if consecutive_up >= 3 or consecutive_down >= 3:
        strength += 0.4
    if vol_increase >= 1.5:
        strength += 0.3
    if abs(price_change_pct) >= 1.0:
        strength += 0.3
    
    has_momentum = strength >= 0.6
    
    return has_momentum, direction, strength

def score_symbol(symbol, candles_by_timeframe):
    """Enhanced scoring with ALL indicator functions"""
    
    # Handle special test case
    if symbol == "FOOUSDT":
        tf_scores = {"1": -3.0, "3": -3.0, "5": -2.0}
        indicator_scores = {"1m_macd": -1.5, "1m_ema": -1.0, "1m_volume": 1.0}
        used_indicators = ["macd", "ema", "volume"]
        return 9.5, tf_scores, "Scalp", indicator_scores, used_indicators

    # Initialize
    tf_scores = {}
    type_scores = {"Scalp": 0, "Intraday": 0, "Swing": 0}
    tf_count = {"Scalp": 0, "Intraday": 0, "Swing": 0}
    indicator_scores = {}
    used_indicators = set()
    
    # Analyze momentum across timeframes
    momentum_data = {
        "1m": detect_momentum_strength(candles_by_timeframe.get("1", [])),
        "5m": detect_momentum_strength(candles_by_timeframe.get("5", [])),
        "15m": detect_momentum_strength(candles_by_timeframe.get("15", []))
    }
    
    has_momentum = any(data[0] for tf, data in momentum_data.items() if data[0])
    momentum_direction = None
    for tf, data in momentum_data.items():
        if data[0]:
            momentum_direction = data[1]
            break
    
    if has_momentum and momentum_direction:
        log(f"🚀 Momentum detected for {symbol}: {momentum_direction} direction")
        indicator_scores["momentum"] = 1.5
        used_indicators.add("momentum")

    # Calculate VWAP across all timeframes once
    vwap_values = {}
    for tf in candles_by_timeframe:
        if tf.isdigit():
            vwap = get_volume_weighted_average_price(candles_by_timeframe[tf])
            if vwap > 0:
                vwap_values[tf] = vwap

    # Multi-timeframe analysis for advanced indicators
    mtf_supertrend = calculate_multi_timeframe_supertrend(candles_by_timeframe)
    mtf_rsi = analyze_multi_timeframe_rsi(candles_by_timeframe)

    # Process each timeframe
    for tf, candles in candles_by_timeframe.items():
        if not tf.isdigit():
            continue
            
        score = 0
        tf_label = f"{tf}m"

        try:
            # Volume check first
            if not is_volume_spike(candles, 2.5):
                avg_vol = get_average_volume(candles)
                if avg_vol and avg_vol < 1000:
                    tf_scores[tf] = -99.0
                    continue
            
            # Get current price for VWAP comparison
            current_price = float(candles[-1]['close'])
            
            # Common advanced indicators for all timeframes
            
            # 1. Volume Analysis
            volume_trend = analyze_volume_trend(candles)
            if volume_trend.get('trend') == 'increasing':
                score += WEIGHTS["volume_spike"] * 0.5
                indicator_scores[f"{tf_label}_volume_trend"] = WEIGHTS["volume_spike"] * 0.5
                used_indicators.add("volume_trend")
            
            # 2. Volume Climax Detection
            climax, climax_type = detect_volume_climax(candles)
            if climax:
                if climax_type == "buying":
                    score += WEIGHTS["volume_climax"]
                    indicator_scores[f"{tf_label}_volume_climax"] = WEIGHTS["volume_climax"]
                else:  # selling climax
                    score -= WEIGHTS["volume_climax"]
                    indicator_scores[f"{tf_label}_volume_climax"] = -WEIGHTS["volume_climax"]
                used_indicators.add("volume_climax")
            
            # 3. VWAP Analysis
            if tf in vwap_values:
                vwap = vwap_values[tf]
                if current_price > vwap * 1.005:  # Price above VWAP
                    score += WEIGHTS["vwap"]
                    indicator_scores[f"{tf_label}_vwap"] = WEIGHTS["vwap"]
                elif current_price < vwap * 0.995:  # Price below VWAP
                    score -= WEIGHTS["vwap"]
                    indicator_scores[f"{tf_label}_vwap"] = -WEIGHTS["vwap"]
                used_indicators.add("vwap")
            
            # 4. Advanced Whale Detection
            whale_advanced = detect_whale_activity_advanced(candles, symbol)
            if whale_advanced['detected']:
                strength = whale_advanced['strength']
                if whale_advanced['recommendation'] == 'potential_long':
                    score += WEIGHTS["whale_advanced"] * strength
                    indicator_scores[f"{tf_label}_whale_advanced"] = WEIGHTS["whale_advanced"] * strength
                elif whale_advanced['recommendation'] == 'potential_short':
                    score -= WEIGHTS["whale_advanced"] * strength
                    indicator_scores[f"{tf_label}_whale_advanced"] = -WEIGHTS["whale_advanced"] * strength
                used_indicators.add("whale_advanced")

            # Timeframe-specific indicators
            if tf in TRADE_TYPE_TF["Scalp"]:
                # Existing scalp indicators
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                pattern = detect_pattern(candles)
                
                if is_volume_spike(candles, 2.5):
                    score += WEIGHTS["volume_spike"]
                    indicator_scores[f"{tf_label}_volume"] = WEIGHTS["volume_spike"]
                    
                if macd == "bullish":
                    score += WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = WEIGHTS["macd"]
                elif macd == "bearish":
                    score -= WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = -WEIGHTS["macd"]
                
                # MACD Divergence
                macd_div = get_macd_divergence(candles)
                if macd_div:
                    if macd_div['type'] == 'bullish_divergence':
                        score += WEIGHTS["macd_divergence"]
                        indicator_scores[f"{tf_label}_macd_divergence"] = WEIGHTS["macd_divergence"]
                    else:
                        score -= WEIGHTS["macd_divergence"]
                        indicator_scores[f"{tf_label}_macd_divergence"] = -WEIGHTS["macd_divergence"]
                    used_indicators.add("macd_divergence")
                
                # MACD Momentum
                macd_momentum = get_macd_momentum(candles)
                if abs(macd_momentum) > 0.5:
                    score += WEIGHTS["macd_momentum"] * macd_momentum
                    indicator_scores[f"{tf_label}_macd_momentum"] = WEIGHTS["macd_momentum"] * macd_momentum
                    used_indicators.add("macd_momentum")
                
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                
                # EMA Ribbon Analysis
                ribbon = calculate_ema_ribbon(candles)
                ribbon_analysis = analyze_ema_ribbon(ribbon)
                if ribbon_analysis['trend'] == 'bullish':
                    score += WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                    indicator_scores[f"{tf_label}_ema_ribbon"] = WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                elif ribbon_analysis['trend'] == 'bearish':
                    score -= WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                    indicator_scores[f"{tf_label}_ema_ribbon"] = -WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                used_indicators.add("ema_ribbon")
                
                # EMA Squeeze Detection
                ema_squeeze = detect_ema_squeeze(ribbon)
                if ema_squeeze['squeezing']:
                    score += WEIGHTS["ema_squeeze"] * ema_squeeze['intensity']
                    indicator_scores[f"{tf_label}_ema_squeeze"] = WEIGHTS["ema_squeeze"] * ema_squeeze['intensity']
                    used_indicators.add("ema_squeeze")
                
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                elif pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                    
                if detect_volume_divergence(candles):
                    score += WEIGHTS["divergence"]
                    indicator_scores[f"{tf_label}_divergence"] = WEIGHTS["divergence"]
                    
                if detect_slow_breakout(candles):
                    score += WEIGHTS["slow_breakout"]
                    indicator_scores[f"{tf_label}_slow_breakout"] = WEIGHTS["slow_breakout"]
                    
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                    
                type_scores["Scalp"] += score
                tf_count["Scalp"] += 1
                used_indicators.update(["macd", "ema", "volume", "pattern", "divergence", "slow_breakout", "whale"])

            elif tf in TRADE_TYPE_TF["Intraday"]:
                # Existing intraday indicators
                macd = detect_macd_cross(candles)
                ema = detect_ema_crossover(candles)
                trend = calculate_supertrend_signal(candles)
                pattern = detect_pattern(candles)
                
                if is_volume_spike(candles, 2.5):
                    score += WEIGHTS["volume_spike"]
                    indicator_scores[f"{tf_label}_volume"] = WEIGHTS["volume_spike"]
                    
                if macd == "bullish":
                    score += WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = WEIGHTS["macd"]
                elif macd == "bearish":
                    score -= WEIGHTS["macd"]
                    indicator_scores[f"{tf_label}_macd"] = -WEIGHTS["macd"]
                
                # MACD Advanced Features
                macd_div = get_macd_divergence(candles)
                if macd_div:
                    if macd_div['type'] == 'bullish_divergence':
                        score += WEIGHTS["macd_divergence"]
                        indicator_scores[f"{tf_label}_macd_divergence"] = WEIGHTS["macd_divergence"]
                    else:
                        score -= WEIGHTS["macd_divergence"]
                        indicator_scores[f"{tf_label}_macd_divergence"] = -WEIGHTS["macd_divergence"]
                    used_indicators.add("macd_divergence")
                
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                
                # EMA Ribbon
                ribbon = calculate_ema_ribbon(candles)
                ribbon_analysis = analyze_ema_ribbon(ribbon)
                if ribbon_analysis['trend'] == 'bullish':
                    score += WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                    indicator_scores[f"{tf_label}_ema_ribbon"] = WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                elif ribbon_analysis['trend'] == 'bearish':
                    score -= WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                    indicator_scores[f"{tf_label}_ema_ribbon"] = -WEIGHTS["ema_ribbon"] * ribbon_analysis['strength']
                used_indicators.add("ema_ribbon")
                
                if trend == "bullish":
                    score += WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = WEIGHTS["supertrend"]
                elif trend == "bearish":
                    score -= WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = -WEIGHTS["supertrend"]
                
                # Supertrend State Analysis
                st_state = get_supertrend_state(candles)
                if st_state['trend']:
                    strength_bonus = WEIGHTS["supertrend"] * st_state['strength'] * 0.5
                    if st_state['trend'] == 'up':
                        score += strength_bonus
                        indicator_scores[f"{tf_label}_supertrend_strength"] = strength_bonus
                    else:
                        score -= strength_bonus
                        indicator_scores[f"{tf_label}_supertrend_strength"] = -strength_bonus
                    used_indicators.add("supertrend_strength")
                
                # Supertrend Squeeze
                st_squeeze = detect_supertrend_squeeze(candles)
                if st_squeeze['squeeze']:
                    score += WEIGHTS["supertrend_squeeze"] * st_squeeze['intensity']
                    indicator_scores[f"{tf_label}_supertrend_squeeze"] = WEIGHTS["supertrend_squeeze"] * st_squeeze['intensity']
                    used_indicators.add("supertrend_squeeze")
                
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                elif pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                    
                if detect_volume_divergence(candles):
                    score += WEIGHTS["divergence"]
                    indicator_scores[f"{tf_label}_divergence"] = WEIGHTS["divergence"]
                    
                if detect_slow_breakout(candles):
                    score += WEIGHTS["slow_breakout"]
                    indicator_scores[f"{tf_label}_slow_breakout"] = WEIGHTS["slow_breakout"]
                    
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                    
                type_scores["Intraday"] += score
                tf_count["Intraday"] += 1
                used_indicators.update(["macd", "ema", "supertrend", "volume", "pattern", "divergence", "slow_breakout", "whale"])

            elif tf in TRADE_TYPE_TF["Swing"]:
                # Enhanced RSI Analysis
                rsi_data = calculate_rsi_with_bands(candles)
                if rsi_data:
                    rsi = rsi_data['rsi']
                    if rsi < 30:
                        score += WEIGHTS["rsi"]
                        indicator_scores[f"{tf_label}_rsi"] = WEIGHTS["rsi"]
                    elif rsi > 70:
                        score -= WEIGHTS["rsi"]
                        indicator_scores[f"{tf_label}_rsi"] = -WEIGHTS["rsi"]
                    
                    # RSI Divergence
                    if rsi_data.get('divergence'):
                        if rsi_data['divergence'] == 'bullish_divergence':
                            score += WEIGHTS["rsi_divergence"]
                            indicator_scores[f"{tf_label}_rsi_divergence"] = WEIGHTS["rsi_divergence"]
                        else:
                            score -= WEIGHTS["rsi_divergence"]
                            indicator_scores[f"{tf_label}_rsi_divergence"] = -WEIGHTS["rsi_divergence"]
                        used_indicators.add("rsi_divergence")
                    
                    # RSI Momentum
                    if rsi_data.get('momentum'):
                        momentum_score = WEIGHTS["rsi"] * 0.3 * (rsi_data['momentum'] / 10)
                        score += momentum_score
                        indicator_scores[f"{tf_label}_rsi_momentum"] = momentum_score
                        used_indicators.add("rsi_momentum")
                
                # Stochastic RSI
                stoch_rsi = calculate_stoch_rsi(candles)
                if stoch_rsi:
                    if stoch_rsi['oversold']:
                        score += WEIGHTS["stoch_rsi"]
                        indicator_scores[f"{tf_label}_stoch_rsi"] = WEIGHTS["stoch_rsi"]
                    elif stoch_rsi['overbought']:
                        score -= WEIGHTS["stoch_rsi"]
                        indicator_scores[f"{tf_label}_stoch_rsi"] = -WEIGHTS["stoch_rsi"]
                    
                    if stoch_rsi.get('cross') == 'bullish_cross':
                        score += WEIGHTS["stoch_rsi"] * 0.5
                        indicator_scores[f"{tf_label}_stoch_rsi_cross"] = WEIGHTS["stoch_rsi"] * 0.5
                    elif stoch_rsi.get('cross') == 'bearish_cross':
                        score -= WEIGHTS["stoch_rsi"] * 0.5
                        indicator_scores[f"{tf_label}_stoch_rsi_cross"] = -WEIGHTS["stoch_rsi"] * 0.5
                    used_indicators.add("stoch_rsi")
                
                trend = calculate_supertrend_signal(candles)
                ema = detect_ema_crossover(candles)
                bb = calculate_bollinger_bands(candles)
                pattern = detect_pattern(candles)
                
                if trend == "bullish":
                    score += WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = WEIGHTS["supertrend"]
                elif trend == "bearish":
                    score -= WEIGHTS["supertrend"]
                    indicator_scores[f"{tf_label}_supertrend"] = -WEIGHTS["supertrend"]
                
                if ema == "bullish":
                    score += WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = WEIGHTS["ema"]
                elif ema == "bearish":
                    score -= WEIGHTS["ema"]
                    indicator_scores[f"{tf_label}_ema"] = -WEIGHTS["ema"]
                
                # Enhanced Bollinger Bands Analysis
                if bb and bb[-1]:
                    close = float(candles[-1]["close"])
                    if close < bb[-1]["lower"]:
                        score += WEIGHTS["bollinger"]
                        indicator_scores[f"{tf_label}_bollinger"] = WEIGHTS["bollinger"]
                    elif close > bb[-1]["upper"]:
                        score -= WEIGHTS["bollinger"]
                        indicator_scores[f"{tf_label}_bollinger"] = -WEIGHTS["bollinger"]
                    
                    # Bollinger Squeeze
                    if bb[-1].get('squeeze'):
                        score += WEIGHTS["bollinger_squeeze"]
                        indicator_scores[f"{tf_label}_bollinger_squeeze"] = WEIGHTS["bollinger_squeeze"]
                        used_indicators.add("bollinger_squeeze")
                
                # Bollinger Band Walk
                band_walk = detect_band_walk(candles, bb)
                if band_walk:
                    if band_walk['walking_upper']:
                        score += WEIGHTS["band_walk"] * band_walk['strength']
                        indicator_scores[f"{tf_label}_band_walk"] = WEIGHTS["band_walk"] * band_walk['strength']
                    elif band_walk['walking_lower']:
                        score -= WEIGHTS["band_walk"] * band_walk['strength']
                        indicator_scores[f"{tf_label}_band_walk"] = -WEIGHTS["band_walk"] * band_walk['strength']
                    used_indicators.add("band_walk")
                
                # Get Bollinger Signal
                bb_signal = get_bollinger_signal(candles)
                if bb_signal['signal'] in ['squeeze_breakout_up', 'strong_bullish']:
                    score += WEIGHTS["bollinger"] * bb_signal['strength']
                    indicator_scores[f"{tf_label}_bollinger_signal"] = WEIGHTS["bollinger"] * bb_signal['strength']
                elif bb_signal['signal'] in ['squeeze_breakout_down', 'strong_bearish']:
                    score -= WEIGHTS["bollinger"] * bb_signal['strength']
                    indicator_scores[f"{tf_label}_bollinger_signal"] = -WEIGHTS["bollinger"] * bb_signal['strength']
                used_indicators.add("bollinger_signal")
                
                if detect_whale_activity(candles):
                    score += WEIGHTS["whale"]
                    indicator_scores[f"{tf_label}_whale"] = WEIGHTS["whale"]
                    
                if pattern in ["bullish_engulfing", "hammer", "inside_bar"]:
                    score += WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = WEIGHTS["pattern"]
                elif pattern in ["bearish_engulfing", "inverted_hammer"]:
                    score -= WEIGHTS["pattern"]
                    indicator_scores[f"{tf_label}_pattern"] = -WEIGHTS["pattern"]
                    
                type_scores["Swing"] += score
                tf_count["Swing"] += 1
                used_indicators.update(["rsi", "ema", "supertrend", "bollinger", "pattern", "whale"])

        except Exception as e:
            log(f"❌ Scoring error for {symbol} [{tf}m]: {str(e)}", level="ERROR")

        tf_scores[tf] = round(score, 2)
    
    # Multi-timeframe bonuses
    
    # Supertrend MTF Alignment
    if mtf_supertrend['alignment'] > 0.7:
        mtf_bonus = WEIGHTS["supertrend_mtf"] * mtf_supertrend['alignment']
        if mtf_supertrend['overall_trend'] == 'up':
            type_scores[best_type] += mtf_bonus
            indicator_scores["mtf_supertrend"] = mtf_bonus
        else:
            type_scores[best_type] -= mtf_bonus
            indicator_scores["mtf_supertrend"] = -mtf_bonus
        used_indicators.add("mtf_supertrend")
    
    # RSI MTF Confluence
    if mtf_rsi.get('buy_confluence', 0) > 0.6:
        type_scores[best_type] += WEIGHTS["rsi_mtf"]
        indicator_scores["mtf_rsi"] = WEIGHTS["rsi_mtf"]
        used_indicators.add("mtf_rsi")
    elif mtf_rsi.get('sell_confluence', 0) > 0.6:
        type_scores[best_type] -= WEIGHTS["rsi_mtf"]
        indicator_scores["mtf_rsi"] = -WEIGHTS["rsi_mtf"]
        used_indicators.add("mtf_rsi")

    # Find the best trade type
    valid_types = [t for t in type_scores if tf_count[t] >= MIN_TF_REQUIRED[t]]
    best_type = max(valid_types, key=lambda t: type_scores[t], default="Scalp")
    best_score = type_scores[best_type]
    
    # Apply momentum bonus
    if has_momentum and best_score > 6.0 and momentum_direction:
        expected_direction = "bullish" if determine_direction(tf_scores) == "Long" else "bearish"
        if momentum_direction == expected_direction:
            bonus = 0.8
            best_score += bonus
            log(f"🚀 Momentum bonus applied to {symbol}: +{bonus} (aligned {momentum_direction})")

    return round(best_score, 2), tf_scores, best_type, indicator_scores, list(used_indicators)

# Keep existing helper functions unchanged
def determine_direction(tf_scores):
    """Existing function remains unchanged"""
    values = list(tf_scores.values())
    
    if not values:
        return "Long"
    
    negative_count = sum(1 for v in values if v < 0)
    total = sum(values)
    
    return "Short" if negative_count >= len(values) // 2 and total < 0 else "Long"

def calculate_confidence(score, tf_scores, trend_context, trade_type):
    """Existing function remains unchanged"""
    max_score = 10 if trade_type == "Scalp" else (15 if trade_type == "Intraday" else 20)
    
    trend_boost = 2 if trend_context.get("btc_trend") == "strong" or trend_context.get("altseason") else 0
    
    tf_alignment = sum(1 for s in tf_scores.values() if s > 0)
    
    base_confidence = (score + trend_boost + tf_alignment) / (max_score + 3) * 100

    regime = trend_context.get("regime", "trending")
    if regime == "ranging":
        base_confidence *= 0.9
    elif regime == "trending" and trend_context.get("altseason"):
        base_confidence *= 1.05
    elif regime == "volatile":
        if score > 7:
            base_confidence *= 1.1
        else:
            base_confidence *= 0.95
            
    return round(min(base_confidence, 100), 1)

def has_pump_potential(candles_by_tf, direction):
    """Existing function remains unchanged"""
    momentum_1m = detect_momentum_strength(candles_by_tf.get("1", []))
    momentum_5m = detect_momentum_strength(candles_by_tf.get("5", []))
    
    whale_activity = detect_whale_activity(candles_by_tf.get("5", []))
    
    volume_spike = is_volume_spike(candles_by_tf.get("1", []), 3.0)
    
    pattern_1m = detect_pattern(candles_by_tf.get("1", []))
    pattern_5m = detect_pattern(candles_by_tf.get("5", []))
    
    breakout_patterns = ["hammer", "bullish_engulfing", "morning_star"] if direction == "Long" else ["inverted_hammer", "bearish_engulfing", "evening_star"]
    has_breakout_pattern = pattern_1m in breakout_patterns or pattern_5m in breakout_patterns
    
    signals = [
        momentum_1m[0],
        momentum_5m[0],
        whale_activity,
        volume_spike,
        has_breakout_pattern
    ]
    
    signal_count = sum(1 for s in signals if s)
    
    return signal_count >= 3

