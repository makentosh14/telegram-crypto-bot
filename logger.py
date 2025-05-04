# logger.py

import datetime
import asyncio
import os
import sys
import aiohttp
from config import TELEGRAM_ASSISTANT_CHAT_ID, TELEGRAM_BOT_TOKEN

# ✅ Unified log path (used across bot)
LOG_PATH = "/mnt/data/bot_logs"
LOG_FILE = os.path.join(LOG_PATH, "trading_bot_activity.log")

# Ensure log directory exists
os.makedirs(LOG_PATH, exist_ok=True)

def log(msg, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{timestamp}] [{level}] {msg}")
    except UnicodeEncodeError:
        print(f"[{timestamp}] [{level}] {msg.encode('utf-8', 'ignore').decode('utf-8')}", file=sys.stderr)

    # Log to file
    write_log(msg, level)

    # Send to assistant Telegram if level is ERROR/ALERT
    if TELEGRAM_ASSISTANT_CHAT_ID and level in ["ERROR", "ALERT"]:
        asyncio.create_task(send_assistant_log(msg))

def write_log(message, level="INFO"):
    """
    Writes logs to trading_bot_activity.log in persistent volume.
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")

async def send_assistant_log(message):
    if not message.strip():
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ASSISTANT_CHAT_ID,
        "text": f"📋 <b>Log</b>:\n<code>{message}</code>",
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, data=payload)
    except Exception as e:
        print(f"[Logger] Failed to send assistant log: {e}")
