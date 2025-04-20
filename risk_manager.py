def calculate_position_size(balance, entry_price, stop_loss_price, risk_percent, leverage=1):
    try:
        risk_amount = balance * risk_percent
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance == 0:
            return 0
        quantity = (risk_amount / sl_distance) * leverage
        return round(quantity, 3)
    except Exception as e:
        print(f"[Risk Manager] Error calculating position size: {e}")
        return 0

def adjust_risk_after_losses(trade_history, base_risk_percent, max_daily_loss=0.1):
    losses_today = sum(t['loss'] for t in trade_history if t['date'] == get_today())
    if losses_today >= max_daily_loss:
        return 0  # Bot pauses trading
    elif get_consecutive_losses(trade_history) >= 3:
        return base_risk_percent / 2  # Reduce risk after 3 losses
    return base_risk_percent

def get_consecutive_losses(trades):
    count = 0
    for trade in reversed(trades):
        if trade.get("result") == "loss":
            count += 1
        else:
            break
    return count

def get_today():
    from datetime import datetime
    return datetime.utcnow().strftime('%Y-%m-%d')
