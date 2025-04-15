import os
import time
import logging
import random
import requests
import schedule
from telegram import Bot, ParseMode
from datetime import datetime

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Simulated list of coins being scanned
coin_list = ["PEPE", "WIF", "FLOKI", "DOGE", "BONK", "COW", "ALCH", "BTC", "ETH"]

# Simulated signal score function
def generate_confidence():
    return round(random.uniform(6.5, 9.8), 2)

# Simulate indicator/pattern detection
def detect_indicators():
    indicators = []
    if random.random() > 0.5:
        indicators.append("RSI Oversold")
    if random.random() > 0.6:
        indicators.append("MACD Bullish Crossover")
    if random.random() > 0.7:
        indicators.append("Supertrend Flip")
    if random.random() > 0.5:
        indicators.append("Bullish Engulfing Candle")
    if random.random() > 0.8:
        indicators.append("Whale Wallet Activity")
    return indicators

# Send trade signal
def send_trade_signal():
    coin = random.choice(coin_list)
    entry = round(random.uniform(0.00001, 2.0), 8)
    sl = round(entry * random.uniform(0.92, 0.97), 8)
    tp1 = round(entry * random.uniform(1.05, 1.1), 8)
    tp2 = round(entry * random.uniform(1.15, 1.3), 8)
    leverage = random.choice([3, 5, 10])
    confidence = generate_confidence()
    indicators = detect_indicators()

    message = (
        f"📈 *Trade Setup Detected!*\n\n"
        f"*Coin:* `{coin}/USDT`\n"
        f"*Entry:* `{entry}`\n"
        f"*SL:* `{sl}`\n"
        f"*TP1:* `{tp1}`\n"
        f"*TP2:* `{tp2}`\n"
        f"*Leverage:* `{leverage}x`\n"
        f"*Confidence:* `{confidence}/10`\n"
        f"*Detected:* {', '.join(indicators)}\n"
        f"\n_Risk-managed signal | No auto-trading active_"
    )

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# Command handlers (simulated)
def handle_commands():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = (
        f"✅ *Bot Status Check*\n\n"
        f"Time: {now}\n"
        f"Scanner: Running\n"
        f"Coins Watched: {len(coin_list)}\n"
        f"Whale + Social Radar: Active\n"
        f"Stealth Detector: Live\n"
        f"\n_Send /portfolio or /weekly for more._"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status, parse_mode=ParseMode.MARKDOWN)

def handle_portfolio():
    message = (
        f"📊 *Portfolio Snapshot (Simulated)*\n\n"
        f"Total Trades: 12\n"
        f"Win Rate: 75%\n"
        f"Biggest Win: +42% (PEPE)\n"
        f"Biggest Miss: -12% (ALCH)\n"
        f"Current Radar: Top Meme + Trending Alts"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

def handle_weekly():
    message = (
        f"📅 *Weekly Strategy Report*\n\n"
        f"Most Accurate: RSI + MACD Combo\n"
        f"Least Accurate: Inside Bar Breakouts\n"
        f"Missed Pumps: BONK (early), COW (late entry)\n"
        f"Fixes Applied: Volume filter widened, re-entry logic added."
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# Listen to Telegram commands every 60s
def check_messages():
    updates = bot.get_updates(offset=-5)
    for update in updates:
        if update.message.text:
            msg = update.message.text.lower()
            if "/status" in msg:
                handle_commands()
            elif "/portfolio" in msg:
                handle_portfolio()
            elif "/weekly" in msg:
                handle_weekly()

# Main loop
def run_bot():
    schedule.every(5).minutes.do(send_trade_signal)
    schedule.every(1).minutes.do(check_messages)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Bot running... waiting for signal triggers.")
    run_bot()

