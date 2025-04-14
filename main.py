import os
import logging
from telegram import Bot
import time
import schedule
import random

# Get environment variables from Railway
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def generate_fake_signal():
types = ['Scalp', 'Swing', 'Meme']
coin = random.choice(['BTC', 'ETH', 'PEPE', 'WIF', 'FLOKI', 'COW'])
trade_type = random.choice(types)
entry = round(random.uniform(0.01, 2.5), 4)
sl = round(entry * random.uniform(0.9, 0.97), 4)
tp1 = round(entry * random.uniform(1.05, 1.1), 4)
tp2 = round(entry * random.uniform(1.15, 1.3), 4)

message = (
f"*{trade_type} Setup Alert*\n"
f"Coin: {coin}/USDT\n"
f"Entry: `{entry}`\n"
f"Stop Loss: `{sl}`\n"
f"TP1: `{tp1}`\n"
f"TP2: `{tp2}`\n"
f"Leverage: `5x`\n"
f"Risk: `2%`\n"
f"Mode: Simulated"
)
return message

def send_signal():
bot = Bot(token=TELEGRAM_BOT_TOKEN)
signal = generate_fake_signal()
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal, parse_mode='Markdown')

def run_schedule():
schedule.every(3).minutes.do(send_signal)
while True:
schedule.run_pending()
time.sleep(1)

if __name__ == '__main__':
logging.basicConfig(level=logging.INFO)
print("Simulated bot running... Sending signals to Telegram every 3 minutes.")
run_schedule()
