import aiohttp
import asyncio
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ASSISTANT_CHAT_ID

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

async def send_telegram_message(message: str, chat_id: str = TELEGRAM_CHAT_ID):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        print("Telegram configuration missing.")
        return
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BASE_TELEGRAM_URL, json=payload) as resp:
                if resp.status != 200:
                    print(f"❌ Telegram message failed: {resp.status}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def notify_both_chats(message: str):
    await send_telegram_message(message, TELEGRAM_CHAT_ID)
    if ASSISTANT_CHAT_ID and ASSISTANT_CHAT_ID != TELEGRAM_CHAT_ID:
        await send_telegram_message(message, ASSISTANT_CHAT_ID)

# For testing directly (optional)
if __name__ == "__main__":
    asyncio.run(send_telegram_message("✅ Telegram bot is connected!"))
