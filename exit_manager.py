def smart_exit_signal(current_price, entry_price, tp1, tp2, sl, trail_active, last_peak=None):
    if not trail_active:
        if current_price >= tp1:
            return "TP1"
        elif current_price <= sl:
            return "SL"
        else:
            return None
    else:
        if last_peak is None:
            return None
        trail_sl = last_peak * 0.98  # 2% trailing stop
        if current_price <= trail_sl:
            return "Trailing SL"
        return None

def update_peak_price(current_price, last_peak):
    if last_peak is None or current_price > last_peak:
        return current_price
    return last_peak
