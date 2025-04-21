# ai_memory.py

memory_db = {}

def log_trade_result(symbol, tf_scores, result):
    """
    Store which type of score profiles worked or failed.
    result: "win", "loss", or "breakeven"
    """
    profile_key = str(tf_scores)

    if profile_key not in memory_db:
        memory_db[profile_key] = {"win": 0, "loss": 0, "breakeven": 0, "total": 0}

    memory_db[profile_key][result] += 1
    memory_db[profile_key]["total"] += 1

def get_profile_confidence(tf_scores):
    """
    Returns confidence (0.0 to 1.0) based on past performance of similar score profiles.
    Can be used to filter weak signals.
    """
    profile_key = str(tf_scores)
    stats = memory_db.get(profile_key)

    if not stats or stats["total"] < 3:
        return 0.5  # neutral if no data

    win_rate = stats["win"] / stats["total"]
    return round(win_rate, 2)
