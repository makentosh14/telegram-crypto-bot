# risk_manager.py

from config import RISK_SPOT, RISK_FUTURES, DAILY_MAX_LOSS
from logger import log

# Daily risk tracking
daily_loss_count = 0
daily_loss_total = 0
paused_due_to_loss = False

def get_risk(symbol, is_altseason=False):
    """
    Returns risk % for a given symbol. Spot and futures have different defaults.
    Boosts risk if altseason flag is enabled.
    """
    risk = RISK_SPOT if symbol.startswith("SPOT_") else RISK_FUTURES
    if is_altseason:
        risk *= 1.5  # Boost risk in altseason
    return round(risk, 4)

def register_loss(symbol, loss_amount, balance):
    """
    Register a trade loss and check if daily max loss has been hit.
    If hit, pause further trading.
    """
    global daily_loss_count, daily_loss_total, paused_due_to_loss

    daily_loss_count += 1
    daily_loss_total += loss_amount

    if balance > 0 and (daily_loss_total / balance) >= DAILY_MAX_LOSS:
        paused_due_to_loss = True
        log("🛑 Trading paused due to hitting daily loss cap!", level="ALERT")

def reset_risk_day():
    """
    Resets daily loss counters. Call at start of new trading day.
    """
    global daily_loss_count, daily_loss_total, paused_due_to_loss
    daily_loss_count = 0
    daily_loss_total = 0
    paused_due_to_loss = False

def is_trading_paused():
    return paused_due_to_loss
