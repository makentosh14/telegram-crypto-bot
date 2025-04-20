import asyncio
import time
from scanner import fetch_symbols  # fetch_candles removed
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from datetime import datetime
from websocket_candles import live_candles, stream_candles  # <-- NEW IMPORT

TRADING_MODE = "auto"  # "auto" or "signal"
TIMEFRAMES = ['1']  # WebSocket supports live 1m updates

async def safe_send_telegram_message(message):
    from config import TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN
    import aiohttp

    if not message or not isinstance(message, str) or not message.strip():
        print("⚠️ Skipping empty Telegram message to avoid 400 error.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Telegram error [{response.status}]: {error_text}")
    except Exception as e:
        print(f"❌ Exception sending Telegram message: {e}")

async def main():
    print("🚀 Bot starting...")

    symbols = await fetch_symbols()
    print(f"✅ Fetched {len(symbols)} symbols.")
    top_symbols = symbols[:10]  # Limit active symbols for now

    # Start WebSocket candle feed
    asyncio.create_task(stream_candles(top_symbols, interval='1'))
    await asyncio.sleep(5)  # Wait for initial candle data

    while True:
        try:
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            if btc_trend == 'downtrend':
                allow_meme_trades = False
                max_risk_per_trade = 0.015
                scan_interval = 180
            elif altseason:
                allow_meme_trades = True
                max_risk_per_trade = 0.04
                scan_interval = 120
            else:
                allow_meme_trades = True
                max_risk_per_trade = 0.025
                scan_interval = 180

            signals_this_round = 0
            top_signals = []

            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            await safe_send_telegram_message(
                f"📊 Bot Status\n"
                f"🕒 Time: {timestamp}\n"
                f"🔎 Coins Scanned: {len(top_symbols)}\n"
                f"📡 Mode: {'AUTO' if TRADING_MODE == 'auto' else 'SIGNAL'}\n"
                f"📈 Signals This Round: calculating..."
            )

            for symbol in top_symbols:
                candles_by_timeframe = {}
                for tf in TIMEFRAMES:
                    if symbol in live_candles:
                        # Build pseudo-history with repeated live data (basic example)
                        candles_by_timeframe[tf] = [live_candles[symbol]] * 50
                    else:
                        print(f"⏩ Skipping {symbol}: no live candle data yet.")
                        continue

                if any(len(candles) < 30 for candles in candles_by_timeframe.values()):
                    print(f"⏩ Skipping {symbol}: not enough candles.")
                    continue

                score, tf_scores = score_symbol(symbol, candles_by_timeframe)
                print(f"🔍 {symbol} | Score: {score} | TF Scores: {tf_scores}")

                if score >= 3:
                    if not is_duplicate_signal(symbol):
                        signal_data = {
                            'symbol': symbol,
                            'score': score,
                            'tf_scores': tf_scores,
                            'btc_trend': btc_trend,
                            'altseason': altseason
                        }
                        log_signal(symbol)

                        if TRADING_MODE == "auto":
                            await execute_trade_if_valid(signal_data, max_risk=max_risk_per_trade)
                        else:
                            await safe_send_telegram_message(
                                f"🚨 Trade Setup: {symbol}\nScore: {score}\n"
                                f"TF Scores: {tf_scores}"
                            )

                        top_signals.append(symbol)

            if not top_signals:
                print("⚠️ No high-quality signals this round.")
                await safe_send_telegram_message("⚠️ No high-quality signals this round.")

        except Exception as e:
            await safe_send_telegram_message(f"❌ Error in main loop: {str(e)}")
            await asyncio.sleep(10)

        await asyncio.sleep(scan_interval)

if __name__ == "__main__":
    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
