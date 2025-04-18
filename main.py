import time
from scanner import scan_market
from signal_memory import update_signal_memory
from telegram_bot import send_telegram_signal, send_status_report
from trade_executor import execute_trade
from trend_filters import update_market_mode
from risk_manager import get_risk_per_trade
from config import (
    SCAN_INTERVAL, ENABLE_SCALP, ENABLE_INTRADAY, ENABLE_SWING,
    TELEGRAM_CHAT_ID, MODE, ENABLE_TREND_FILTERS,
    SEND_SIGNAL_ALERTS, ENABLE_AI_SIGNAL_MEMORY, ENABLE_SMART_EXIT_MANAGER
)
from bybit_api import fetch_all_symbols, fetch_candles

print("🚀 Bot starting...")
symbols = fetch_all_symbols()
print(f"✅ Fetched {len(symbols)} symbols.")

while True:
    print(f"🔁 Starting scan cycle...")

    update_market_mode() if ENABLE_TREND_FILTERS else None

    all_signals = []

    for symbol in symbols:
        try:
            candles_by_tf = {
                tf: fetch_candles(symbol, tf)
                for tf in ["5m", "15m", "1h"]
            }

            score, breakdown = scan_market(symbol, candles_by_tf)

            if score >= 4:  # Score threshold for valid trade
                strategy_type = (
                    "Scalp" if breakdown['5m'] > 0 else
                    "Intraday" if breakdown['15m'] > 0 else
                    "Swing"
                )

                if (
                    (strategy_type == "Scalp" and not ENABLE_SCALP) or
                    (strategy_type == "Intraday" and not ENABLE_INTRADAY) or
                    (strategy_type == "Swing" and not ENABLE_SWING)
                ):
                    continue

                signal = {
                    "symbol": symbol,
                    "score": score,
                    "strategy": strategy_type,
                    "breakdown": breakdown
                }

                all_signals.append(signal)

                if SEND_SIGNAL_ALERTS:
                    send_telegram_signal(signal)

                if MODE == "LIVE":
                    risk = get_risk_per_trade(signal)
                    execute_trade(signal, risk)

                if ENABLE_SMART_EXIT_MANAGER:
                    pass  # Exit manager runs as part of executor or separate thread

                if ENABLE_AI_SIGNAL_MEMORY:
                    update_signal_memory(symbol, score)

        except Exception as e:
            print(f"⚠️ Error scanning {symbol}: {e}")
            continue

    if all_signals:
        print(f"✅ {len(all_signals)} high-score setups found.")
    else:
        print("❌ No valid trade setups found this cycle.")

    send_status_report(len(symbols), len(all_signals))

    time.sleep(SCAN_INTERVAL)
