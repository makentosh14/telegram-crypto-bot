from bybit_api import get_balance

DEFAULT_BALANCE = 500  # fallback
DEFAULT_RISK = 0.02  # default 2% risk

def calculate_position_size(symbol, entry_price, stop_loss_price, risk_pct=DEFAULT_RISK):
    try:
        balance = get_balance()
    except Exception:
        balance = DEFAULT_BALANCE

    risk_amount = balance * risk_pct
    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance == 0:
        return 0

    qty = round(risk_amount / sl_distance, 3)
    return qty
