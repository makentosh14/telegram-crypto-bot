import asyncio
from bybit_api import signed_request

async def emergency_cleanup():
    print("🧹 Starting emergency cleanup...")
    
    # Get all open orders first
    try:
        orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear"
        })
        
        if orders_resp.get("retCode") == 0:
            orders = orders_resp.get("result", {}).get("list", [])
            print(f"Found {len(orders)} open orders")
            
            # Cancel each order individually
            for order in orders:
                symbol = order.get("symbol")
                order_id = order.get("orderId")
                
                cancel_result = await signed_request("POST", "/v5/order/cancel", {
                    "category": "linear",
                    "symbol": symbol,
                    "orderId": order_id
                })
                
                if cancel_result.get("retCode") == 0:
                    print(f"✅ Cancelled {order_id} for {symbol}")
                else:
                    print(f"❌ Failed {order_id}: {cancel_result.get('retMsg')}")
                
                await asyncio.sleep(0.2)
                
        print("✅ Cleanup complete")
        
    except Exception as e:
        print(f"❌ Error: {e}")

asyncio.run(emergency_cleanup())
