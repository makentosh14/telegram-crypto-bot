import os
from datetime import datetime

LOG_PATH = "/mnt/data/bot_logs"
LOG_FILE = os.path.join(LOG_PATH, "trading_bot_activity.log")

# Ensure directory exists
os.makedirs(LOG_PATH, exist_ok=True)

def write_log(message, level="INFO"):
    """
    Write a formatted log message to the trading_bot_activity.log file.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] [{level.upper()}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
