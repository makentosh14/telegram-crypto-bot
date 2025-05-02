from config import TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN
import aiohttp
import traceback

BOT_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

async def send_telegram_message(message):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(BOT_URL, data=payload) as resp:
                return await resp.text()
        except Exception as e:
            print(f"❌ Telegram send error: {e}")
            await send_error_to_telegram(f"Telegram Error: {str(e)}")
            return None

async def send_error_to_telegram(error_text):
    error_msg = f"❗️<b>Bot Error/Crash Detected</b>\n<pre>{error_text}</pre>"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": error_msg[:4096],  # Telegram max length
        "parse_mode": "HTML"
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(BOT_URL, data=payload)
    except Exception as e:
        print(f"❌ Telegram crash-report failed: {e}")

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
