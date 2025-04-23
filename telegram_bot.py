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

def format_trade_signal(symbol, score, tf_scores, trend, entry_price, sl, tp1, trade_type, direction, trailing_pct):
    direction_emoji = "🟢 Long" if direction == "Buy" else "🔴 Short"
    return (
        f"\n{direction_emoji} <b>{trade_type} Signal</b>"
        f"\nSymbol: <b>{symbol}</b>"
        f"\nScore: <b>{score}</b>"
        f"\nTF Breakdown: <code>{tf_scores}</code>"
        f"\nEntry: <code>{entry_price}</code>"
        f"\nSL: <code>{sl}</code>"
        f"\nTP1: <code>{tp1}</code>"
        f"\n📈 Trailing SL: {trailing_pct}% after TP1"
        f"\n📊 Trend: BTC = {trend['btc_trend']}, Altseason = {trend['altseason']}"
    )

def format_exit_alert(symbol, reason, exit_price=None):
    message = f"❌ <b>Exit Alert</b>\nSymbol: <b>{symbol}</b>\nReason: {reason}"
    if exit_price:
        message += f"\nExit Price: <code>{exit_price}</code>"
    return message
