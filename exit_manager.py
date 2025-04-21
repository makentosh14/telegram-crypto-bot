# exit_manager.py

def calculate_trailing_stop(entry_price, current_price, direction="long", trigger_pct=0.01, trail_pct=0.005):
    """
    Calculates dynamic SL price using trailing logic.
    """
    if direction == "long":
        move_up = current_price > entry_price * (1 + trigger_pct)
        if move_up:
            return round(current_price * (1 - trail_pct), 2)
    elif direction == "short":
        move_down = current_price < entry_price * (1 - trigger_pct)
        if move_down:
            return round(current_price * (1 + trail_pct), 2)
    return None

def should_trail_stop(entry_price, current_price, direction="long", volume=None, avg_volume=None):
    """
    Determines whether to activate trailing stop-loss.
    Only triggers if:
      1. Price has moved far enough
      2. Volume confirms (current > 1.2x avg)
    """
    if volume and avg_volume:
        if volume < avg_volume * 1.2:
            return False  # Wait for breakout volume
    return calculate_trailing_stop(entry_price, current_price, direction) is not None
