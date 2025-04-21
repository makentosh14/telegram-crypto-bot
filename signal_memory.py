# signal_memory.py

import time

signal_cache = {}

def is_duplicate_signal(symbol, cooldown=1800):
    """
    Prevents sending repeated signals for the same coin.
    cooldown: seconds to wait before allowing another signal
    """
    now = time.time()
    if symbol in signal_cache:
        if now - signal_cache[symbol] < cooldown:
            return True
    return False

def log_signal(symbol):
    signal_cache[symbol] = time.time()
