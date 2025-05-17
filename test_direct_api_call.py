import os
import asyncio
import json
import hmac
import hashlib
import time
import aiohttp
from logger import log

# === Configuration ===
API_KEY = "NuGJJSlzNeQG2bMb8h"
API_SECRET = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"
BASE_URL = "https://api.bybit.com"

async def signed_request(method, endpoint, params=None):
    """Make a signed request to the Bybit API directly using the v5 auth method"""
    if params is None:
        params = {}
        
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    if method.upper() == "GET":
        # For GET requests, params are added to the URL
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        signature_payload = timestamp + API_KEY + recv_window + query_string
        signature = hmac.new(API_SECRET.encode(), signature_payload.encode(), hashlib.sha256).hexdigest()
        
        headers = {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window
        }
        
        url = f"{BASE_URL}{endpoint}?{query_string}" if query_string else f"{BASE_URL}{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                return await response.json()
    else:
        # For POST requests, params are in the body
        body = json.dumps(params)
        signature_payload = timestamp + API_KEY + recv_window + body
        signature = hmac.new(API_SECRET.encode(), signature_payload.encode(), hashlib.sha256).hexdigest()
        
        headers = {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }
        
        url = f"{BASE_URL}{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=body) as response:
                return await response.json()

async def test_sl_configurations():
    """Test various stop-loss configurations to determine the expected parameters"""
    symbol = "BTCUSDT"
    
    # First, get the current price
    ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": "linear", "symbol": symbol})
    if ticker_resp.get("retCode") != 0:
        log(f"❌ Failed to get ticker: {ticker_resp}")
        return
        
    mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
    log(f"📊 Current {symbol} price: {mark_price}")
    
    # Set up test parameters
    long_sl_price = round(mark_price * 0.95, 2)  # 5% below current price
    short_sl_price = round(mark_price * 1.05, 2)  # 5% above current price
    
    log("\n==== Testing LONG position SL configurations ====")
    log(f"Current price: {mark_price}, SL price: {long_sl_price}")
    
    # Test configurations for LONG position
    long_configs = [
        {
            "desc": "LONG - TriggerDirection=2 (Falling)",
            "params": {
                "category": "linear",
                "symbol": symbol,
                "side": "Sell",
                "orderType": "Market",
                "qty": "0.001",
                "triggerPrice": str(long_sl_price),
                "triggerDirection": 2,
                "triggerBy": "MarkPrice",
                "timeInForce": "GTC",
                "reduceOnly": True,
                "orderFilter": "Stop"
            }
        },
        {
            "desc": "LONG - TriggerDirection=1 (Rising)",
            "params": {
                "category": "linear",
                "symbol": symbol,
                "side": "Sell",
                "orderType": "Market",
                "qty": "0.001",
                "triggerPrice": str(long_sl_price),
                "triggerDirection": 1,
                "triggerBy": "MarkPrice",
                "timeInForce": "GTC",
                "reduceOnly": True,
                "orderFilter": "Stop"
            }
        }
    ]
    
    # Run tests for LONG position
    for config in long_configs:
        log(f"\nTesting: {config['desc']}")
        log(f"Params: {json.dumps(config['params'], indent=2)}")
        
        should_test = input("Test this configuration? (y/n): ")
        if should_test.lower() == 'y':
            result = await signed_request("POST", "/v5/order/create", config['params'])
            log(f"Result: {json.dumps(result, indent=2)}")
            
            # If successful, cancel immediately
            if result.get("retCode") == 0:
                log("✅ Order placed successfully, cancelling...")
                order_id = result.get("result", {}).get("orderId")
                cancel_result = await signed_request("POST", "/v5/order/cancel", {
                    "category": "linear",
                    "symbol": symbol,
                    "orderId": order_id
                })
                log(f"Cancel result: {cancel_result}")
    
    log("\n==== Testing SHORT position SL configurations ====")
    log(f"Current price: {mark_price}, SL price: {short_sl_price}")
    
    # Test configurations for SHORT position
    short_configs = [
        {
            "desc": "SHORT - TriggerDirection=1 (Rising)",
            "params": {
                "category": "linear",
                "symbol": symbol,
                "side": "Buy",
                "orderType": "Market",
                "qty": "0.001",
                "triggerPrice": str(short_sl_price),
                "triggerDirection": 1,
                "triggerBy": "MarkPrice",
                "timeInForce": "GTC",
                "reduceOnly": True,
                "orderFilter": "Stop"
            }
        },
        {
            "desc": "SHORT - TriggerDirection=2 (Falling)",
            "params": {
                "category": "linear",
                "symbol": symbol,
                "side": "Buy",
                "orderType": "Market",
                "qty": "0.001",
                "triggerPrice": str(short_sl_price),
                "triggerDirection": 2,
                "triggerBy": "MarkPrice",
                "timeInForce": "GTC",
                "reduceOnly": True,
                "orderFilter": "Stop"
            }
        }
    ]
    
    # Run tests for SHORT position
    for config in short_configs:
        log(f"\nTesting: {config['desc']}")
        log(f"Params: {json.dumps(config['params'], indent=2)}")
        
        should_test = input("Test this configuration? (y/n): ")
        if should_test.lower() == 'y':
            result = await signed_request("POST", "/v5/order/create", config['params'])
            log(f"Result: {json.dumps(result, indent=2)}")
            
            # If successful, cancel immediately
            if result.get("retCode") == 0:
                log("✅ Order placed successfully, cancelling...")
                order_id = result.get("result", {}).get("orderId")
                cancel_result = await signed_request("POST", "/v5/order/cancel", {
                    "category": "linear",
                    "symbol": symbol,
                    "orderId": order_id
                })
                log(f"Cancel result: {cancel_result}")
    
    # Final cleanup
    cleanup = await signed_request("POST", "/v5/order/cancel-all", {
        "category": "linear",
        "symbol": symbol
    })
    log(f"\nFinal cleanup result: {cleanup}")

if __name__ == "__main__":
    asyncio.run(test_sl_configurations())
