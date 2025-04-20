def generate_tp_sl(entry_price, direction='long'):
    tp1 = round(entry_price * 1.02, 4) if direction == 'long' else round(entry_price * 0.98, 4)
    tp2 = round(entry_price * 1.04, 4) if direction == 'long' else round(entry_price * 0.96, 4)
    sl = round(entry_price * 0.985, 4) if direction == 'long' else round(entry_price * 1.015, 4)
    return tp1, tp2, sl

def adjust_stop_to_breakeven(entry_price, current_price, sl, direction='long'):
    if direction == 'long' and current_price >= entry_price * 1.02:
        return max(sl, entry_price)
    elif direction == 'short' and current_price <= entry_price * 0.98:
        return min(sl, entry_price)
    return sl

def apply_trailing_stop(entry_price, current_price, sl, direction='long'):
    # Simple trailing logic: move SL up as price moves up
    if direction == 'long':
        gain = current_price - entry_price
        if gain > 0:
            new_sl = entry_price + gain * 0.5
            return max(sl, round(new_sl, 4))
    else:
        gain = entry_price - current_price
        if gain > 0:
            new_sl = entry_price - gain * 0.5
            return min(sl, round(new_sl, 4))
    return sl
