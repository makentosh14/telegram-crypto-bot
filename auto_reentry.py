# auto_reentry.py

from telegram_bot import send_telegram_message
from logger import log, write_log
from score import score_symbol, determine_direction

cooldown_exits = {}
COOLDOWN_CYCLES = 12  # wait 6m after exit before reentry

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
        return True

    return False

def log_exit(symbol):
    cooldown_exits[symbol] = COOLDOWN_CYCLES
