import os
import csv
import json
from datetime import datetime

LOG_PATH = "/mnt/data/bot_logs"
LOG_FILE = os.path.join(LOG_PATH, "trading_bot_activity.log")
TRADE_LOG_CSV = "/mnt/data/trade_logs/trade_setups.csv"

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

def log_trade_to_file(symbol, direction, entry, sl, tp1, tp2, result, score, trade_type, confidence, indicator_scores=None, used_indicators=None):
    """
    Log a structured trade result to CSV for later analysis, including indicator score breakdown.
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    with open(TRADE_LOG_CSV, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "time", "symbol", "direction", "entry", "sl", "tp1", "tp2",
            "result", "score", "trade_type", "confidence",
            "indicator_scores", "used_indicators"
        ])
        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "result": result,
            "score": score,
            "trade_type": trade_type,
            "confidence": confidence,
            "indicator_scores": json.dumps(indicator_scores or {}),
            "used_indicators": ", ".join(used_indicators or [])
        })
