# exit_manager.py

def generate_tp_sl(entry_price, side, risk_reward_1=1.5, risk_reward_2=3.0, stop_loss_pct=0.02):
    if side == "buy":
        stop_loss = entry_price * (1 - stop_loss_pct)
        take_profit_1 = entry_price * (1 + risk_reward_1 * stop_loss_pct)
        take_profit_2 = entry_price * (1 + risk_reward_2 * stop_loss_pct)
    else:
        stop_loss = entry_price * (1 + stop_loss_pct)
        take_profit_1 = entry_price * (1 - risk_reward_1 * stop_loss_pct)
        take_profit_2 = entry_price * (1 - risk_reward_2 * stop_loss_pct)

    return round(stop_loss, 6), round(take_profit_1, 6), round(take_profit_2, 6)


def should_trail_stop(current_price, entry_price, side, tp1_hit):
    """
    Logic to activate trailing stop once TP1 is hit.
    If trailing logic is triggered, SL will move to breakeven or higher.
    """
    if not tp1_hit:
        return None

    breakeven = entry_price
    trail_offset = 0.005  # Example: 0.5% below market for long

    if side == "buy":
        trailing_stop = current_price * (1 - trail_offset)
        return max(trailing_stop, breakeven)
    else:
        trailing_stop = current_price * (1 + trail_offset)
        return min(trailing_stop, breakeven)
