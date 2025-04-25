# monitor.py

from telegram_bot import send_telegram_message
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log

active_trades = {}

def track_active_trade(symbol, trade_type, initial_score):
    active_trades[symbol] = {
        "score_history": [initial_score],
        "trade_type": trade_type,
        "cycles": 0,
        "exited": False
    }

def remove_trade(symbol):
    if symbol in active_trades:
        del active_trades[symbol]

def get_exit_threshold(trade_type):
    return {
        "Scalp": 6,
        "Intraday": 6,
        "Swing": 5
    }.get(trade_type, 6)

def get_exit_cycles(trade_type):
    return {
        "Scalp": 2,
        "Intraday": 3,
        "Swing": 4
    }.get(trade_type, 3)

async def monitor_trades(live_candles):
    for symbol, trade in list(active_trades.items()):
        if trade["exited"]:
            continue

        trade_type = trade["trade_type"]
        if symbol not in live_candles:
            continue

        try:
            candles_by_tf = {
                tf: list(live_candles[symbol][str(tf)]) for tf in ['1', '3', '5', '15', '30', '60', '240']
            }
        except Exception as e:
            log(f"Monitor: Failed to fetch candles for {symbol}: {e}", level="ERROR")
            continue

        score, tf_scores, _ = score_symbol(symbol, candles_by_tf)
        trade["score_history"].append(score)
        trade["cycles"] += 1

        # Exit if score remains too low for N cycles
        if score < get_exit_threshold(trade_type):
            if trade["cycles"] >= get_exit_cycles(trade_type):
                trade["exited"] = True
                await send_telegram_message(
                    f"⚠️ <b>Exit Signal Triggered</b>\n"
                    f"Symbol: <b>{symbol}</b>\n"
                    f"Score dropped to {score} after {trade['cycles']} cycles.\n"
                    f"<i>Monitoring suggests closing this trade.</i>"
                )
                log(f"📉 Score drop exit triggered for {symbol}")
                continue

        # Rebound alert if score previously dropped and recovered
        if len(trade["score_history"]) >= 3:
            if trade["score_history"][-3] < get_exit_threshold(trade_type) and score >= get_exit_threshold(trade_type) + 2:
                await send_telegram_message(
                    f"🔁 <b>Score Recovery Alert</b>\n"
                    f"Symbol: <b>{symbol}</b>\n"
                    f"Score dropped earlier but recovered to {score}.\n"
                    f"<i>Re-entry or hold may be considered.</i>"
                )

        # Detect bearish pattern after entry
        last_candles = candles_by_tf['1'][-2:]
        if detect_pattern(last_candles) in ["bearish_engulfing", "inverted_hammer"]:
            await send_telegram_message(
                f"⚠️ <b>Bearish Reversal Pattern</b> on {symbol}\n"
                f"<i>Reversal candle after entry. Watch closely.</i>"
            )

        # Check volume drop vs 20-period avg
        recent_vol = float(candles_by_tf['1'][-1]['volume'])
        avg_vol = get_average_volume(candles_by_tf['1'], window=20)
        if recent_vol < avg_vol * 0.5:
            await send_telegram_message(
                f"⚠️ <b>Volume Drop</b> on {symbol}\n"
                f"Latest volume is below 50% of average.\n"
                f"<i>Momentum fading. Watch this trade.</i>"
            )

        # Check flat price action
        closes = [float(c['close']) for c in candles_by_tf['1'][-5:]]
        if max(closes) - min(closes) < float(closes[-1]) * 0.002:
            await send_telegram_message(
                f"😴 <b>Flat Price Action</b> on {symbol}\n"
                f"<i>Volatility has dropped. Trend may be stalling.</i>"
            )
