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

def should_trail_stop(symbol, entry_price, current_price, direction="long", candles=None, trigger_pct=0.01, trail_pct=0.005):
    """
    Checks if trailing stop should activate, based on:
      - price exceeding the trigger threshold
      - current volume > 1.2x average volume
    Returns new SL price if activated, else None.
    """
    if candles:
        avg_volume = get_average_volume(candles)
        current_volume = float(candles[-1]['volume'])
        if current_volume < avg_volume * 1.2:
            return None  # Not enough volume to justify SL adjustment

    return calculate_trailing_stop(symbol, entry_price, current_price, direction, trigger_pct, trail_pct)
