import requests
import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ASSISTANT_CHAT_ID

def send_telegram_message(message, silent=False, assistant=False):
    chat_id = ASSISTANT_CHAT_ID if assistant else TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_notification": silent
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

def send_status_update(scanned=0, signals=0, mode="LIVE"):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"📊 <b>Bot Status</b>\n🕒 <b>Time:</b> {now} UTC\n🔎 <b>Coins Scanned:</b> {scanned}\n📡 <b>Mode:</b> {mode}\n📈 <b>Signals Today:</b> {signals}"
    send_telegram_message(msg, assistant=True)

def send_trade_alert(symbol, score, timeframe_scores, signal_type, entry_price, sl, tp):
    tf_msg = "\n".join([f"⏱ <b>{tf}</b>: {s}" for tf, s in timeframe_scores.items()])
    msg = (
        f"🚀 <b>{signal_type} Signal</b>\n"
        f"💠 <b>{symbol}</b>\n"
        f"📊 <b>Total Score:</b> {score}\n"
        f"{tf_msg}\n"
        f"💰 <b>Entry:</b> {entry_price}\n"
        f"🛡 <b>SL:</b> {sl}\n"
        f"🎯 <b>TP:</b> {tp}"
    )
    send_telegram_message(msg)
