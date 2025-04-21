# test_trade.py

import asyncio
import sys
from trade_executor import execute_trade_if_valid
from trend_filters import get_trend_context

async def test_trade():
    if len(sys.argv) < 4:
        print("Usage: python test_trade.py <symbol> <side> <score>")
        print("Example: python test_trade.py BTCUSDT long 5")
        return

    symbol = sys.argv[1].upper()
    side = sys.argv[2].lower()
    score = int(sys.argv[3])

    # Fake TF score map
    tf_scores = {"1": score}

    # Simulate current trend
    trend_context = get_trend_context()

    signal = {
        "symbol": symbol,
        "score": score,
        "tf_scores": tf_scores,
        "btc_trend": trend_context["btc_trend"],
        "altseason": trend_context["altseason"],
        "side": side  # Optional, in case your executor uses it
    }

    print(f"🚀 Executing test trade for {symbol} with score {score} and trend: {trend_context}")
    await execute_trade_if_valid(signal, max_risk=0.005)  # 0.5% risk

if __name__ == "__main__":
    asyncio.run(test_trade())
