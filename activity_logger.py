import os
import csv
from datetime import datetime

LOG_PATH = "/mnt/data/bot_logs"
LOG_FILE = os.path.join(LOG_PATH, "trading_bot_activity.log")
TRADE_LOG_CSV = os.path.join(LOG_PATH, "trade_log.csv")

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

def log_trade_to_file(symbol, direction, entry, sl, tp1, tp2, result, score, trade_type, confidence):
    """
    Log a structured trade result to CSV for later analysis.
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    with open(TRADE_LOG_CSV, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "time", "symbol", "direction", "entry", "sl", "tp1", "tp2",
                "result", "score", "trade_type", "confidence"
            ])
        writer.writerow([
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            direction,
            entry,
            sl,
            tp1,
            tp2,
            result,
            score,
            trade_type,
            confidence
        ])
