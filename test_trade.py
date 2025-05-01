
import asyncio
from bybit_api import place_market_order
from logger import log
import time

# === Test API keys (override the ones in bybit_api.py) ===
TEST_API_KEY = "9LSEH2ZksKPSk1fJud"
TEST_API_SECRET = "eDjrnmIcgJD2FTwvuEDkocLVo3v7c7IqGuq0"

# Monkey patch (override the imported bybit_api variables)
bybit_api.BYBIT_API_KEY = TEST_API_KEY
bybit_api.BYBIT_API_SECRET = TEST_API_SECRET

async def test_trade():
    symbol = "BTCUSDT"   # ← Change to any tradable symbol you want to test
    qty = 0.0001         # ← Adjust quantity for small test
    side = "Buy"         # ← "Buy" or "Sell"
    market_type = "linear"  # "linear" for futures, "spot" for spot market

    log(f"🚀 Sending {side} market order for {symbol} | Qty: {qty}")
    log(f"🕒 Local UTC Timestamp: {int(time.time() * 1000)}")

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

        log(f"🟨 Raw Response: {result}")

        if result.get("retCode") == 0:
            log(f"✅ Test Trade Successful!")
        else:
            log(f"❌ Test Trade Failed | Code: {result.get('retCode')} | Msg: {result.get('retMsg')}")
            if result.get("retExtInfo"):
                log(f"ℹ️ Extended Info: {result['retExtInfo']}")
            if result.get("result"):
                log(f"🔍 Result Payload: {result['result']}")
            log("🧪 Suggestion: Check server time, IP, and signature logic.")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")

if __name__ == "__main__":
    asyncio.run(test_trade())
