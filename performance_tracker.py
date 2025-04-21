# performance_tracker.py

import datetime

signal_log = {}
missed_pumps = []

def track_signal(symbol, score):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    signal_log[symbol] = {
        "score": score,
        "time": now,
        "status": "open"
    }

def mark_trade_outcome(symbol, result):  # result: "win", "loss", "breakeven"
    if symbol in signal_log:
        signal_log[symbol]["status"] = result

def log_missed_pump(symbol, reason=""):
    missed_pumps.append((symbol, reason))

def get_daily_summary():
    total = len(signal_log)
    wins = sum(1 for s in signal_log.values() if s["status"] == "win")
    losses = sum(1 for s in signal_log.values() if s["status"] == "loss")
    breakevens = sum(1 for s in signal_log.values() if s["status"] == "breakeven")

    win_rate = (wins / total) * 100 if total > 0 else 0
    return {
        "total_signals": total,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": round(win_rate, 2),
        "missed_pumps": missed_pumps[-10:]
    }

def reset_daily_log():
    signal_log.clear()
    missed_pumps.clear()
