def generate_tp_sl(entry_price, direction, atr=0.01):
    if direction == "long":
        tp1 = round(entry_price * (1 + 0.015), 6)
        tp2 = round(entry_price * (1 + 0.03), 6)
        sl = round(entry_price * (1 - atr), 6)
    else:
        tp1 = round(entry_price * (1 - 0.015), 6)
        tp2 = round(entry_price * (1 - 0.03), 6)
        sl = round(entry_price * (1 + atr), 6)

    return {
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
    }


def smart_trailing_stop(price, current_sl, direction, buffer=0.005):
    if direction == "long":
        new_sl = round(price * (1 - buffer), 6)
        return new_sl if new_sl > current_sl else current_sl
    else:
        new_sl = round(price * (1 + buffer), 6)
        return new_sl if new_sl < current_sl else current_sl
