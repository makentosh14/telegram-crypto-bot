import os
import csv
import json
from datetime import datetime

LOG_PATH = "/mnt/data/bot_logs"
TRADE_LOG_PATH = "/mnt/data/trade_logs"
LOG_FILE = os.path.join(LOG_PATH, "trading_bot_activity.log")
TRADE_LOG_CSV = os.path.join(TRADE_LOG_PATH, "trade_setups.csv")

# Ensure directories exist
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(TRADE_LOG_PATH, exist_ok=True)

def write_log(message, level="INFO"):
    """
    Write a formatted log message to the trading_bot_activity.log file.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] [{level.upper()}] {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except Exception as e:
        print(f"Logging error: {e}")

def log_trade_to_file(symbol, direction, entry, sl, tp1, tp2, result, score, trade_type, confidence, indicator_scores=None, used_indicators=None):
    """
    Log a structured trade result to CSV for later analysis, including indicator score breakdown.
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    try:
        with open(TRADE_LOG_CSV, mode='a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "symbol", "direction", "entry", "sl", "tp1", "tp2",
                "result", "score", "trade_type", "confidence",
                "indicator_scores", "used_indicators"
            ])
            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
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
                "used_indicators": json.dumps(used_indicators or [])
            })
    except Exception as e:
        write_log(f"❌ Failed to log trade: {e}", level="ERROR")
