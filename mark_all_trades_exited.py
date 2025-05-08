import json

path = "monitor_active_trades.json"

try:
    with open(path, "r") as f:
        trades = json.load(f)

    for symbol in trades:
        trades[symbol]["exited"] = True

    with open(path, "w") as f:
        json.dump(trades, f, indent=2)

    print("✅ All trades marked as exited.")
except Exception as e:
    print(f"❌ Error: {e}")
