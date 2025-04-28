import asyncio
from bybit_api import place_market_order
from logger import log
import bybit_api_async
bybit_api.BYBIT_API_KEY = TEST_API_KEY
bybit_api.BYBIT_API_SECRET = TEST_API_SECRET

async def test_trade():
    symbol = "BTCUSDT"   # ← Change to any tradable symbol you want to test
    qty = 0.0001         # ← Adjust quantity for small test
    side = "Buy"         # ← "Buy" or "Sell"
    market_type = "linear"  # "linear" for futures, "spot" for spot market

    log(f"🚀 Sending {side} market order for {symbol} | Qty: {qty}")

    try:
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            market_type=market_type,
            reduce_only=False
        )

        if result is None:
            log(f"❌ No response received from Bybit!")
            return

        if result.get("retCode") == 0:
            log(f"✅ Test Trade Successful: {result}")
        else:
            log(f"❌ Test Trade Failed: {result}")
            if "retMsg" in result:
                log(f"⚠️ Reason: {result['retMsg']}")
            else:
                log(f"⚠️ No specific reason provided by Bybit!")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")

if __name__ == "__main__":
    asyncio.run(test_trade())
