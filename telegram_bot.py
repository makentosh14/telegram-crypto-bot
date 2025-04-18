import requests
import datetime
import traceback

# Replace with your real bot token and chat IDs
BOT_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
MAIN_CHAT_ID = "1806610681"
ASSISTANT_CHAT_ID = "YOUR_ASSISTANT_CHAT_ID"  # optional

def send_telegram_message(message, chat_id=None, silent=False):
    if chat_id is None:
        chat_id = MAIN_CHAT_ID

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_notification": silent
    }
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload)
    except Exception as e:
        print(f"Telegram send failed: {e}")
        traceback.print_exc()

def format_signal(symbol, score, type, tf_scores, reason):
    emoji = "🚀" if score >= 4 else "⚠️" if score >= 2 else "🔍"
    tf_line = " | ".join([f"{tf}: {s}" for tf, s in tf_scores.items()])
    return (
        f"{emoji} *New {type.upper()} Signal* {emoji}\n"
        f"• Coin: `{symbol}`\n"
        f"• Score: *{score}*\n"
        f"• Time: {datetime.datetime.utcnow().strftime('%H:%M:%S')} UTC\n"
        f"• Timeframe Scores: {tf_line}\n"
        f"• Reason: _{reason}_"
    )

def send_signal_alert(symbol, score, type, tf_scores, reason):
    message = format_signal(symbol, score, type, tf_scores, reason)
    send_telegram_message(message)

def send_status_report(scanned, mode, signals_today):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    message = (
        f"📊 *Bot Status*\n"
        f"🕒 Time: {now}\n"
        f"🔎 Coins Scanned: *{scanned}*\n"
        f"📡 Mode: *{mode.upper()}*\n"
        f"📈 Signals Today: *{signals_today}*"
    )
    send_telegram_message(message)

def send_error_report(context, err):
    message = (
        f"❗ *ERROR ALERT*\n"
        f"📍 Context: `{context}`\n"
        f"⚠️ Error: `{str(err)}`"
    )
    send_telegram_message(message, chat_id=ASSISTANT_CHAT_ID)

def send_trade_execution(symbol, side, amount, entry, stop, tp1, tp2):
    emoji = "📈" if side.lower() == "long" else "📉"
    message = (
        f"{emoji} *Trade Executed*\n"
        f"• Symbol: `{symbol}`\n"
        f"• Side: *{side.upper()}*\n"
        f"• Amount: `{amount}`\n"
        f"• Entry: `{entry}`\n"
        f"• SL: `{stop}` | TP1: `{tp1}` | TP2: `{tp2}`"
    )
    send_telegram_message(message)

def send_trade_result(symbol, result, pnl):
    emoji = "✅" if result == "win" else "❌"
    message = (
        f"{emoji} *Trade Closed*\n"
        f"• Symbol: `{symbol}`\n"
        f"• Result: *{result.upper()}*\n"
        f"• PnL: `{pnl:.2f} USDT`"
    )
    send_telegram_message(message)
