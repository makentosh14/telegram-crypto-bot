import os
import time
import schedule
import datetime
from telegram import Bot

# Setup Telegram bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_TOKEN)

# Core scanning variables
total_scans = 0
total_signals = 0
last_best_trade = None
win_rate = 0
scan_mode = "Normal"
scan_log = []

# Simulated scanner function (placeholder for real logic)
def scan_market():
    global total_scans, total_signals, last_best_trade, win_rate, scan_mode

    total_scans += 5  # Simulates 5 coins scanned per cycle

    # Simulated example of sending a trade signal
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    if total_scans % 30 == 0:
        signal = f"🔥 Trade Signal @ {current_time}\nCoin: *TEST/USDT*\nEntry: 1.23\nSL: 1.10\nTP1: 1.35\nTP2: 1.50\nLeverage: 5x\nConfidence: 8.6/10"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal, parse_mode='Markdown')
        total_signals += 1
        last_best_trade = "TEST +10.5%"

    # Simulate win rate calculation
    if total_signals > 0:
        win_rate = int((total_signals * 0.68))  # Placeholder for real win tracking

# Sends updated bot status to Telegram
def send_status():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = (
        f"📊 *Bot Status*\n"
        f"🕒 Last Scan: {now}\n"
        f"🔁 Coins Scanned: {total_scans}\n"
        f"📈 Signals Sent: {total_signals}\n"
        f"🎯 Win Rate (est): {win_rate}%\n"
        f"💹 Last Best Trade: {last_best_trade or 'N/A'}\n"
        f"⚙️ Scan Mode: {scan_mode}"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status, parse_mode='Markdown')

# Main loop that runs every 3 minutes
def run_schedule():
    schedule.every(3).minutes.do(scan_market)
    schedule.every(15).minutes.do(send_status)

    while True:
        schedule.run_pending()
        time.sleep(1)

# Start the bot
print("Simulated bot running... Sending signals to Telegram every 3 minutes.")
run_schedule()

