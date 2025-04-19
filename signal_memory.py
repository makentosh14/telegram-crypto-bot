import time

# In-memory cache for recent signals
recent_signals = {}

# Time window in seconds to prevent duplicate signals (e.g., 30 minutes)
DUPLICATE_SIGNAL_WINDOW = 1800

def log_signal(symbol):
    recent_signals[symbol] = int(time.time())

def is_duplicate_signal(symbol):
    now = int(time.time())
    last_time = recent_signals.get(symbol, 0)
    return (now - last_time) < DUPLICATE_SIGNAL_WINDOW

def cleanup_old_signals():
    now = int(time.time())
    to_remove = [symbol for symbol, t in recent_signals.items() if now - t > DUPLICATE_SIGNAL_WINDOW]
    for symbol in to_remove:
        del recent_signals[symbol]
