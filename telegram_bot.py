# telegram_bot.py

from config import TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN
import aiohttp

BOT_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

async def send_telegram_message(message):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(BOT_URL, data=payload) as resp:
            return await resp.text()

def format_trade_signal(symbol, score, tf_scores, trend, entry_price, sl, tp1, tp2, trade_type, trailing_stop):
    return (
        f"🚨 <b>{trade_type} Trade Signal</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Score:</b> {score} | <b>TFs:</b> {tf_scores}\n"
        f"<b>Entry:</b> {entry_price} | <b>SL:</b> {sl}\n"
        f"<b>TP1:</b> {tp1} | <b>TP2:</b> {tp2}\n"
        f"📈 <i>Smart Trailing SL</i>: {trailing_stop}% after TP1\n"
        f"📊 Trend: BTC = {trend['btc_trend']}, Altseason = {trend['altseason']}"
    )
