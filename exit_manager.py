from volume import get_average_volume
from symbol_info import get_precision
from activity_logger import write_log

def calculate_trailing_stop(symbol, entry_price, current_price, direction="long", trigger_pct=0.01, trail_pct=0.005):
    """
    Calculates new SL price using trailing logic once trigger threshold is passed.
    Applies correct rounding precision per symbol.
    """
    precision = get_precision(symbol)

    if direction == "long":
        if current_price > entry_price * (1 + trigger_pct):
            new_sl = round(current_price * (1 - trail_pct), precision)
            write_log(f"🔐 Trailing SL calc for {symbol} (long): new SL = {new_sl}")
            return new_sl
    elif direction == "short":
        if current_price < entry_price * (1 - trigger_pct):
            new_sl = round(current_price * (1 + trail_pct), precision)
            write_log(f"🔐 Trailing SL calc for {symbol} (short): new SL = {new_sl}")
            return new_sl

    return None

def should_trail_stop(symbol, entry_price, current_price, direction="long", candles=None, trigger_pct=0.018, trail_pct=0.009, current_trailing_sl=None):
    """
    Checks if trailing stop should activate:
      - price exceeds trigger threshold
      - volume is at least 1.2x average (optional)
      - SL must improve (never downgrade)
    """
    if candles:
        avg_volume = get_average_volume(candles)
        current_volume = float(candles[-1]['volume'])
        if current_volume < avg_volume * 1.2:
            write_log(f"🔕 Volume too low for trailing: {current_volume:.2f} < 1.2x avg {avg_volume:.2f}")
            return None

    new_sl = calculate_trailing_stop(symbol, entry_price, current_price, direction, trigger_pct, trail_pct)
    if not new_sl:
        return None

    # Only update SL if it's better (tighter)
    if current_trailing_sl:
        if direction == "long" and new_sl <= current_trailing_sl:
            return None
        if direction == "short" and new_sl >= current_trailing_sl:
            return None

    return new_sl

