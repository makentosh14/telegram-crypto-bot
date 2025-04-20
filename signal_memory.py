import json
import os
from datetime import datetime, timedelta

SIGNAL_LOG_FILE = "signal_log.json"
DUPLICATE_WINDOW_MINUTES = 60  # Don't repeat trades for the same coin within this time

def load_signal_log():
    if not os.path.exists(SIGNAL_LOG_FILE):
        return {}
    with open(SIGNAL_LOG_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_signal_log(log):
    with open(SIGNAL_LOG_FILE, "w") as f:
        json.dump(log, f)

def log_signal(symbol):
    log = load_signal_log()
    log[symbol] = datetime.utcnow().isoformat()
    save_signal_log(log)

def is_duplicate_signal(symbol):
    log = load_signal_log()
    if symbol not in log:
        return False
    last_time = datetime.fromisoformat(log[symbol])
    return datetime.utcnow() - last_time < timedelta(minutes=DUPLICATE_WINDOW_MINUTES)

def clean_old_signals():
    log = load_signal_log()
    now = datetime.utcnow()
    updated_log = {
        symbol: timestamp for symbol, timestamp in log.items()
        if now - datetime.fromisoformat(timestamp) < timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    }
    save_signal_log(updated_log)
