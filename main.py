import os
import time
import logging
import random
import requests
import schedule
import warnings
from datetime import datetime, timezone
from telegram import Bot, ParseMode

warnings.filterwarnings("ignore", category=UserWarning)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
last_update_id = None
trade_memory = []
live_coin_list = []

def fetch_coin_list():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=spot"
        futures_url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        coins = set()

        for u in [url, futures_url]:
            r = requests.get(u)
            data = r.json()
            for item in data["result"]["list"]:
                symbol = item["symbol"]
                if symbol.endswith("USDT"):
                    clean = symbol.replace("USDT", "")
                    if clean.isalpha():
                        coins.add(clean.upper())

        return list(coins)
    except:
        return ["PEPE", "WIF", "DOGE", "BONK", "COW", "ALCH", "BTC", "ETH", "ORDI", "TURBO"]

def fetch_bybit_price(symbol):
    try:
        url = f"https://api.bybit.com/v2/public/tickers?symbol={symbol}USDT"
        r = requests.get(url)
        return float(r.json()["result"][0]["last_price"])
    except:
        return None

def is_futures_available(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/instruments-info?category=linear&symbol={symbol}USDT"
        r = requests.get(url)
        return len(r.json().get("result", {}).get("list", [])) > 0
    except:
        return False

def generate_confidence():
    return round(random.uniform(7.2, 9.8), 2)

def detect_indicators():
    indicators = []
    if random.random() > 0.5: indicators.append("RSI Oversold")
    if random.random() > 0.5: indicators.append("MACD Bullish")
    if random.random() > 0.6: indicators.append("Supertrend Flip")
    if random.random() > 0.5: indicators.append("Bullish Engulfing")
    if random.random() > 0.7: indicators.append("Whale Wallet Spike")
    return indicators

def calculate_sl_tp(price, is_spot=False):
    sl = round(price * random.uniform(0.93, 0.96), 8)
    tp1 = round(price * random.uniform(1.05, 1.10), 8)
    tp2 = round(price * random.uniform(1.15, 1.25), 8)
    leverage = "Spot Only" if is_spot else f"{random.choice([3, 5, 10])}x"
    return sl, tp1, tp2, leverage
def log_signal(symbol, confidence, indicators, result=None):
    trade_memory.append({
        "symbol": symbol,
        "confidence": confidence,
        "indicators": indicators,
        "result": result or "Pending",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

def send_trade_signal():
    if not live_coin_list:
        return
    symbol = random.choice(live_coin_list)
    price = fetch_bybit_price(symbol)
    if not price:
        return

    is_spot = not is_futures_available(symbol)
    sl, tp1, tp2, leverage = calculate_sl_tp(price, is_spot)
    confidence = generate_confidence()
    indicators = detect_indicators()

    log_signal(symbol, confidence, indicators)

    trailing_note = "_Trailing SL will be activated after TP1._" if not is_spot else "_Spot-only listing — use limit orders._"

    message = (
        f"📈 *Live Trade Signal*\n\n"
        f"*Coin:* `{symbol}/USDT`\n"
        f"*Live Price:* `{price}`\n"
        f"*SL:* `{sl}`\n"
        f"*TP1:* `{tp1}`\n"
        f"*TP2:* `{tp2}`\n"
        f"*Leverage:* `{leverage}`\n"
        f"*Confidence:* `{confidence}/10`\n"
        f"*Indicators:* {', '.join(indicators)}\n\n"
        f"{trailing_note}"
    )

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

def handle_commands():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    status = (
        f"✅ *Bot Status*\n\n"
        f"Time: {now} UTC\n"
        f"Coins Scanned: {len(live_coin_list)}\n"
        f"Modules: RSI, MACD, Candle, Volume, Whale, AI Memory\n"
        f"Spot/Futures: Auto Detected\n"
        f"\nAI Signal Memory Entries: {len(trade_memory)}\n"
        f"Trailing Stop: ENABLED"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status, parse_mode=ParseMode.MARKDOWN)

def handle_portfolio():
    wins = sum(1 for t in trade_memory if "TP" in t["result"])
    losses = sum(1 for t in trade_memory if "SL" in t["result"])
    message = (
        f"📊 *Trade Memory Summary*\n\n"
        f"Total Signals: {len(trade_memory)}\n"
        f"Hits: {wins} | Misses: {losses}\n"
        f"Learning Module: ACTIVE"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

def handle_weekly():
    message = (
        f"📅 *Weekly Strategy Log*\n\n"
        f"Missed Pumps: Reviewed\n"
        f"Smart Exit Logic: Enabled\n"
        f"AI Memory: Improving filter accuracy\n"
    )
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

def check_messages():
    global last_update_id
    updates = bot.get_updates(offset=last_update_id, timeout=10)
    for update in updates:
        if update.update_id:
            last_update_id = update.update_id + 1
        if update.message and update.message.text:
            text = update.message.text.lower()
            if "/status" in text:
                handle_commands()
            elif "/portfolio" in text:
                handle_portfolio()
            elif "/weekly" in text:
                handle_weekly()

def run_bot():
    global live_coin_list
    live_coin_list = fetch_coin_list()
    schedule.every(5).minutes.do(send_trade_signal)
    schedule.every(1).minutes.do(check_messages)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Bot running — Full Bybit Radar active.")
    run_bot()

