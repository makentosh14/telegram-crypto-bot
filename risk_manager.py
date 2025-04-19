def calculate_position_size(balance, entry_price, stop_loss_price, risk_per_trade):
    if entry_price == stop_loss_price:
        return 0  # avoid division by zero

    risk_amount = balance * risk_per_trade
    position_size = risk_amount / abs(entry_price - stop_loss_price)
    return round(position_size, 3)


def adjust_risk_based_on_context(base_risk, btc_trend, altseason):
    if btc_trend == 'downtrend':
        return base_risk * 0.5
    elif altseason:
        return base_risk * 1.5
    else:
        return base_risk


def smart_dynamic_risk(recent_win_rate, base_risk):
    if recent_win_rate >= 0.7:
        return base_risk * 1.2
    elif recent_win_rate <= 0.4:
        return base_risk * 0.6
    else:
        return base_risk
