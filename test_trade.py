async def test_trade():
    symbol = "BTCUSDT"
    qty = 0.0001
    side = "Buy"
    market_type = "linear"

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
