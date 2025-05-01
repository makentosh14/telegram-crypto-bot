import asyncio
import time
from bybit_api import place_market_order
from logger import log


async def test_trade():
    symbol = "BTCUSDT"
    qty = 0.0001
    side = "Buy"
    market_type = "linear"

    # Logging request metadata
    log(f"🚀 Attempting test trade...")
    log(f"📌 Symbol: {symbol}")
    log(f"📌 Side: {side}")
    log(f"📌 Quantity: {qty}")
    log(f"📌 Market Type: {market_type}")
    log(f"🕒 Local UTC Timestamp (ms): {int(time.time() * 1000)}")

    try:
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            market_type=market_type,
            reduce_only=False
        )

        if not result:
            log("❌ No response received from Bybit API!")
            return

        log(f"🟨 Raw Response: {result}")

        ret_code = result.get("retCode")
        ret_msg = result.get("retMsg")

        if ret_code == 0:
            log("✅ Test Trade Successful!")
        else:
            log(f"❌ Test Trade Failed!")
            log(f"📛 Error Code: {ret_code}")
            log(f"📛 Error Message: {ret_msg}")

            if result.get("retExtInfo"):
                log(f"ℹ️ Extended Info: {result['retExtInfo']}")
            if result.get("result"):
                log(f"🔍 Result Payload: {result['result']}")

            # Error-specific suggestions
            if ret_code == 10001:
                log("🧪 Likely Causes for retCode 10001:")
                log("    - ❌ Incorrect signature (check signing payload and JSON body)")
                log("    - ❌ Wrong Content-Type or double encoding (use content=body, NOT json=...)")
                log("    - ❌ IP not whitelisted (check Bybit API key settings)")
                log("    - ❌ Server time mismatch (sync time via NTP)")
                log("    - ❌ Old/invalid API keys")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")


if __name__ == "__main__":
    asyncio.run(test_trade())
