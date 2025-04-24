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
    sl_pct=None  # ✅ Optional dynamic SL %
):
    relevant_tfs = {
        "Scalp": [1, 3],
        "Intraday": [5, 15],
        "Swing": [30, 60, 240]
    }[trade_type]

    filtered_tf_scores = {k: v for k, v in tf_scores.items() if int(k) in relevant_tfs}
    emoji = "🟢" if direction == "Long" else "🔴"

    message = (
        f"{emoji} <b>{direction} {trade_type} Signal</b>\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>TF Breakdown:</b> {filtered_tf_scores}\n\n"
        f"<b>Entry:</b> {entry_price}\n"
        f"<b>SL:</b> {sl}"
    )

    if sl_pct is not None:
        message += f" (-{sl_pct:.2f}% | ATR-based)"

    message += (
        f"\n<b>TP1:</b> {tp1}\n\n"
        f"⚖️ <b>Risk:</b> {risk_pct:.1f}% of balance\n"
        f"📈 <b>Leverage:</b> {leverage}x\n"
        f"📉 <b>Trailing SL:</b> {trailing_pct:.1f}% after TP1\n"
        f"📊 <b>Trend:</b> BTC = {trend['btc_trend']}, Altseason = {trend['altseason']}\n"
    )

    if confidence is not None:
        message += f"\n🔍 <b>Confidence:</b> {confidence:.1f}%"

    return message
