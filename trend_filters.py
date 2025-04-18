def is_btc_uptrend(btc_candles):
    if not btc_candles or len(btc_candles) < 20:
        return False
    closes = [float(c['close']) for c in btc_candles]
    return closes[-1] > sum(closes[-20:]) / 20

def is_btc_downtrend(btc_candles):
    if not btc_candles or len(btc_candles) < 20:
        return False
    closes = [float(c['close']) for c in btc_candles]
    return closes[-1] < sum(closes[-20:]) / 20

def is_altseason(eth_btc_ratio, btc_dominance, meme_volume):
    if eth_btc_ratio > 0.065 and btc_dominance < 50 and meme_volume > 50000000:
        return True
    return False

def get_trend_summary(btc_candles, eth_btc_ratio, btc_dominance, meme_volume):
    trend = []
    if is_btc_uptrend(btc_candles):
        trend.append("BTC UP")
    if is_btc_downtrend(btc_candles):
        trend.append("BTC DOWN")
    if is_altseason(eth_btc_ratio, btc_dominance, meme_volume):
        trend.append("ALTSEASON")
    return ", ".join(trend) if trend else "Neutral"
