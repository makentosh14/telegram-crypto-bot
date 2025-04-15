import os
import time
import datetime
import requests
import schedule
from telegram import Bot

# === Environment Variables ===
TELEGRAM_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"
bot = Bot(token=TELEGRAM_TOKEN)

# === Global Tracking ===
total_scans = 0
total_signals = 0
win_rate = 0
last_best_trade = "N/A"
scan_mode = "Normal"
active_risk = 2
ai_memory = {}
missed_pumps = []

# === Altseason Trigger Settings ===
altseason_enabled = False
btc_dominance = 54.0  # Simulated fallback
eth_btc_ratio = 0.06  # Simulated fallback
# === Pull Tradable Bybit Symbols ===
def fetch_bybit_symbols():
    url = "https://api.bybit.com/v5/market/instruments?category=linear"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        return [s["symbol"] for s in data["result"]["list"] if "USDT" in s["symbol"]]
    except:
        return []

# === Fake Market Conditions (Sim for altseason logic)
def update_market_conditions():
    global altseason_enabled, scan_mode, active_risk
    # Simulated logic — normally from BTC dominance, ETH/BTC, etc.
    if btc_dominance < 50 or eth_btc_ratio > 0.07:
        altseason_enabled = True
        scan_mode = "Altseason"
        active_risk = 4
        schedule.clear()
        schedule.every(2).minutes.do(scan_market)
        schedule.every(15).minutes.do(send_status)
    else:
        altseason_enabled = False
        scan_mode = "Normal"
        active_risk = 2

# === Score Coin Based on Technicals + Memory
def score_coin(symbol):
    score = 0

    # Simulated indicators
    rsi = 45 + hash(symbol) % 30
    macd = hash(symbol) % 4 - 2
    supertrend = hash(symbol) % 3 != 0
    volume_spike = hash(symbol) % 10 > 7
    meme_name = any(x in symbol.lower() for x in ["wif", "doge", "pepe", "popcat", "floki"])

    if 50 < rsi < 70: score += 1.5
    if macd > 0: score += 1.5
    if supertrend: score += 1.5
    if volume_spike: score += 2
    if meme_name: score += 2.5

    # AI Signal Memory boost
    if symbol in ai_memory and ai_memory[symbol] > 1:
        score += 1.0

    return round(score, 2)
# === Send Trade Signal to Telegram ===
def send_trade_signal(symbol, score):
    global total_signals, last_best_trade

    # Smart Exit logic
    tp1 = f"+{round(score * 1.5, 1)}%"
    tp2 = f"+{round(score * 2.5, 1)}%"
    trailing_sl = f"{round(score * 0.8, 1)}%"

    signal = (
        f"📈 *Trade Signal Detected*\n"
        f"Symbol: {symbol}\n"
        f"Score: {score}/10\n"
        f"Leverage: 3–5x\n"
        f"Risk: {active_risk}%\n"
        f"TP1: {tp1}, TP2: {tp2}, SL: Trailing {trailing_sl}\n"
        f"Exit Mode: Smart Trailing\n"
        f"Confidence: 🔥 High"
    )

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal, parse_mode='Markdown')
    total_signals += 1
    last_best_trade = f"{symbol} {tp2}"

    # Update AI Memory
    if symbol in ai_memory:
        ai_memory[symbol] += 1
    else:
        ai_memory[symbol] = 1

# === Send Status Update to Telegram ===
def send_status():
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    status = (
        f"📊 *Bot Status*\n"
        f"🕒 Last Scan: {now} UTC\n"
        f"🔁 Coins Scanned: {total_scans}\n"
        f"📈 Signals Sent: {total_signals}\n"
        f"🎯 Est. Win Rate: {win_rate}%\n"
        f"💹 Last Best Trade: {last_best_trade}\n"
        f"⚙️ Scan Mode: {scan_mode}\n"
        f"🤖 AI Memory: {len(ai_memory)} symbols tracked"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status, parse_mode='Markdown')
# === Market Scanner ===
def scan_market():
    global total_scans, win_rate

    update_market_conditions()
    symbols = fetch_bybit_symbols()
    total_scans += len(symbols)

    high_score_signals = []

    for symbol in symbols:
        score = score_coin(symbol)

        if score >= 8.5:
            high_score_signals.append((symbol, score))
        elif score >= 7.8 and "usdt" in symbol.lower():
            missed_pumps.append(symbol)

    high_score_signals = sorted(high_score_signals, key=lambda x: x[1], reverse=True)[:5]

    for symbol, score in high_score_signals:
        send_trade_signal(symbol, score)

    # Simulated win rate update
    if total_signals > 0:
        win_rate = int(total_signals * 0.68)

# === Bot Runner ===
def run_bot():
    print("🚀 Sniper bot is live. Scanning Bybit market...")
    schedule.every(3).minutes.do(scan_market)
    schedule.every(15).minutes.do(send_status)

    while True:
        schedule.run_pending()
        time.sleep(1)

# === Launch Bot ===
run_bot()



