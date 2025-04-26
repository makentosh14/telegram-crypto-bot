# sl_tp_utils.py (ATR-based Dynamic SL Strategy)

import numpy as np

def calculate_atr(candles, period=14):
    """Calculate the Average True Range (ATR) from candles."""
    if len(candles) < period + 1:
        return None

    highs = np.array([float(c['high']) for c in candles[-(period+1):]])
    lows = np.array([float(c['low']) for c in candles[-(period+1):]])
    closes = np.array([float(c['close']) for c in candles[-(period+1):]])

    tr_list = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)

    atr = np.mean(tr_list)
    return round(atr, 4)

def calculate_dynamic_sl_tp(candles_by_tf, entry_price, trade_type, direction, score, confidence):
    """Calculate dynamic SL/TP using ATR, entry price, and trade confidence."""
    tf = '3' if trade_type == "Scalp" else ('15' if trade_type == "Intraday" else '60')
    candles = candles_by_tf.get(tf)
    if not candles:
        return None, None, 1.5, 0.5  # fallback static SL/TP if no candles available

    atr = calculate_atr(candles)
    if atr is None:
        return None, None, 1.5, 0.5

    factor = 1.2 if confidence > 75 else (1.5 if confidence > 60 else 1.8)
    sl_pct = (atr / entry_price) * 100 * factor

    if trade_type == "Scalp":
        tp1_pct = 1.5
        trailing_pct = 0.4
    elif trade_type == "Intraday":
        tp1_pct = 3.0
        trailing_pct = 0.7
    else:  # Swing
        tp1_pct = 6.0
        trailing_pct = 1.2

    if direction == "Long":
        sl = round(entry_price * (1 - sl_pct / 100), 4)
        tp1 = round(entry_price * (1 + tp1_pct / 100), 4)
    else:
        sl = round(entry_price * (1 + sl_pct / 100), 4)
        tp1 = round(entry_price * (1 - tp1_pct / 100), 4)

    return sl, tp1, round(sl_pct, 2), trailing_pct
