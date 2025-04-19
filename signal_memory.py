import json
import os
from datetime import datetime, timedelta

SIGNAL_MEMORY_FILE = "logs/signal_memory.json"

def load_signal_memory():
    if not os.path.exists(SIGNAL_MEMORY_FILE):
        return {}
    with open(SIGNAL_MEMORY_FILE, "r") as file:
        return json.load(file)

def save_signal_memory(memory):
    os.makedirs(os.path.dirname(SIGNAL_MEMORY_FILE), exist_ok=True)
    with open(SIGNAL_MEMORY_FILE, "w") as file:
        json.dump(memory, file, indent=2)

def is_duplicate_signal(symbol):
    memory = load_signal_memory()
    last_signal_time = memory.get(symbol)
    if last_signal_time:
        last_time = datetime.strptime(last_signal_time, "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() - last_time < timedelta(minutes=30):
            return True
    return False

def log_signal(symbol):
    memory = load_signal_memory()
    memory[symbol] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    save_signal_memory(memory)
