# signal_memory.py

import time

signal_cache = {}

def is_duplicate_signal(symbol, cooldown=1800):
    """
    Prevents sending repeated signals for the same symbol.
    cooldown: seconds to wait before allowing another signal (default 30 min)
    """
    now = time.time()
    last_signal_time = signal_cache.get(symbol)
    if last_signal_time and (now - last_signal_time) < cooldown:
        return True
    return False

def log_signal(symbol):
    """Logs the signal time for a symbol."""
    signal_cache[symbol] = time.time()
