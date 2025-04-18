def btc_dominance_filter(btc_dominance, threshold=50):
    """
    Filters altcoin signals based on BTC dominance.
    """
    return btc_dominance < threshold  # Favor altcoins when BTC dominance is lower


def eth_btc_ratio_filter(eth_btc_ratio, min_ratio=0.06):
    """
    Filters for altseason based on ETH/BTC ratio strength.
    """
    return eth_btc_ratio > min_ratio


def is_altseason(btc_dominance, eth_btc_ratio, meme_volume_spike=False):
    """
    Determines if the market is in altseason mode.
    """
    dominance_ok = btc_dominance_filter(btc_dominance)
    eth_ok = eth_btc_ratio_filter(eth_btc_ratio)
    return (dominance_ok and eth_ok) or meme_volume_spike


def detect_market_phase(btc_price_change_24h, btc_dominance_change_24h):
    """
    Detects current market phase: bullish, bearish, or sideways.
    """
    if btc_price_change_24h > 3:
        return "bullish"
    elif btc_price_change_24h < -3:
        return "bearish"
    elif abs(btc_dominance_change_24h) < 0.5:
        return "sideways"
    return "ranging"


def auto_scan_cycle_mode(btc_dominance, eth_btc_ratio, meme_volume_spike, high_volatility_detected):
    """
    Returns recommended scan cycle speed in seconds based on market conditions.
    """
    if is_altseason(btc_dominance, eth_btc_ratio, meme_volume_spike) or high_volatility_detected:
        return 120  # faster scan every 2 mins
    return 180  # normal 3 mins
