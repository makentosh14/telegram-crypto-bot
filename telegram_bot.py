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

def format_trade_signal(symbol, score, tf_scores, trend, entry_price, sl, tp1, trade_type, direction, trailing_pct, leverage, risk_pct):
    emoji = "🟢" if direction == "Long" else "🔴"
    return (
        f"{emoji} <b>{direction} {trade_type} Signal</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>TF Breakdown:</b> <code>{tf_scores}</code>\n"
        f"<b>Entry:</b> <code>{entry_price}</code>\n"
        f"<b>SL:</b> <code>{sl}</code>\n"
        f"<b>TP1:</b> <code>{tp1}</code>\n"
        f"⚖️ <b>Risk:</b> {risk_pct}% of balance\n"
        f"📉 <b>Leverage:</b> {leverage}x\n"
        f"📈 <b>Trailing SL:</b> {trailing_pct}% after TP1\n"
        f"📊 <b>Trend:</b> BTC = {trend['btc_trend']}, Altseason = {trend['altseason']}"
    )
