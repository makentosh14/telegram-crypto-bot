# auto_reentry.py

from telegram_bot import send_telegram_message
from logger import log, write_log
from score import score_symbol, determine_direction

cooldown_exits = {}
COOLDOWN_CYCLES = 12  # wait ~6m after exit before reentry

def log_exit(symbol, score):
    write_log(f"EXIT LOGGED: {symbol} | Final Score: {score}")
    # You can store this in a pattern or performance memory too
    cooldown_exits[symbol] = COOLDOWN_CYCLES

def update_exit_cooldowns():
    expired = []
    for symbol in cooldown_exits:
        cooldown_exits[symbol] -= 1
        if cooldown_exits[symbol] <= 0:
            expired.append(symbol)
    for symbol in expired:
        del cooldown_exits[symbol]

def should_reenter(symbol, current_score):
    return symbol in cooldown_exits and current_score >= 7.5  # reentry if strong score again

async def handle_reentry(symbol, current_score):
    await send_telegram_message(
        f"🔄 <b>Re-Entry Signal</b> on <b>{symbol}</b>\n"
        f"<b>Score:</b> {current_score} | <b>Status:</b> Cooldown cleared"
    )
    write_log(f"RE-ENTRY SIGNAL: {symbol} | Score: {current_score}")
    log(f"🔄 Reentry triggered for {symbol} | Score = {current_score}")
    del cooldown_exits[symbol]

async def try_reenter(symbol, candles_by_tf, trade_type, direction, entry_price, trailing_pct):
    if cooldown_exits.get(symbol, 0) > 0:
        cooldown_exits[symbol] -= 1
        return False

    score, tf_scores, re_type = score_symbol(symbol, candles_by_tf)
    re_direction = determine_direction(tf_scores)

    if score >= 7.5 and re_type == trade_type and re_direction == direction:
        await send_telegram_message(
            f"🔄 <b>Re-Entry Signal</b> on <b>{symbol}</b>\n"
            f"<b>Score:</b> {score} | <b>Type:</b> {trade_type} | <b>Dir:</b> {direction}"
        )
        write_log(f"REENTRY TRIGGERED: {symbol} | Score: {score} | Type: {trade_type} | Direction: {direction}")
        log(f"🔄 Reentry triggered for {symbol} | Score = {score}")
        del cooldown_exits[symbol]
        return True

    return False
