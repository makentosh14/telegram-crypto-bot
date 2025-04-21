# telegram_bot.py

import aiohttp
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ASSISTANT_CHAT_ID

async def send_telegram_message(text, chat_id=None):
    if not text or not isinstance(text, str) or not text.strip():
        return

    chat_id = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    print(f"❌ Telegram error [{resp.status}]: {err}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")

async def send_to_assistant(text):
    if TELEGRAM_ASSISTANT_CHAT_ID:
        await send_telegram_message(text, chat_id=TELEGRAM_ASSISTANT_CHAT_ID)
