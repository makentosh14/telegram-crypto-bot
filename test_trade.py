import asyncio
from bybit_api import place_market_order
from logger import log

async def test_trade():
    symbol = "BTCUSDT"   # ← Change to any tradable symbol you want to test
    qty = 0.0001          # ← Adjust quantity for small test
    side = "Buy"         # ← "Buy" or "Sell"
    market_type = "linear"  # "linear" for futures, "spot" for spot market

    log(f"🚀 Sending {side} market order for {symbol} | Qty: {qty}")

    result = await place_market_order(
        symbol=symbol,
        side=side,
        qty=qty,
        market_type=market_type,
        reduce_only=False
    )

    if result and result.get("retCode") == 0:
        log(f"✅ Test Trade Successful: {result}")
    else:
        log(f"❌ Test Trade Failed: {result}")

if __name__ == "__main__":
    asyncio.run(test_trade())
