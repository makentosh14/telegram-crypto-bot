from config import RISK_SPOT, RISK_FUTURES, DAILY_MAX_LOSS
from logger import log
from strategy_performance import get_strategy_stats

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

def calculate_dynamic_risk(symbol, confidence, strategy_name, base_risk_pct):
    """
    Adjusts risk % based on confidence score and strategy win rate
    """
    risk = base_risk_pct

    # Confidence-based adjustment
    if confidence >= 85:
        risk *= 1.2
    elif confidence < 60:
        risk *= 0.6

    # Strategy win rate adjustment
    stats = get_strategy_stats(strategy_name)
    win_rate = stats.get("win_rate", 50)

    if win_rate >= 70:
        risk *= 1.15
    elif win_rate <= 40:
        risk *= 0.7

    # Apply altseason multiplier if needed
    if symbol.startswith("SPOT_ALTSEASON_"):
        risk *= 1.25

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
