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
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] [{level.upper()}] {message}\n"
    try:
        with open("/mnt/data/bot_logs/trading_bot_activity.log", "a") as f:
            f.write(line)
    except Exception as e:
        print(f"Logging error: {e}")

def log_trade_to_file(
    symbol, direction, entry, sl, tp1, tp2, result, score, trade_type, confidence,
    tf_scores=None, indicator_scores=None, used_indicators=None,
    pattern_detected=None, whale_signal=False, volume_spike=False, sl_strategy=None
):
    """
    Log a structured trade result to CSV for later analysis.
    Includes scoring breakdowns, indicators, pattern/volume/whale flags, and SL strategy.
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    try:
        with open(TRADE_LOG_CSV, mode='a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "symbol", "direction", "entry", "sl", "tp1", "tp2",
                "result", "score", "trade_type", "confidence",
                "tf_scores", "indicator_scores", "used_indicators",
                "pattern_detected", "whale_signal", "volume_spike", "sl_strategy"
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
                "tf_scores": json.dumps(tf_scores or {}),
                "indicator_scores": json.dumps(indicator_scores or {}),
                "used_indicators": json.dumps(used_indicators or []),
                "pattern_detected": pattern_detected,
                "whale_signal": whale_signal,
                "volume_spike": volume_spike,
                "sl_strategy": sl_strategy
            })
    except Exception as e:
        write_log(f"❌ Failed to log trade: {e}", level="ERROR")
