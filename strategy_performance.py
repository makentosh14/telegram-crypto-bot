import json
import os
from collections import deque
from statistics import mean

PERF_LOG_PATH = "strategy_performance_log.json"
MAX_HISTORY = 50  # Track last 50 results per strategy

# In-memory cache
strategy_history = {}

# Load from disk on startup
if os.path.exists(PERF_LOG_PATH):
    try:
        with open(PERF_LOG_PATH, "r") as f:
            data = json.load(f)
            for strategy, entries in data.items():
                strategy_history[strategy] = deque(entries, maxlen=MAX_HISTORY)
    except Exception as e:
        print(f"❌ Failed to load strategy performance log: {e}")

def save_history():
    try:
        with open(PERF_LOG_PATH, "w") as f:
            json.dump({k: list(v) for k, v in strategy_history.items()}, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save strategy performance: {e}")

def log_strategy_result(strategy_name: str, result: str, pnl: float):
    if strategy_name not in strategy_history:
        strategy_history[strategy_name] = deque(maxlen=MAX_HISTORY)
    strategy_history[strategy_name].append({
        "result": result,
        "pnl": pnl
    })
    save_history()

def get_strategy_stats(strategy_name: str):
    history = strategy_history.get(strategy_name, [])
    if not history:
        return {"win_rate": 0, "avg_pnl": 0, "count": 0}

    wins = sum(1 for r in history if r["result"] == "win")
    losses = sum(1 for r in history if r["result"] == "loss")
    count = wins + losses
    win_rate = round((wins / count) * 100, 1) if count else 0
    avg_pnl = round(mean(r["pnl"] for r in history), 2) if count else 0

    return {
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "count": count
    }
