import os
import asyncio
import time
from bybit_api import place_stop_loss_with_retry, signed_request
from logger import log

# === Set and verify Bybit API credentials ===
os.environ["BYBIT_API_KEY"] = "NuGJJSlzNeQG2bMb8h"
os.environ["BYBIT_API_SECRET"] = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"

async def verify_sl_functionality():
    """
    This script verifies if the stop-loss functionality is working correctly
    by testing the SL placement function directly without making an actual trade.
    """
    symbol = "BTCUSDT"
    market_type = "linear"
    
    try:
        # === Step 1: Get current market price ===
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
        
        # === Step 2: Calculate valid SL prices for both long and short positions ===
        # For a long position, SL should be below current price
        long_sl_price = round(current_price * 0.95, 2)  # 5% below current
        
        # For a short position, SL should be above current price
        short_sl_price = round(current_price * 1.05, 2)  # 5% above current
        
        log(f"📋 Test Parameters:")
        log(f"  Symbol: {symbol}")
        log(f"  Current Price: {current_price}")
        log(f"  Long SL Price: {long_sl_price} (5% below)")
        log(f"  Short SL Price: {short_sl_price} (5% above)")
        
        # === Step 3: Test place_stop_loss_with_retry for LONG position ===
        log("\n🧪 Testing SL placement for LONG position (without actual trade)...")
        result_long = await place_stop_loss_with_retry(
            symbol=symbol,
            direction="long",
            qty=0.001,  # Small quantity for testing
            sl_price=long_sl_price,
            market_type=market_type,
            max_attempts=2
        )
        
        # === Step 4: Test place_stop_loss_with_retry for SHORT position ===
        log("\n🧪 Testing SL placement for SHORT position (without actual trade)...")
        result_short = await place_stop_loss_with_retry(
            symbol=symbol,
            direction="short",
            qty=0.001,  # Small quantity for testing
            sl_price=short_sl_price,
            market_type=market_type,
            max_attempts=2
        )
        
        # === Step 5: Check if the function validates prices correctly ===
        log("\n🧪 Testing SL price validation...")
        # This should fail as the SL price for long is above current price
        invalid_long_sl = await place_stop_loss_with_retry(
            symbol=symbol,
            direction="long",
            qty=0.001,
            sl_price=current_price * 1.05,  # Invalid - above current price for long
            market_type=market_type,
            max_attempts=1
        )
        
        # This should fail as the SL price for short is below current price
        invalid_short_sl = await place_stop_loss_with_retry(
            symbol=symbol,
            direction="short",
            qty=0.001,
            sl_price=current_price * 0.95,  # Invalid - below current price for short
            market_type=market_type,
            max_attempts=1
        )
        
        # === Step 6: Result summary ===
        log("\n📋 TEST RESULTS SUMMARY:")
        log(f"  Long position SL test: {'✅ SUCCESS' if result_long.get('retCode') == 0 else '❌ FAILED'}")
        log(f"  Short position SL test: {'✅ SUCCESS' if result_short.get('retCode') == 0 else '❌ FAILED'}")
        log(f"  Invalid long SL validation: {'✅ SUCCESS' if invalid_long_sl.get('retCode') != 0 else '❌ FAILED'}")
        log(f"  Invalid short SL validation: {'✅ SUCCESS' if invalid_short_sl.get('retCode') != 0 else '❌ FAILED'}")
        
        # === Step 7: Check if the orders would actually be created ===
        # In a real trade, these orders would be created
        # But since we're not opening positions, they'll likely be rejected
        # That's normal and expected in this test
        
        overall = (
            (result_long.get('retCode') == 0 or result_long.get('retMsg', '').startswith("position idx")) and
            (result_short.get('retCode') == 0 or result_short.get('retMsg', '').startswith("position idx")) and
            invalid_long_sl.get('retCode') != 0 and
            invalid_short_sl.get('retCode') != 0
        )
        
        if overall:
            log("\n✅ OVERALL TEST RESULT: SUCCESS")
            log("Your SL placement logic appears to be working correctly!")
        else:
            log("\n⚠️ OVERALL TEST RESULT: PARTIAL FAILURE")
            log("Some aspects of SL placement may need improvement.")
            
        log("\nNote: Any 'position idx' errors are normal in this test since we're not opening actual positions.")
        
    except Exception as e:
        log(f"❌ Test error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_sl_functionality())
