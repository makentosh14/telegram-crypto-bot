import time
from scanner import fetch_symbols, fetch_candles
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from exit_manager import update_trailing_sl_if_needed

TRADING_MODE = "auto"  # or "signal"
SCAN_INTERVAL_DEFAULT = 180

def main():
    print("🚀 Bot starting...")
    last_telegram_update_min = -1

    while True:
        try:
            # === Get market context
            trend_context = get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            if btc_trend == 'downtrend':
                allow_meme_trades = False
                max_risk = 0.015
                scan_interval = 180
            elif altseason:
                allow_meme_trades = True
                max_risk = 0.04
                scan_interval = 120
            else:
                allow_meme_trades = True
                max_risk = 0.025
                scan_interval = SCAN_INTERVAL_DEFAULT

            # === Periodic Telegram status update
            current_minute = int(time.time() / 60)
            if current_minute % 60 == 0 and current_minute != last_telegram_update_min:
                send_telegram_message(
                    f"📊 Market Context:\n"
                    f"BTC Trend: {'📈 Uptrend' if btc_trend == 'uptrend' else '📉 Downtrend'}\n"
                    f"Altseason: {'✅ Yes' if altseason else '❌ No'}\n"
                    f"Scan Interval: {scan_interval}s\n"
                    f"Risk per Trade: {int(max_risk * 100)}%"
                )
                last_telegram_update_min = current_minute

            # === Fetch tradable symbols
            symbols = fetch_symbols()
            print(f"✅ Scanning {len(symbols)} coins...")

            for symbol in symbols:
                candles_by_tf = {
                    tf: fetch_candles(symbol, tf) for tf in ['5m', '15m', '1h']
                }

                score, tf_scores = score_symbol(symbol, candles_by_tf)

                if score >= 3.5 and not is_duplicate_signal(symbol):
                    signal = {
                        'symbol': symbol,
                        'score': score,
                        'tf_scores': tf_scores,
                        'btc_trend': btc_trend,
                        'altseason': altseason
                    }

                    log_signal(symbol)

                    if TRADING_MODE == "auto":
                        execute_trade_if_valid(signal, max_risk=max_risk)
                    else:
                        send_telegram_message(
                            f"📈 Trade Signal: {symbol}\n"
                            f"Score: {score}\n"
                            f"Timeframes: {tf_scores}"
                        )

            # === Update trailing stop-loss logic
            update_trailing_sl_if_needed()

        except Exception as e:
            send_telegram_message(f"❌ Error: {str(e)}")
            time.sleep(5)

        time.sleep(scan_interval)

if __name__ == "__main__":
    main()
