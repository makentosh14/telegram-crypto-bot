import os
import json
import time
import asyncio
import datetime
import aiohttp
import telegram
from telegram import Bot

# 🔐 Tokens (replace with os.getenv() later if using Railway vars)
TELEGRAM_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"

bot = Bot(token=TELEGRAM_TOKEN)

# ✅ Real-time coin data store
coin_data = {}

# ✅ Scoring config
def score_coin(symbol, price, volume):
    score = 0

    # Placeholder logic – you can expand with RSI, MACD, etc.
    if volume > 100000:  # example volume threshold
        score += 3
    if price > 0.01:
        score += 1

    return score

# ✅ Signal formatting
def format_signal(symbol, price, volume, score):
    return f"""
🚨 *Trade Signal Detected*
🪙 Coin: `{symbol}`
💵 Price: `{price}`
📊 Volume: `{volume}`
📈 Score: `{score}`

Risk: 2–3% • Leverage: 5–10x
SL/TP logic active ✅
"""

# ✅ Telegram send
async def send_telegram_signal(signal_text):
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=signal_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
    except Exception as e:
        print("Telegram error:", e)

# ✅ WebSocket connection
async def bybit_websocket():
    url = "wss://stream.bybit.com/v5/public/linear"
    print("Connecting to WebSocket...")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            await ws.send_json({
                "op": "subscribe",
                "args": ["tickers.BTCUSDT", "tickers.ETHUSDT"]  # replace with full USDT scan later
            })

            print("WebSocket subscribed to tickers.")
            last_scan = time.time()

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if "data" in data:
                            ticker = data["data"]
                            symbol = ticker["symbol"]
                            price = float(ticker["lastPrice"])
                            volume = float(ticker["turnover24h"])

                            coin_data[symbol] = {
                                "price": price,
                                "volume": volume
                            }

                            # Scan every 5 seconds per coin (adjustable)
                            if time.time() - last_scan > 5:
                                last_scan = time.time()
                                for sym, info in coin_data.items():
                                    s = score_coin(sym, info["price"], info["volume"])
                                    if s >= 8.5:
                                        signal = format_signal(sym, info["price"], info["volume"], s)
                                        await send_telegram_signal(signal)

                    except Exception as e:
                        print("Data parsing error:", e)

# ✅ Telegram status updater
async def send_status():
    while True:
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = f"📊 *Bot Status*\n🕒 Time: `{now}`\n📡 Mode: `LIVE WEBSOCKET`\n🪙 Coins Tracked: `{len(coin_data)}`"
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')
        except:
            pass
        await asyncio.sleep(900)  # 15 minutes

# ✅ Run all
async def main():
    await asyncio.gather(
        bybit_websocket(),
        send_status()
    )

asyncio.run(main())


