import asyncio
import time
from scanner import fetch_symbols, fetch_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from datetime import datetime

TRADING_MODE = "auto"  # "auto" or "signal"

async def main():
    print("🚀 Bot starting...")

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

            symbols = await fetch_symbols()
            print(f"✅ Fetched {len(symbols)} symbols.")

            signals_this_round = 0
            top_signals = []

            # Telegram status update
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            await send_telegram_message(
                f"📊 Bot Status\n"
                f"🕒 Time: {timestamp}\n"
                f"🔎 Coins Scanned: {len(symbols)}\n"
                f"📡 Mode: {'AUTO' if TRADING_MODE == 'auto' else 'SIGNAL'}\n"
                f"📈 Signals This Round: calculating..."
            )

            for symbol in symbols:
                candles_by_timeframe = {
                    tf: await fetch_candles(symbol, tf) for tf in ['5m', '15m', '1h']
                }

                score, tf_scores = score_symbol(symbol, candles_by_timeframe)

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
                            await send_telegram_message(
                                f"🚨 Trade Setup: {symbol}\nScore: {score}\n"
                                f"TF Scores: {tf_scores}"
                            )

                        top_signals.append(symbol)

            if not top_signals:
                print("⚠️ No high-quality signals this round.")
                await send_telegram_message("⚠️ No high-quality signals this round.")

        except Exception as e:
            await send_telegram_message(f"❌ Error in main loop: {str(e)}")
            await asyncio.sleep(10)

        await asyncio.sleep(scan_interval)

if __name__ == "__main__":
    asyncio.run(main())
