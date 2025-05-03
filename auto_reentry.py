# auto_reentry.py

from telegram_bot import send_telegram_message
from activity_logger import write_log

recent_exits = {}  # symbol: {"score": float, "cooldown": int}
REENTRY_THRESHOLD = 2.0  # points score must rebound by
REENTRY_COOLDOWN = 6  # cycles to wait after exit before checking for re-entry

def log_exit(symbol, exit_score):
    recent_exits[symbol] = {"score": exit_score, "cooldown": REENTRY_COOLDOWN}
    write_log(f"🛑 Exit logged for {symbol} | Score: {exit_score}")

def update_exit_cooldowns():
    for symbol in list(recent_exits):
        recent_exits[symbol]["cooldown"] -= 1
        if recent_exits[symbol]["cooldown"] <= 0:
            del recent_exits[symbol]

def should_reenter(symbol, current_score):
    if symbol not in recent_exits:
        return False
    previous = recent_exits[symbol]
    rebound = current_score - previous["score"]
    if rebound >= REENTRY_THRESHOLD:
        write_log(f"🔁 Re-entry trigger: {symbol} | Score rebound: {rebound:.2f}")
        return True
    return False

async def handle_reentry(symbol, score):
    await send_telegram_message(
        f"🔁 <b>Re-Entry Opportunity</b> for <b>{symbol}</b>\n"
        f"<b>Score:</b> {score} (rebounded from exit)\n"
        f"<i>Watch for new entry signal or manually consider re-buying.</i>"
    )
    write_log(f"🔁 Re-entry alert sent for {symbol} | New Score: {score}")
