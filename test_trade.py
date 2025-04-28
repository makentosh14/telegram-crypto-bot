import asyncio
from bybit_api import place_market_order
from logger import log

async def test_trade():
    symbol = "BTCUSDT"      # Trading Futures (Perpetual)
    qty = 0.0001            # Small test quantity (~$6–$7)
    side = "Buy"            # Buy position
    market_type = "linear"  # "linear" = Futures market

    log(f"🚀 Sending {side} market order for {symbol} | Qty: {qty}")

    try:
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
    except Exception as e:
        log(f"⛔ Error during test trade: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_trade())
