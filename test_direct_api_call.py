import os
import asyncio
import time
import json
from logger import log

# === Set API credentials ===
os.environ["BYBIT_API_KEY"] = "NuGJJSlzNeQG2bMb8h"
os.environ["BYBIT_API_SECRET"] = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"

async def test_direct_api_call():
    """
    This test directly calls the Bybit API with the correct triggerDirection 
    values without going through any wrapper functions
    """
    import hmac
    import hashlib
    import time
    import aiohttp
    
    # === Configuration ===
    BASE_URL = "https://api.bybit.com"
    API_KEY = os.environ["BYBIT_API_KEY"]
    API_SECRET = os.environ["BYBIT_API_SECRET"]
    SYMBOL = "BTCUSDT"
    
    # === Get Current Price ===
    async def make_request(method, endpoint, params=None):
        """Make a request to Bybit API with proper authentication"""
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        if params is None:
            params = {}
            
        params["timestamp"] = timestamp
        params["recvWindow"] = recv_window
        params["api_key"] = API_KEY
        
        # Create signature
        param_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()
        params["sign"] = signature
        
        url = f"{BASE_URL}{endpoint}"
        
        # Make request
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, params=params) as response:
                    return await response.json()
            else:
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                async with session.post(url, data=params, headers=headers) as response:
                    return await response.json()
    
    # Get current price
    ticker_response = await make_request("GET", "/v5/market/tickers", 
                                        {"category": "linear", "symbol": SYMBOL})
    
    if ticker_response.get("retCode") != 0:
        log(f"❌ Error fetching ticker: {ticker_response}")
        return
        
    mark_price = float(ticker_response["result"]["list"][0]["markPrice"])
    log(f"📊 Current {SYMBOL} price: {mark_price}")
    
    # === Test Long Position SL ===
    # For a long position, SL should be below current price with triggerDirection=2
    long_sl_price = round(mark_price * 0.9, 2)  # 10% below current price
    
    long_sl_params = {
        "category": "linear",
        "symbol": SYMBOL,
        "side": "Sell",  # Sell to close a long position
        "orderType": "Market",
        "triggerPrice": str(long_sl_price),
        "triggerDirection": 2,  # FALLING (correct for long)
        "triggerBy": "MarkPrice",
        "qty": "0.001",  # Small quantity
        "reduceOnly": True,
        "timeInForce": "GTC",
        "orderFilter": "Stop",
        "positionIdx": 0
    }
    
    # === Test Short Position SL ===
    # For a short position, SL should be above current price with triggerDirection=1
    short_sl_price = round(mark_price * 1.1, 2)  # 10% above current price
    
    short_sl_params = {
        "category": "linear",
        "symbol": SYMBOL,
        "side": "Buy",  # Buy to close a short position
        "orderType": "Market",
        "triggerPrice": str(short_sl_price),
        "triggerDirection": 1,  # RISING (correct for short)
        "triggerBy": "MarkPrice",
        "qty": "0.001",  # Small quantity
        "reduceOnly": True,
        "timeInForce": "GTC",
        "orderFilter": "Stop",
        "positionIdx": 0
    }
    
    # === Execute Tests ===
    log("\n=== Testing Long Position SL (triggerDirection=2) ===")
    log(f"SL Price: {long_sl_price} (below mark: {mark_price})")
    log(f"Parameters: {json.dumps(long_sl_params, indent=2)}")
    
    confirm = input("\nDo you want to send this test order to Bybit? (y/n): ")
    if confirm.lower() == 'y':
        result = await make_request("POST", "/v5/order/create", long_sl_params)
        log(f"Result: {json.dumps(result, indent=2)}")
        
        if result.get("retCode") == 110026:  # Position not found
            log("✅ API accepted the triggerDirection value (position error is expected)")
        elif result.get("retCode") == 0:
            log("✅ Order placed successfully! Cancel it immediately.")
            # Cancel the order
            await make_request("POST", "/v5/order/cancel-all", 
                             {"category": "linear", "symbol": SYMBOL})
            log("Order cancelled.")
        else:
            log(f"❌ Test failed: {result.get('retMsg')}")
            
    log("\n=== Testing Short Position SL (triggerDirection=1) ===")
    log(f"SL Price: {short_sl_price} (above mark: {mark_price})")
    log(f"Parameters: {json.dumps(short_sl_params, indent=2)}")
    
    confirm = input("\nDo you want to send this test order to Bybit? (y/n): ")
    if confirm.lower() == 'y':
        result = await make_request("POST", "/v5/order/create", short_sl_params)
        log(f"Result: {json.dumps(result, indent=2)}")
        
        if result.get("retCode") == 110026:  # Position not found
            log("✅ API accepted the triggerDirection value (position error is expected)")
        elif result.get("retCode") == 0:
            log("✅ Order placed successfully! Cancel it immediately.")
            # Cancel the order
            await make_request("POST", "/v5/order/cancel-all", 
                             {"category": "linear", "symbol": SYMBOL})
            log("Order cancelled.")
        else:
            log(f"❌ Test failed: {result.get('retMsg')}")
    
    log("\n=== Cleanup ===")
    # Final cleanup of any orders
    cleanup = await make_request("POST", "/v5/order/cancel-all", 
                               {"category": "linear", "symbol": SYMBOL})
    log(f"Cleanup result: {cleanup}\n")
    
    log("✅ Test complete. If the API accepted the triggerDirection values (no direction errors),")
    log("  then the fix is correct. Expected errors about position not found are normal.")

if __name__ == "__main__":
    asyncio.run(test_direct_api_call())
