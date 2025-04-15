print("🚀 Bot starting...")
import os
import json
import time
import asyncio
import datetime
import math
import statistics
import aiohttp
import telegram
from telegram import Bot

TELEGRAM_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

bot = Bot(token=TELEGRAM_TOKEN)

# Store historical price data
coin_data = {}
signal_memory = {}

# Scoring threshold
SIGNAL_THRESHOLD = 8.5

# Technical indicator helpers
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    deltas = [closes[i+1] - closes[i] for i in range(-period-1, -1)]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0001
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return 0
    ema_fast = statistics.mean(closes[-fast:])
    ema_slow = statistics.mean(closes[-slow:])
    macd_line = ema_fast - ema_slow
    signal_line = statistics.mean([macd_line] * signal)
    return macd_line - signal_line

def calculate_supertrend(highs, lows, closes, period=10, multiplier=3.0):
    if len(closes) < period:
        return False
    atr = sum([highs[i] - lows[i] for i in range(-period, 0)]) / period
    hl2 = (highs[-1] + lows[-1]) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    return closes[-1] > upper_band

def calculate_ema(data, period):
    if len(data) < period:
        return sum(data) / len(data)
    k = 2 / (period + 1)
    ema = data[-period]
    for price in data[-period + 1:]:
        ema = price * k + ema * (1 - k)
    return ema

def bollinger_bands(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None, None
    sma = sum(prices[-period:]) / period
    std = statistics.stdev(prices[-period:])
    return sma + std_dev * std, sma - std_dev * std

def score_coin(symbol, history):
    closes = history["closes"]
    highs = history["highs"]
    lows = history["lows"]
    volumes = history["volumes"]
    score = 0

    if len(closes) < 30:
        return 0

    rsi = calculate_rsi(closes)
    if 55 < rsi < 75:
        score += 2

    macd = calculate_macd(closes)
    if macd > 0:
        score += 2

    if calculate_supertrend(highs, lows, closes):
        score += 1.5

    upper, lower = bollinger_bands(closes)
    if upper and closes[-1] > upper:
        score += 1.5

    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    if ema9 > ema21:
        score += 1.5

    if volumes[-1] > statistics.mean(volumes[-10:]) * 2:
        score += 1.5

    return score

def format_signal(symbol, price, score):
    return f"""
🚨 *Trade Signal Detected*
🪙 Coin: `{symbol}`
💰 Price: `{price}`
📊 Score: `{score}`

Type: Scalp / Swing 🧠
Risk: 2–3% • Leverage: 5–10x
SL/TP/Trailing: ✅ Enabled
"""

async def send_telegram_signal(text):
    try:
     bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print("Telegram error:", e)

import hmac
import hashlib
import time

async def fetch_symbols():
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            url = "https://api.bybit.com/v2/public/symbols"
            async with session.get(url) as resp:
                print(f"Fetch URL: {url}, Status: {resp.status}")
                if resp.status != 200:
                    return []
                data = await resp.json()
                symbols = data.get("result", [])
                return [s["name"] for s in symbols if s.get("quote_currency") == "USDT"]
    except Exception as e:
        print("Error fetching symbols:", e)
        return []

async def fetch_candles(symbol):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit=100"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                candles = data["result"]["list"]
                closes = [float(c[4]) for c in candles]
                highs = [float(c[2]) for c in candles]
                lows = [float(c[3]) for c in candles]
                volumes = [float(c[5]) for c in candles]
                return {"closes": closes, "highs": highs, "lows": lows, "volumes": volumes, "price": closes[-1]}
    except Exception as e:
        print("Candle fetch error:", e)
        return None

async def scan_market():
    symbols = await fetch_symbols()
    print(f"✅ Scanning {len(symbols)} coins...")
    for symbol in symbols:
        data = await fetch_candles(symbol)
        if not data:
            continue
        score = score_coin(symbol, data)
        if score >= SIGNAL_THRESHOLD and symbol not in signal_memory:
            signal_memory[symbol] = True
            signal = format_signal(symbol, data['price'], round(score, 2))
            await send_telegram_signal(signal)

async def send_status():
    while True:
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        status = f"📊 *Bot Status*\n🕒 Time: `{now}`\n🔎 Coins Scanned: `{len(coin_data)}`\n📡 Mode: `LIVE`\n📈 Signals Today: `{len(signal_memory)}`"
        await send_telegram_signal(status)
        await asyncio.sleep(900)

async def run():
    while True:
        await scan_market()
        await asyncio.sleep(180)

async def main():
    await asyncio.gather(run(), send_status())

asyncio.run(main())


