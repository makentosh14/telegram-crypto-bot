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

            # === Score all symbols ===
            for symbol in symbols:
                candles_by_timeframe = {
                    tf: await fetch_candles(symbol, tf) for tf in ["5m", "15m", "1h"]
                }

                score, tf_scores = score_symbol(symbol, candles_by_timeframe)

                if score >= 3 and not is_duplicate_signal(symbol):
                    signal_data = {
                        "symbol": symbol,
                        "score": score,
                        "tf_scores": tf_scores,
                        "btc_trend": btc_trend,
                        "altseason": altseason,
                    }

                    log_signal(symbol)

                    if TRADING_MODE == "auto":
                        await execute_trade_if_valid(signal_data, max_risk=max_risk_per_trade)
                    else:
                        await send_telegram_message(
                            f"🚨 Trade Setup: {symbol}\nScore: {score}\nTF Scores: {tf_scores}"
                        )

                    top_signals.append(symbol)

            if not top_signals:
                print("⚠️ No high-quality signals this round.")

        except Exception as e:
            await send_telegram_message(f"❌ Error in main loop: {str(e)}")
            await asyncio.sleep(10)

        await asyncio.sleep(scan_interval)


if __name__ == "__main__":
    asyncio.run(main())
