import asyncio
import time
from scanner import fetch_symbols, fetch_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal

TRADING_MODE = "auto"  # "auto" or "signal"

async def main():
    print("🚀 Bot starting...")

    while True:
        try:
            # === Market context ===
            trend_context = get_trend_context()
            btc_trend = trend_context["btc_trend"]
            altseason = trend_context["altseason"]

            # === Dynamic risk & interval ===
            if btc_trend == "downtrend":
                allow_meme_trades = False
                max_risk_per_trade = 0.015
                scan_interval = 180
            elif altseason:
                allow_meme_trades = True
                max_risk_per_trade = 0.04
                scan_interval = 90
            else:
                allow_meme_trades = True
                max_risk_per_trade = 0.025
                scan_interval = 180

            # === Send Telegram hourly ===
            current_minute = int(time.time() / 60)
            if current_minute % 60 == 0:
                await send_telegram_message(
                    f"📊 Market Context:\n"
                    f"BTC Trend: {'📈 Uptrend' if btc_trend == 'uptrend' else '📉 Downtrend'}\n"
                    f"Altseason: {'✅ Yes' if altseason else '❌ No'}\n"
                    f"Scan Interval: {scan_interval}s\n"
                    f"Risk per trade: {int(max_risk_per_trade * 100)}%"
                )

            # === Fetch symbols ===
            symbols = await fetch_symbols()
            print(f"✅ Fetched {len(symbols)} symbols.")

            top_signals = []

  async def fetch_symbols():
    url = f"{BYBIT_API_URL}/v5/market/instruments-info?category=linear"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if 'result' in data and 'list' in data['result']:
                    symbols = [item['symbol'] for item in data['result']['list']]
                    return symbols
                else:
                    log("⚠️ Unexpected response structure.")
                    return []
    except Exception as e:
        log(f"❌ Error fetching symbols: {e}")
        return []

async def fetch_candles(symbol, timeframe='5m', limit=100):
    url = f"{BYBIT_API_URL}/v5/market/kline?category=linear&symbol={symbol}&interval={timeframe}&limit={limit}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if 'result' in data and 'list' in data['result']:
                    candles = []
                    for item in data['result']['list']:
                        candles.append({
                            'timestamp': int(item[0]),
                            'open': item[1],
                            'high': item[2],
                            'low': item[3],
                            'close': item[4],
                            'volume': item[5]
                        })
                    return candles
                else:
                    log(f"⚠️ Invalid candle response for {symbol}")
                    return []
    except Exception as e:
        log(f"❌ Error fetching candles for {symbol}: {e}")
        return []


if __name__ == "__main__":
    asyncio.run(main())
