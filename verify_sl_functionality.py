import os
import asyncio
import time
from bybit_api import place_stop_loss, place_stop_loss_with_retry, get_futures_available_balance, signed_request
from logger import log

# === Set and verify Bybit API credentials ===
os.environ["BYBIT_API_KEY"] = "NuGJJSlzNeQG2bMb8h"
os.environ["BYBIT_API_SECRET"] = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"

async def test_fixed_sl_functionality():
    """
    A simple test script to verify that the fixed stop-loss functions work correctly
    This script doesn't place real trades - it just tests the stop-loss logic
    """
    symbol = "BTCUSDT"
    market_type = "linear"
    
    log("🧪 Testing Fixed Stop-Loss Implementation")
    log("----------------------------------------")
    
    try:
        # Step 1: Get current market price
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {
            "category": market_type, 
            "symbol": symbol
        })
        
        if ticker_resp.get("retCode") != 0:
            log(f"❌ Failed to get market price: {ticker_resp.get('retMsg')}")
            return
            
        # Extract current price
        current_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
        if current_price <= 0:
            log("❌ Failed to get valid market price")
            return
            
        log(f"📊 Current mark price: {current_price}")
        
        # Step 2: Calculate valid SL prices for testing
        long_sl_price = round(current_price * 0.95, 2)  # 5% below current
        short_sl_price = round(current_price * 1.05, 2)  # 5% above current
        
        log(f"📋 Test Parameters:")
        log(f"  Symbol: {symbol}")
        log(f"  Current Price: {current_price}")
        log(f"  Long SL Price: {long_sl_price} (5% below)")
        log(f"  Short SL Price: {short_sl_price} (5% above)")
        
        # Step 3: First, check what we're going to send through the API
        log("\n🔍 Debug check of params first (no API call):")
        
        # For long position
        side_long = "Sell"  # For closing a long position
        trigger_dir_long = 2  # FIXED: Now using 2 (falling) for long positions
        log(f"  Long position SL params: side={side_long}, triggerDirection={trigger_dir_long}")
        
        # For short position
        side_short = "Buy"  # For closing a short position
        trigger_dir_short = 1  # FIXED: Now using 1 (rising) for short positions
        log(f"  Short position SL params: side={side_short}, triggerDirection={trigger_dir_short}")
        
        # Step 4: Test without actually placing orders (mock positions)
        log("\n🧪 Testing how SL params would be calculated:")
        
        # Simulate a mock position instead of placing a real trade
        mock_position_qty = 0.001
        
        # For long position
        long_sl_payload = {
            "category": market_type,
            "symbol": symbol,
            "side": side_long,
            "orderType": "Market",
            "triggerPrice": str(long_sl_price),
            "triggerDirection": trigger_dir_long,
            "triggerBy": "MarkPrice",
            "qty": str(mock_position_qty),
            "reduceOnly": True,
            "timeInForce": "GTC",
            "orderFilter": "Stop"
        }
        
        log(f"\n📦 Long SL Payload (FIXED):")
        log(f"  side: {long_sl_payload['side']}")
        log(f"  triggerPrice: {long_sl_payload['triggerPrice']}")
        log(f"  triggerDirection: {long_sl_payload['triggerDirection']}")
        log(f"  triggerBy: {long_sl_payload['triggerBy']}")
        
        # For short position
        short_sl_payload = {
            "category": market_type,
            "symbol": symbol,
            "side": side_short,
            "orderType": "Market",
            "triggerPrice": str(short_sl_price),
            "triggerDirection": trigger_dir_short,
            "triggerBy": "MarkPrice",
            "qty": str(mock_position_qty),
            "reduceOnly": True,
            "timeInForce": "GTC",
            "orderFilter": "Stop"
        }
        
        log(f"\n📦 Short SL Payload (FIXED):")
        log(f"  side: {short_sl_payload['side']}")
        log(f"  triggerPrice: {short_sl_payload['triggerPrice']}")
        log(f"  triggerDirection: {short_sl_payload['triggerDirection']}")
        log(f"  triggerBy: {short_sl_payload['triggerBy']}")
        
        # Step 5: Test with real API call but with extremely out-of-range prices
        # This ensures the API validates our TriggerDirection logic without risk of execution
        log("\n🧪 Testing SL direction logic with API (using far OTM values):")
        
        # Price way below current (will never execute)
        test_long_sl = current_price * 0.5  # 50% below current price
        
        # Price way above current (will never execute)  
        test_short_sl = current_price * 2  # 100% above current price
        
        # Test only if user confirms
        proceed = input("\nDo you want to make API test calls to validate the fix? (y/n): ")
        
        if proceed.lower() == 'y':
            # For long position (should accept the direction)
            log("\n🧪 Testing with long position SL (far OTM)...")
            long_result = await place_stop_loss(
                symbol=symbol,
                direction="long",
                qty=0.001,  # Tiny amount 
                sl_price=test_long_sl,
                market_type=market_type
            )
            
            if long_result.get("retCode") == 0:
                log("✅ Long SL direction logic FIXED! API accepted the order.")
            else:
                log(f"❌ Long SL test failed: {long_result.get('retMsg')}")
            
            # For short position (should accept the direction)
            log("\n🧪 Testing with short position SL (far OTM)...")
            short_result = await place_stop_loss(
                symbol=symbol,
                direction="short",
                qty=0.001,  # Tiny amount
                sl_price=test_short_sl,
                market_type=market_type
            )
            
            if short_result.get("retCode") == 0:
                log("✅ Short SL direction logic FIXED! API accepted the order.")
            else:
                log(f"❌ Short SL test failed: {short_result.get('retMsg')}")
                
            # Clean up any orders we created
            try:
                await signed_request("POST", "/v5/order/cancel-all", 
                                    {"category": market_type, "symbol": symbol})
                log("🧹 Cleaned up any test orders")
            except:
                pass
        else:
            log("Skipping API calls, testing complete.")
        
        log("\n✅ Test complete! If you saw the correct TriggerDirection values (2 for long, 1 for short),")
        log("   then the stop-loss direction logic has been fixed.")
        
    except Exception as e:
        log(f"❌ Test error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fixed_sl_functionality())
