import asyncio
import time
from scanner import fetch_symbols, fetch_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal

TRADING_MODE = "auto"  # 'signal' or 'auto'

async def main():
    print("🚀 Bot starting...")

    last_announcement = 0

    while True:
        try:
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            # === Smart Scan Interval Logic ===
            if btc_trend == 'downtrend':
                scan_interval = 180
                max_risk_per_trade = 0.015
            elif altseason:
                scan_interval = 60
                max_risk_per_trade = 0.04
            else:
                scan_interval = 120
                max_risk_per_trade = 0.025

            allow_meme_trades = altseason or btc_trend == 'uptrend'

            # === Send context update every 60 min
            now = time.time()
            if now - last_announcement >= 3600:
                await send_telegram_message(
                    f"📊 Smart Mode Market Context:\n"
                    f"BTC Trend: {'📈 Uptrend' if btc_trend == 'uptrend' else '📉 Downtrend'}\n"
                    f"Altseason: {'✅ Yes' if altseason else '❌ No'}\n"
                    f"Scan Speed: {scan_interval}s\n"
                    f"Auto Risk: {int(max_risk_per_trade * 100)}%"
                )
                last_announcement = now

            # === Fetch coins ===
            symbols = await fetch_symbols()
            print(f"✅ Fetched {len(symbols)} symbols.")
            await send_telegram_message(f"✅ Fetched {len(symbols)} symbols.")

            top_signals = []

            for symbol in symbols:
                try:
                    candles_by_timeframe = {
                        tf: await fetch_candles(symbol, tf) for tf in ['5m', '15m', '1h']
                    }

                    # Debug info
                    lengths = [len(candles_by_timeframe[tf]) for tf in candles_by_timeframe]
                    print(f"🔍 {symbol} | Candle lengths: {lengths}")

                    score, tf_scores = score_symbol(symbol, candles_by_timeframe)
                    print(f"🧠 Scored {symbol} → Total: {score} | TF: {tf_scores}")

                    if score >= 3 and not is_duplicate_signal(symbol):
                        log_signal(symbol)
                        signal_data = {
                            'symbol': symbol,
                            'score': score,
                            'tf_scores': tf_scores,
                            'btc_trend': btc_trend,
                            'altseason': altseason
                        }

                        if TRADING_MODE == "auto":
                            await execute_trade_if_valid(signal_data, max_risk=max_risk_per_trade)
                        else:
                            await send_telegram_message(
                                f"🚨 Trade Setup: {symbol}\nScore: {score}\nTF Scores: {tf_scores}"
                            )

                        top_signals.append(symbol)

                except Exception as inner_e:
                    print(f"❌ Error scanning {symbol}: {str(inner_e)}")

            if not top_signals:
                print("⚠️ No high-quality signals this round.")
                await send_telegram_message("⚠️ No high-quality signals this round.")

        except Exception as e:
            print(f"❌ Error in main loop: {str(e)}")
            await send_telegram_message(f"❌ Error in main loop: {str(e)}")

        await asyncio.sleep(scan_interval)

if __name__ == "__main__":
    asyncio.run(main())
