import json
import os

MEMORY_FILE = "ai_memory.json"
memory_db = {}

def clean_key(tf_scores):
    """
    Normalize scores to 1 decimal place to group similar profiles.
    """
    return str({k: round(v, 1) for k, v in tf_scores.items()})

def log_trade_result(symbol, tf_scores, result):
    """
    Store which type of score profiles worked or failed.
    result: "win", "loss", or "breakeven"
    """
    profile_key = clean_key(tf_scores)

    if profile_key not in memory_db:
        memory_db[profile_key] = {"win": 0, "loss": 0, "breakeven": 0, "total": 0}

    memory_db[profile_key][result] += 1
    memory_db[profile_key]["total"] += 1

    save_memory()

def get_profile_confidence(tf_scores):
    """
    Returns confidence (0.0 to 1.0) based on past performance of similar score profiles.
    Can be used to filter or adjust signal strength.
    """
    profile_key = clean_key(tf_scores)
    stats = memory_db.get(profile_key)

    if not stats or stats["total"] < 3:
        return 0.5  # neutral base confidence

    win_rate = stats["win"] / stats["total"]
    return round(win_rate, 2)

def save_memory():
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory_db, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save AI memory: {e}")

def load_memory():
    global memory_db
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                memory_db = json.load(f)
            print("🔁 AI memory loaded from disk.")
        except Exception as e:
            print(f"❌ Failed to load AI memory: {e}")
