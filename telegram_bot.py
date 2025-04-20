# telegram_bot.py

import aiohttp
import asyncio
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

async def send_telegram_message(message: str, chat_id: str = TELEGRAM_CHAT_ID):
    if not TELEGRAM_TOKEN or not chat_id:
        print("❌ Telegram config missing.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            payload = {"chat_id": chat_id, "text": message}
            async with session.post(BASE_TELEGRAM_URL, data=payload) as response:
                if response.status != 200:
                    print(f"❌ Telegram error: {response.status}")
        except Exception as e:
            print(f"❌ Exception sending Telegram message: {e}")
