import os
import asyncio
import time
from bybit_api import place_market_order, place_stop_loss, get_futures_available_balance, signed_request
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

    try:
        # === Step 1: Get current market price first ===
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {
            "category": market_type, 
            "symbol": symbol
        })
        
        if ticker_resp.get("retCode") != 0:
            log(f"❌ Failed to get market price: {ticker_resp.get('retMsg')}")
            return
            
        # Extract current price and calculate SL price
        current_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("lastPrice", 0))
        if current_price <= 0:
            log("❌ Failed to get valid market price")
            return
            
        log(f"📊 Current market price: {current_price}")
            
        # === Step 2: Place market order ===
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
            order_id = result.get("result", {}).get("orderId")
            
            # === Step 3: Wait briefly for the order to be processed ===
            log("⏳ Waiting 2 seconds for order to be processed...")
            await asyncio.sleep(2)
            
            # === Step 4: Fetch position to confirm entry ===
            position_resp = await signed_request("GET", "/v5/position/list", {
                "category": market_type,
                "symbol": symbol
            })
            
            if position_resp.get("retCode") != 0:
                log(f"❌ Failed to get position: {position_resp.get('retMsg')}")
                return
                
            positions = position_resp.get("result", {}).get("list", [])
            if not positions:
                log("❌ No position found after order execution")
                return
                
            position = positions[0]
            entry_price = float(position.get("avgPrice", 0))
            position_size = float(position.get("size", 0))
            
            if position_size <= 0:
                log("❌ Position size is zero - order may have failed")
                return
                
            log(f"📈 Confirmed position - Entry price: {entry_price}, Size: {position_size}")
            
            # === Step 5: Calculate valid SL price (5% below entry for long) ===
            sl_price = round(entry_price * 0.95, 2)  # 5% below entry for testing
            log(f"🛑 Setting SL at {sl_price} (5% below entry)")
            
            # === Step 6: Place stop loss order ===
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
                
                # === Step 7: Verify SL order exists ===
                sl_order_resp = await signed_request("GET", "/v5/order/realtime", {
                    "category": market_type,
                    "symbol": symbol,
                    "orderId": sl_order_id
                })
                
                if sl_order_resp.get("retCode") == 0 and sl_order_resp.get("result", {}).get("list"):
                    sl_order = sl_order_resp.get("result", {}).get("list")[0]
                    log(f"✅ SL Order verified: Status = {sl_order.get('orderStatus')}, Trigger = {sl_order.get('triggerPrice')}")
                else:
                    log("⚠️ Could not verify SL order")
                
                # === Step 8: Close position with market order ===
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
                    log("🔄 Test complete - trade cycle verified with SL placement")
                else:
                    log(f"❌ Test Trade Exit Failed: {close_result.get('retMsg')}")
            else:
                log(f"❌ Stop Loss Placement Failed: {sl_result.get('retMsg')}")
                
                # Still close the position even if SL failed
                await place_market_order(
                    symbol=symbol,
                    side="Sell",
                    qty=qty,
                    market_type=market_type,
                    reduce_only=True
                )
                log("✅ Position closed with market order")
        else:
            log(f"❌ Test Trade Failed!")
            log(f"📛 Error Code: {ret_code}")
            log(f"📛 Error Message: {ret_msg}")

    except Exception as e:
        log(f"❌ Exception occurred during test trade: {e}")
        
        # Emergency cleanup - try to close any open position
        try:
            position_resp = await signed_request("GET", "/v5/position/list", {
                "category": market_type,
                "symbol": symbol
            })
            
            if position_resp.get("retCode") == 0:
                positions = position_resp.get("result", {}).get("list", [])
                for pos in positions:
                    if float(pos.get("size", 0)) > 0:
                        await place_market_order(
                            symbol=symbol,
                            side="Sell",
                            qty=qty,
                            market_type=market_type,
                            reduce_only=True
                        )
                        log("✅ Emergency position cleanup completed")
        except:
            log("⚠️ Failed to perform emergency cleanup")

if __name__ == "__main__":
    asyncio.run(test_trade_with_sl())
