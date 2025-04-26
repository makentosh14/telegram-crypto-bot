import datetime
import pytz
from telegram_bot import send_telegram_message
from logger import log

last_report_date = None

# In-memory trade tracking structure
active_trades = {}
daily_stats = {
    "wins": 0,
    "losses": 0,
    "profit": 0.0
}

# Thresholds
SCORE_EXIT_THRESHOLDS = {
    "Scalp": {"min_score": 6, "cycles": 2},
    "Intraday": {"min_score": 6, "cycles": 3},
    "Swing": {"min_score": 5, "cycles": 4}
}

# Called when a trade is triggered
def track_trade(symbol, trade_type, score, direction, price, sl, tp1):
    active_trades[symbol] = {
        "trade_type": trade_type,
        "score_history": [score],
        "direction": direction,
        "entry_price": price,
        "sl": sl,
        "tp1": tp1,
        "cooldown": 0
    }
    log(f"📌 Tracking {symbol} {direction} | Score: {score} | Type: {trade_type}")

# Called on each scan to monitor existing trades
async def monitor_trades(score_data):
    for symbol, data in list(active_trades.items()):
        if symbol not in score_data:
            continue

        current_score = score_data[symbol]["score"]
        trade_type = data["trade_type"]
        direction = data["direction"]
        tf_scores = score_data[symbol]["tf_scores"]

        data["score_history"].append(current_score)
        if len(data["score_history"]) > 10:
            data["score_history"] = data["score_history"][-10:]  # cap memory

        # Volatility / flat alerts
        if current_score < SCORE_EXIT_THRESHOLDS[trade_type]["min_score"]:
            recent = data["score_history"][-SCORE_EXIT_THRESHOLDS[trade_type]["cycles"]:]
            if all(s < SCORE_EXIT_THRESHOLDS[trade_type]["min_score"] for s in recent):
                log(f"⚠️ Score dropped below threshold for {symbol} → Exit suggestion.")
                await send_telegram_message(
                    f"⚠️ <b>Exit Alert</b>\n"
                    f"<b>{symbol}</b> ({direction}) {trade_type}\n"
                    f"Score dropped: {recent}\n"
                    f"Consider exiting early."
                )
                active_trades.pop(symbol)
                continue

        # Score rebound logic
        if len(data["score_history"]) >= 3:
            if data["score_history"][-3] < 6 and current_score > 8:
                await send_telegram_message(
                    f"🔄 <b>Rebound Alert</b>\n"
                    f"<b>{symbol}</b> score dropped then recovered to {current_score}.\n"
                    f"Potential re-entry?"
                )

# Track wins/losses after trade closes
async def log_trade_result(symbol, result: str, profit: float):
    if symbol in active_trades:
        active_trades.pop(symbol)

    if result == "win":
        daily_stats["wins"] += 1
    elif result == "loss":
        daily_stats["losses"] += 1
    daily_stats["profit"] += profit

# Send daily summary
async def send_daily_report():
    global last_report_date
    now = datetime.datetime.now(pytz.timezone("Europe/Amsterdam"))

    if now.hour == 23:
        today = now.date()
        if last_report_date != today:
            message = (
                f"📊 <b>Daily Trade Report</b> ({now.strftime('%Y-%m-%d')})\n"
                f"Wins: <b>{daily_stats['wins']}</b>\n"
                f"Losses: <b>{daily_stats['losses']}</b>\n"
                f"Net Profit: <b>{daily_stats['profit']:.2f} USDT</b>\n"
            )
            await send_telegram_message(message)
            log("✉️ Daily trade report sent.")
            last_report_date = today

            # Reset daily stats
            daily_stats["wins"] = 0
            daily_stats["losses"] = 0
            daily_stats["profit"] = 0.0
