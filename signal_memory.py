import time

# In-memory signal log (can be replaced with persistent DB in future)
signal_log = {}

# Time in seconds to remember each signal (e.g., 2 hours)
SIGNAL_EXPIRY = 2 * 60 * 60

def log_signal(symbol):
    now = time.time()
    signal_log[symbol] = now

def is_duplicate_signal(symbol):
    now = time.time()
    if symbol in signal_log:
        if now - signal_log[symbol] < SIGNAL_EXPIRY:
            return True
    return False

def clean_old_signals():
    now = time.time()
    expired = [symbol for symbol, timestamp in signal_log.items() if now - timestamp > SIGNAL_EXPIRY]
    for symbol in expired:
        del signal_log[symbol]
