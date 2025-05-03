# monitor.py

from telegram_bot import send_telegram_message
from score import score_symbol
from pattern_detector import detect_pattern
from volume import get_average_volume
from logger import log
from exit_manager import should_trail_stop  # ✅ NEW

active_trades = {}

def track_active_trade(symbol, trade_type, initial_score, entry_price=None, direction=None, trailing_pct=None):
    active_trades[symbol] = {
        "score_history": [initial_score],
        "trade_type": trade_type,
        "entry_price": entry_price,
        "direction": direction,
        "cycles": 0,
        "exited": False,
        "trailing_pct": trailing_pct,
        "trailing_sl": None  # ✅ NEW: stores last updated SL to avoid spamming
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
        direction = trade["direction"]
        entry_price = trade["entry_price"]

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

        # === SMART TRAILING STOP LOGIC === ✅
        current_price = float(candles_by_tf['1'][-1]['close'])
        trailing_pct = trade.get("trailing_pct")
        if trailing_pct and entry_price:
            new_sl = should_trail_stop(entry_price, current_price, direction.lower(), candles=candles_by_tf['1'],
                                       trigger_pct=trailing_pct * 2, trail_pct=trailing_pct)

            if new_sl and new_sl != trade.get("trailing_sl"):
                trade["trailing_sl"] = new_sl
                await send_telegram_message(
                    f"🔐 <b>Trailing Stop Updated</b>\n"
                    f"<b>{symbol}</b> | New SL: {new_sl} | Price: {current_price}\n"
                    f"<i>Smart SL activated by trailing logic.</i>"
                )
                log(f"🔐 Smart SL updated for {symbol} to {new_sl}")

        # === Exit if score stays low too long ===
        if score < get_exit_threshold(trade_type):
            if trade["cycles"] >= get_exit_cycles(trade_type):
                trade["exited"] = True
                await send_telegram_message(
                    f"⚠️ <b>Exit Signal Triggered</b>\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Score:</b> {score} after {trade['cycles']} cycles.\n"
                    f"<i>Monitoring suggests closing this trade.</i>"
                )
                log(f"📉 Score drop exit triggered for {symbol}")
                continue

        # Rebound alert
        if len(trade["score_history"]) >= 3:
            if trade["score_history"][-3] < get_exit_threshold(trade_type) and score >= get_exit_threshold(trade_type) + 2:
                await send_telegram_message(
                    f"🔁 <b>Score Recovery Alert</b>\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Recovered Score:</b> {score}\n"
                    f"<i>Re-entry or hold may be considered.</i>"
                )

        # Detect bearish pattern
        last_candles = candles_by_tf['1'][-2:]
        pattern = detect_pattern(last_candles)
        if pattern in ["bearish_engulfing", "inverted_hammer"]:
            await send_telegram_message(
                f"⚠️ <b>Bearish Reversal Pattern</b> on {symbol}\n"
                f"<i>Pattern: {pattern} after entry. Watch closely.</i>"
            )

        # Volume drop warning
        recent_vol = float(candles_by_tf['1'][-1]['volume'])
        avg_vol = get_average_volume(candles_by_tf['1'], window=20)
        if recent_vol < avg_vol * 0.5:
            await send_telegram_message(
                f"⚠️ <b>Volume Drop</b> on {symbol}\n"
                f"Latest volume is below 50% of average.\n"
                f"<i>Momentum fading. Watch this trade.</i>"
            )

        # Flat price warning
        closes = [float(c['close']) for c in candles_by_tf['1'][-5:]]
        if max(closes) - min(closes) < float(closes[-1]) * 0.002:
            await send_telegram_message(
                f"😴 <b>Flat Price Action</b> on {symbol}\n"
                f"<i>Volatility has dropped. Trend may be stalling.</i>"
            )
