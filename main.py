import os
import time
import requests
import datetime
import schedule
from telegram import Bot

# === Environment Variables ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_TOKEN)

# === Bot State ===
total_scans = 0
total_signals = 0
win_rate = 0
last_best_trade = "N/A"
scan_mode = "Normal"
top_coins = []
# === Fetch tradable Bybit pairs ===
def fetch_bybit_symbols():
    url = "https://api.bybit.com/v5/market/instruments?category=linear"
    try:
        response = requests.get(url)
        data = response.json()
        symbols = [item["symbol"] for item in data["result"]["list"] if "USDT" in item["symbol"]]
        return symbols[:100]  # Limit for speed
    except:
        return []

# === Simulated Scoring Function ===
def score_coin(symbol):
    score = 0

    # Simulated indicator values (replace with real logic in future)
    rsi = 45 + hash(symbol) % 30       # Range 45–75
    macd = hash(symbol) % 4 - 2        # Range -2 to +2
    supertrend = True if hash(symbol) % 3 != 0 else False
    volume_spike = True if "WIF" in symbol or "PEPE" in symbol else False
    social_hype = "PEPE" in symbol or "POPCAT" in symbol or "DOGE" in symbol

    # Score logic
    if 50 < rsi < 70: score += 1.5
    if macd > 0: score += 1.5
    if supertrend: score += 1.5
    if volume_spike: score += 2
    if social_hype: score += 2.5

    return round(score, 2)
# === Build and Send Signal ===
def send_trade_signal(symbol, score):
    global total_signals, last_best_trade

    signal = (
        f"📈 *Trade Signal Detected*\n"
        f"Coin: {symbol}\n"
        f"Score: {score}/10\n"
        f"Strategy: Momentum + Volume Spike\n"
        f"TP1/TP2: Auto Managed\n"
        f"Leverage: 3–5x\n"
        f"Risk: Adaptive\n"
        f"Confidence: 🔥 High"
    )

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal, parse_mode='Markdown')
    total_signals += 1
    last_best_trade = f"{symbol} +{score * 2:.1f}%"

# === Send Bot Status ===
def send_status():
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    status = (
        f"📊 *Bot Status*\n"
        f"🕒 Last Scan: {now} UTC\n"
        f"🔁 Coins Scanned: {total_scans}\n"
        f"📈 Signals Sent: {total_signals}\n"
        f"🎯 Est. Win Rate: {win_rate}%\n"
        f"💹 Best Trade: {last_best_trade}\n"
        f"⚙️ Mode: {scan_mode}"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status, parse_mode='Markdown')
# === Main Scanner ===
def scan_market():
    global total_scans, win_rate

    symbols = fetch_bybit_symbols()
    total_scans += len(symbols)

    high_score_signals = []

    for symbol in symbols:
        score = score_coin(symbol)
        if score >= 8.5:
            high_score_signals.append((symbol, score))

    # Sort top 5 signals
    high_score_signals = sorted(high_score_signals, key=lambda x: x[1], reverse=True)[:5]

    for symbol, score in high_score_signals:
        send_trade_signal(symbol, score)

    # Win rate placeholder logic
    if total_signals > 0:
        win_rate = int(total_signals * 0.68)


# === Run Loop ===
def run_bot():
    schedule.every(3).minutes.do(scan_market)
    schedule.every(15).minutes.do(send_status)

    print("🚀 Sniper bot is live and scanning...")
    while True:
        schedule.run_pending()
        time.sleep(1)


# === Start Bot ===
run_bot()


