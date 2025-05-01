import asyncio
import time
from bybit_api import place_market_order
from logger import log

async def test_trade():
    symbol = "BTCUSDT"
    qty = 0.0001
    side = "Buy"
    market_type = "linear"

    log(f"🚀 Sending {side} market order for {symbol} | Qty: {qty}")
    timestamp = int(time.time() * 1000)
    log(f"🕒 Local UTC Timestamp: {timestamp}")

    try:
        result = await place_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            market_type=market_type,
            reduce_only=False
        )

        if not result:
            log("❌ No response received from Bybit!")
            return

        log(f"🟨 Raw Response: {result}")

        ret_code = result.get("retCode")
        ret_msg = result.get("retMsg")

        if ret_code == 0:
            log("✅ Test Trade Successful!")
        else:
            log(f"❌ Test Trade Failed | Code: {ret_code} | Msg: {ret_msg}")
            if result.get("retExtInfo"):
                log(f"ℹ️ Extended Info: {result['retExtInfo']}")
            if result.get("result"):
                log(f"🔍 Result Payload: {result['result']}")
            log("🧪 Suggestion: Double-check server time sync, signature format, and IP whitelisting.")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")

if __name__ == "__main__":
    asyncio.run(test_trade())
