# logger.py

import datetime
import asyncio
from config import TELEGRAM_ASSISTANT_CHAT_ID, TELEGRAM_BOT_TOKEN
import aiohttp

def log(msg, level="INFO"):
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

    # Optionally forward to Telegram assistant channel
    if TELEGRAM_ASSISTANT_CHAT_ID and level in ["ERROR", "ALERT"]:
        asyncio.create_task(send_assistant_log(msg))

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
