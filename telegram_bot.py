import aiohttp
import asyncio
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

async def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            if resp.status != 200:
                print(f"Telegram error: {await resp.text()}")
                

def send_trade_alert(symbol, score, tf_scores, entry_price, sl, tp1, tp2):
    msg = (
        f"🚨 <b>New Trade Setup</b>\n"
        f"Symbol: <b>{symbol}</b>\n"
        f"Score: <b>{score}</b>\n"
        f"Timeframe Scores: {tf_scores}\n"
        f"Entry: {entry_price}\n"
        f"SL: {sl}\n"
        f"TP1: {tp1}\n"
        f"TP2: {tp2}"
    )
    send_telegram_message(msg)

def send_status_report(scan_count, mode, signals_today, memory_signals):
    msg = (
        f"📊 <b>Bot Status</b>\n"
        f"🕒 Time: <code>{get_utc_timestamp()}</code>\n"
        f"🔎 Coins Scanned: <b>{scan_count}</b>\n"
        f"📡 Mode: <b>{mode.upper()}</b>\n"
        f"📈 Signals Today: <b>{signals_today}</b>\n"
        f"💾 Signal Memory: {len(memory_signals)}"
    )
    send_telegram_message(msg, assistant=True)

def get_utc_timestamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
