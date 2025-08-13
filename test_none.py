#!/usr/bin/env python3
import asyncio

async def test_functions():
    try:
        from monitor import get_current_price, get_current_price_enhanced
        from active_trade_scanner import get_current_price as scanner_price
        
        print("✅ Functions imported successfully")
        
        # Test with SUNUSDT
        price1 = await get_current_price("SUNUSDT")
        price2 = await get_current_price_enhanced("SUNUSDT")  
        price3 = await scanner_price("SUNUSDT")
        
        print(f"Monitor price: {price1}")
        print(f"Enhanced price: {price2}")
        print(f"Scanner price: {price3}")
        
        if any(p and p > 0 for p in [price1, price2, price3]):
            print("✅ Price functions working!")
        else:
            print("⚠️ All returned None - check API connection")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_functions())
