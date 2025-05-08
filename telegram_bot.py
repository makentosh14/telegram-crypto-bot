# telegram_bot.py

from config import TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN
import aiohttp
import traceback
import os
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InputFile
from logger import LOG_FILE
from error_handler import send_error_to_telegram  # ✅ Use only from external file

# === Global message rate limit ===
_last_send_time = 0
MIN_MESSAGE_DELAY = 1.0  # seconds

BOT_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)


async def send_telegram_message(message):
    global _last_send_time

    now = time.time()
    elapsed = now - _last_send_time

    if elapsed < MIN_MESSAGE_DELAY:
        await asyncio.sleep(MIN_MESSAGE_DELAY - elapsed)

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(BOT_URL, data=payload) as resp:
                _last_send_time = time.time()
                return await resp.text()
        except Exception as e:
            print(f"❌ Telegram send error: {e}")
            await send_error_to_telegram(f"Telegram Error: {str(e)}")
            return None


def format_trade_signal(
    symbol,
    score,
    tf_scores,
    trend,
    entry_price,
    sl,
    tp1,
    trade_type,
    direction,
    trailing_pct,
    leverage,
    risk_pct,
    confidence=None,
    sl_pct=None
):
    relevant_tfs = {
        "Scalp": [1, 3],
        "Intraday": [5, 15],
        "Swing": [30, 60, 240]
    }.get(trade_type, [])

    filtered_tf_scores = {k: v for k, v in tf_scores.items() if int(k) in relevant_tfs}
    emoji = "🟢" if direction == "Long" else "🔴"

    message = (
        f"{emoji} <b>{direction} {trade_type} Signal</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>TF Breakdown:</b> {filtered_tf_scores}\n\n"
        f"<b>Entry:</b> {entry_price}\n"
        f"<b>SL:</b> {sl}" + (f" ({sl_pct:.2f}%)" if sl_pct is not None else "") + "\n"
        f"<b>TP1:</b> {tp1}\n\n"
        f"⚖️ <b>Risk:</b> {risk_pct:.1f}% of balance\n"
        f"📈 <b>Leverage:</b> {leverage}x\n"
        f"📉 <b>Smart Trailing SL:</b> {trailing_pct:.1f}% after TP1\n"
        f"📊 <b>Trend:</b> BTC = {trend['btc_trend']}, Altseason = {trend['altseason']}\n"
    )

    if confidence is not None:
        message += f"\n🔍 <b>Confidence:</b> {confidence:.1f}%"

    return message


async def send_pump_alert(symbol, pump_score, volume_spike_pct, price_change_pct, reason):
    message = (
        f"🚀 <b>Early Pump Signal Detected</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Pump Score:</b> {pump_score:.2f}\n"
        f"<b>Volume Spike:</b> +{volume_spike_pct:.1f}%\n"
        f"<b>Price Change:</b> +{price_change_pct:.2f}%\n"
        f"<b>Reason:</b> {reason}\n"
        f"⚡ <i>Monitoring for breakout, Smart SL/TP activation on momentum</i>"
    )
    await send_telegram_message(message)


# ✅ Command: /active
@dp.message_handler(commands=["active"])
async def handle_active_trades(message: types.Message):
    from monitor import active_trades  # ⬅️ Lazy import avoids circular import
    active = {k: v for k, v in active_trades.items() if not v.get("exited")}
    if not active:
        await message.reply("📭 No active trades currently being monitored.")
        return

    msg = "📡 <b>Active Trade Setups:</b>\n"
    for symbol, trade in active.items():
        trade_type = trade.get("trade_type", "N/A")
        entry = trade.get("entry_price", "?")
        direction = trade.get("direction", "?")
        trailing_sl = trade.get("trailing_sl", "Not set")
        tp1_hit = "✅" if trade.get("tp1_hit") else "❌"
        tp2_hit = "✅" if trade.get("tp2_hit") else "❌"

        msg += (
            f"\n<b>{symbol}</b> | {direction} ({trade_type})\n"
            f"• Entry: {entry}\n"
            f"• Trailing SL: {trailing_sl}\n"
            f"• TP1 Hit: {tp1_hit} | TP2 Hit: {tp2_hit}\n"
        )

    await message.reply(msg, parse_mode="HTML")


# ✅ Command: /download_trades
@dp.message_handler(commands=["download_trades"])
async def handle_download_trades(message: types.Message):
    if os.path.exists(LOG_FILE):
        file_to_send = InputFile(LOG_FILE)
        await message.reply_document(file_to_send, caption="📁 Trade log file attached.")
    else:
        await message.reply("❌ Log file not found.")


# ✅ Start the bot
def run_telegram_bot():
    executor.start_polling(dp, skip_updates=True)
