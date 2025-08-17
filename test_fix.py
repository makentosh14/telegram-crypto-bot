# test_fix.py
import asyncio
from positions_manager import calculate_quantity, get_account_balance

async def test_fixed_calculation():
    print("Testing fixed calculation...")
    
    # Test with actual values from your logs
    symbol = "ENAUSDT"
    price = 0.7175
    sl_price = 0.7117600000000001
    
    # Get balance (should now handle None safely)
    balance = await get_account_balance()
    print(f"Balance: {balance}")
    
    # Calculate quantity (should now handle None safely)
    qty = await calculate_quantity(
        symbol=symbol,
        price=price,
        sl_price=sl_price,
        account_balance=balance,
        candles_by_tf={},
        trade_type="Scalp",
        strategy="core_strategy", 
        confidence=74.6,
        risk_pct=1.0,  # 1% risk
        market_type="linear"
    )
    
    print(f"Calculated quantity: {qty}")
    
    if qty > 0:
        print("✅ Fix successful!")
        return True
    else:
        print("❌ Still issues")
        return False

if __name__ == "__main__":
    asyncio.run(test_fixed_calculation())
