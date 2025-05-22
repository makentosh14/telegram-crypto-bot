import asyncio
from bybit_api import signed_request

async def emergency_cleanup():
    # Cancel ALL orders to reset
    result = await signed_request("POST", "/v5/order/cancel-all", {
        "category": "linear"
    })
    print(f"Cleanup result: {result}")

asyncio.run(emergency_cleanup())
