# main.py (Final Version: Real-Time Scanning + Smart Monitoring + Trade Direction)

import asyncio
from scanner import fetch_symbols
from websocket_candles import live_candles, stream_candles, SUPPORTED_INTERVALS
from score import score_symbol, determine_trade_type, determine_direction
from telegram_bot import send_telegram_message, format_trade_signal, send_monitoring_alert
from trend_filters import get_trend_context
from signal_memory import log_signal, is_duplicate_signal
from config import MIN_SCORE_THRESHOLD, DEFAULT_LEVERAGE
from performance_tracker import track_signal
from logger import log
from trade_monitor import monitor_trade_setups

TIMEFRAMES = SUPPORTED_INTERVALS

active_trades = {}

async def run_bot():
    log("\U0001F680 Bot starting...")

    symbols = await fetch_symbols()
    log(f"✅ Fetched {len(symbols)} symbols.")

    asyncio.create_task(stream_candles(symbols))
    await asyncio.sleep(5)

    while True:
        try:
            trend_context = await get_trend_context()
            btc_trend = trend_context['btc_trend']
            altseason = trend_context['altseason']

            for i, symbol in enumerate(symbols, 1):
                if symbol not in live_candles:
                    log(f"⏩ [{i}/{len(symbols)}] Skipping {symbol}: no live candles yet")
                    continue

                try:
                    candles_by_tf = {
                        tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
                    }
                except Exception as e:
                    log(f"❌ [{i}/{len(symbols)}] Error fetching candles for {symbol}: {e}", level="ERROR")
                    continue

                if not all(len(candles_by_tf[tf]) >= 30 for tf in TIMEFRAMES):
                    log(f"⏩ [{i}/{len(symbols)}] Skipping {symbol}: not enough candles")
                    continue

                score, tf_scores = score_symbol(symbol, candles_by_tf)
                trade_type = determine_trade_type(tf_scores)
                direction = determine_direction(tf_scores)

                log(f"\U0001F4CA [{i}/{len(symbols)}] {symbol} | Score: {score} | TFs: {tf_scores} | Type: {trade_type} | Dir: {direction}")

                if score >= MIN_SCORE_THRESHOLD and not is_duplicate_signal(symbol):
                    log_signal(symbol)
                    track_signal(symbol, score)

                    price = float(candles_by_tf['1'][-1]['close']) if '1' in candles_by_tf else 1.0

                    sl_pct = 0.7 if trade_type == "Scalp" else (1.5 if trade_type == "Intraday" else 2.5)
                    tp1_pct = 1.5 if trade_type == "Scalp" else (3.0 if trade_type == "Intraday" else 6.0)
                    trailing_pct = 0.3 if trade_type == "Scalp" else (0.6 if trade_type == "Intraday" else 1.0)
                    risk_pct = 3.0 if trade_type == "Scalp" else (2.0 if trade_type == "Intraday" else 1.0)

                    leverage = DEFAULT_LEVERAGE

                    sl = round(price * (1 - sl_pct / 100), 4) if direction == "Long" else round(price * (1 + sl_pct / 100), 4)
                    tp1 = round(price * (1 + tp1_pct / 100), 4) if direction == "Long" else round(price * (1 - tp1_pct / 100), 4)

                    msg = format_trade_signal(
                        symbol=symbol,
                        score=score,
                        tf_scores=tf_scores,
                        trend=trend_context,
                        entry_price=price,
                        sl=sl,
                        tp1=tp1,
                        trade_type=trade_type,
                        direction=direction,
                        trailing_pct=trailing_pct,
                        leverage=leverage,
                        risk_pct=risk_pct
                    )

                    await send_telegram_message(msg)

                    active_trades[symbol] = {
                        "score": score,
                        "type": trade_type,
                        "direction": direction,
                        "cycles": 0
                    }

                # Monitor all active trades
                if symbol in active_trades:
                    monitoring_alert = monitor_trade_setups(symbol, tf_scores, active_trades)
                    if monitoring_alert:
                        await send_monitoring_alert(monitoring_alert)

        except Exception as e:
            log(f"❌ Error in main loop: {e}", level="ERROR")

        await asyncio.sleep(0.5)

if __name__ == "__main__":
    log("\U0001F527 DEBUG TEST: main.py is running...")
    asyncio.run(run_bot())
