# monitor_report.py

import datetime
import pytz
from telegram_bot import send_telegram_message
from logger import log

# Track daily performance in memory (can be expanded to persist)
daily_stats = {
    "wins": 0,
    "losses": 0,
    "profit": 0.0
}

def log_trade_result(win: bool, profit: float):
    if win:
        daily_stats["wins"] += 1
    else:
        daily_stats["losses"] += 1
    daily_stats["profit"] += profit

async def send_daily_report():
    now = datetime.datetime.now(pytz.timezone("Europe/Amsterdam"))
    if now.hour == 23:
        message = (
            f"📊 <b>Daily Trade Report</b> ({now.strftime('%Y-%m-%d')})\n"
            f"Wins: <b>{daily_stats['wins']}</b>\n"
            f"Losses: <b>{daily_stats['losses']}</b>\n"
            f"Net Profit: <b>{daily_stats['profit']:.2f} USDT</b>\n"
        )
        await send_telegram_message(message)
        log("✉️ Daily trade report sent.")

        # Reset stats after sending
        daily_stats["wins"] = 0
        daily_stats["losses"] = 0
        daily_stats["profit"] = 0.0
