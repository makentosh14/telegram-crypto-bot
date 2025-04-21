# exit_manager.py

def calculate_trailing_stop(entry_price, current_price, direction="long", trigger_pct=0.01, trail_pct=0.005):
    """
    Calculates a dynamic stop-loss price based on trailing logic.
    """
    if direction == "long":
        move_up = current_price > entry_price * (1 + trigger_pct)
        if move_up:
            sl_price = current_price * (1 - trail_pct)
            return round(sl_price, 2)
    elif direction == "short":
        move_down = current_price < entry_price * (1 - trigger_pct)
        if move_down:
            sl_price = current_price * (1 + trail_pct)
            return round(sl_price, 2)
    return None

def should_trail_stop(entry_price, current_price, direction="long"):
    """
    Determines whether to activate trailing logic.
    """
    return calculate_trailing_stop(entry_price, current_price, direction) is not None
