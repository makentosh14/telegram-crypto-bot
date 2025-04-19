import time
from scanner import fetch_symbols, fetch_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal

# === Global Settings ===
TRADING_MODE = "auto"  # options: 'signal' or 'auto'

def main():
    print("🚀 Bot starting...")

    while True:
        try:
            # === Get market context ===
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

            # === Telegram update hourly ===
            current_minute = int(time.time() / 60)
            if current_minute % 60 == 0:
                send_telegram_message(
                    f"📊 Market Context:\n"
                    f"BTC Trend: {'📈 Uptrend' if btc_trend == 'uptrend' else '📉 Downtrend'}\n"
                    f"Altseason: {'✅ Yes' if altseason else '❌ No'}\n"
                    f"Scan Interval: {scan_interval}s\n"
                    f"Risk: {int(max_risk_per_trade * 100)}%"
                )

            # === Fetch coins ===
            symbols = fetch_symbols()
            print(f"✅ Fetched {len(symbols)} symbols.")

            # === Scan symbols ===
            top_signals = []
            for symbol in symbols:
                candles_by_timeframe = {
                    tf: fetch_candles(symbol, tf) for tf in ['5m', '15m', '1h']
                }
                score, tf_scores = score_symbol(symbol, candles_by_timeframe)

                if score >= 3:  # You can fine-tune threshold
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
                            execute_trade_if_valid(signal_data, max_risk=max_risk_per_trade)
                        else:
                            send_telegram_message(
                                f"🚨 Trade Setup: {symbol}\nScore: {score}\n"
                                f"TF Scores: {tf_scores}"
                            )

                        top_signals.append(symbol)

            if not top_signals:
                print("⚠️ No high-quality signals this round.")

        except Exception as e:
            send_telegram_message(f"❌ Error in main loop: {str(e)}")
            time.sleep(10)

        time.sleep(scan_interval)

if __name__ == "__main__":
    main()
