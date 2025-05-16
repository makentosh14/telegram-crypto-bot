import os
import asyncio
import time
from bybit_api import place_market_order, place_stop_loss, get_futures_available_balance
from logger import log

# === Set and verify Bybit API credentials ===
os.environ["BYBIT_API_KEY"] = "NuGJJSlzNeQG2bMb8h"
os.environ["BYBIT_API_SECRET"] = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"

if not os.environ.get("BYBIT_API_KEY") or not os.environ.get("BYBIT_API_SECRET"):
    log("❌ Missing Bybit API credentials in environment variables.")
    exit(1)

async def test_trade_with_sl():
    # === Settings for the test trade ===
    symbol = "BTCUSDT"  # You can change this to any symbol you want to test
    qty = 0.001  # Very small quantity for testing
    side = "Buy"  # For a long position
    market_type = "linear"
    
    # Check balance first
    balance = await get_futures_available_balance()
    log(f"💰 Available balance: {balance} USDT")
    
    if balance < 10:  # Ensure you have at least $10 for testing
        log("❌ Insufficient balance for test")
        return
    
    log(f"🚀 Attempting test trade...")
    log(f"📌 Symbol: {symbol}")
    log(f"📌 Side: {side}")
    log(f"📌 Quantity: {qty}")
    log(f"📌 Market Type: {market_type}")
    log(f"🕒 Local UTC Timestamp (ms): {int(time.time() * 1000)}")

    try:
        # === Step 1: Place market order ===
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

        log(f"🟨 Market Order Response: {result}")

        ret_code = result.get("retCode")
        ret_msg = result.get("retMsg")

        if ret_code == 0:
            log("✅ Test Trade Entry Successful!")
            entry_price = float(result.get("result", {}).get("avgPrice", 0))
            log(f"📈 Entry price: {entry_price}")
            
            # === Step 2: Get current price for SL calculation ===
            # Calculate a stop loss 1% below entry (for long position)
            sl_price = entry_price * 0.99
            log(f"🛑 Setting SL at {sl_price} (1% below entry)")
            
            # === Step 3: Place stop loss order ===
            sl_result = await place_stop_loss(
                symbol=symbol,
                direction="long",  # since we bought
                qty=qty,
                sl_price=sl_price,
                market_type=market_type
            )
            
            log(f"🟨 Stop Loss Response: {sl_result}")
            
            if sl_result.get("retCode") == 0:
                log("✅ Stop Loss Placement Successful!")
                sl_order_id = sl_result.get("result", {}).get("orderId")
                log(f"🆔 SL Order ID: {sl_order_id}")
                
                # === Step 4: Check active position ===
                log("⏳ Waiting 5 seconds to verify position...")
                await asyncio.sleep(5)
                
                # Wait for a moment, then close position with market order
                log("🔄 Now closing position with market order...")
                close_result = await place_market_order(
                    symbol=symbol,
                    side="Sell",  # opposite of entry
                    qty=qty,
                    market_type=market_type,
                    reduce_only=True
                )
                
                log(f"🟨 Close Position Response: {close_result}")
                
                if close_result.get("retCode") == 0:
                    log("✅ Test Trade Exit Successful!")
                else:
                    log(f"❌ Test Trade Exit Failed: {close_result.get('retMsg')}")
            else:
                log(f"❌ Stop Loss Placement Failed: {sl_result.get('retMsg')}")
        else:
            log(f"❌ Test Trade Failed!")
            log(f"📛 Error Code: {ret_code}")
            log(f"📛 Error Message: {ret_msg}")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")

if __name__ == "__main__":
    asyncio.run(test_trade_with_sl())
