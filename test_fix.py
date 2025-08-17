# test_with_mock_balance.py - Test with simulated balance

import asyncio
from positions_manager import calculate_quantity

async def test_with_different_balances():
    """Test position sizing with different balance amounts"""
    
    print("🧪 Testing position calculation with different balances...")
    
    # Test parameters from your ENAUSDT trade
    symbol = "ENAUSDT"
    price = 0.7175
    sl_price = 0.7117600000000001
    risk_pct = 1.0  # 1% risk
    
    # Test with different balance amounts
    test_balances = [
        {"balance": 0.00001005, "name": "Your Current Balance"},
        {"balance": 10.0, "name": "Small Account ($10)"},
        {"balance": 100.0, "name": "Medium Account ($100)"},
        {"balance": 1000.0, "name": "Large Account ($1000)"},
        {"balance": 10000.0, "name": "Big Account ($10000)"}
    ]
    
    for test in test_balances:
        balance = test["balance"]
        name = test["name"]
        
        print(f"\n📊 Testing {name}: ${balance}")
        
        try:
            qty = await calculate_quantity(
                symbol=symbol,
                price=price,
                sl_price=sl_price,
                account_balance=balance,
                candles_by_tf={},
                trade_type="Scalp",
                strategy="core_strategy",
                confidence=74.6,
                risk_pct=risk_pct,
                market_type="linear"
            )
            
            if qty > 0:
                # Calculate trade value
                trade_value = qty * price
                risk_amount = balance * (risk_pct / 100)
                
                print(f"   ✅ Position Size: {qty:.4f} ENAUSDT")
                print(f"   💰 Trade Value: ${trade_value:.2f}")
                print(f"   🎯 Risk Amount: ${risk_amount:.2f}")
                print(f"   📈 Risk/Reward: 1.5:1 (0.8% SL vs 1.2% TP)")
            else:
                print(f"   ❌ Position size too small: {qty}")
                print(f"   💡 Need at least $1-10 to trade meaningfully")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

async def simulate_successful_trade():
    """Simulate what your ENAUSDT trade would look like with proper funding"""
    
    print("\n" + "="*60)
    print("🚀 SIMULATING YOUR ENAUSDT TRADE WITH $100 BALANCE")
    print("="*60)
    
    # Your exact trade parameters
    symbol = "ENAUSDT"
    price = 0.7175
    sl_price = 0.7117600000000001
    tp_price = 0.72611  # 1.2% profit target
    balance = 100.0  # Simulated balance
    risk_pct = 1.0
    
    # Calculate position
    qty = await calculate_quantity(
        symbol=symbol,
        price=price,
        sl_price=sl_price,
        account_balance=balance,
        candles_by_tf={},
        trade_type="Scalp",
        strategy="core_strategy",
        confidence=74.6,
        risk_pct=risk_pct,
        market_type="linear"
    )
    
    if qty > 0:
        trade_value = qty * price
        risk_amount = balance * (risk_pct / 100)
        
        # Calculate potential P&L
        if price < tp_price:  # Long trade
            profit_if_tp = qty * (tp_price - price)
            loss_if_sl = qty * (price - sl_price)
        
        print(f"📊 Trade Summary:")
        print(f"   Symbol: {symbol}")
        print(f"   Direction: Long")
        print(f"   Entry Price: ${price}")
        print(f"   Stop Loss: ${sl_price:.6f} (-0.8%)")
        print(f"   Take Profit: ${tp_price:.6f} (+1.2%)")
        print(f"   Position Size: {qty:.4f} {symbol}")
        print(f"   Trade Value: ${trade_value:.2f}")
        print(f"   Risk Amount: ${risk_amount:.2f}")
        print(f"")
        print(f"💰 Potential Outcomes:")
        print(f"   If TP Hit: +${profit_if_tp:.2f} profit")
        print(f"   If SL Hit: -${loss_if_sl:.2f} loss")
        print(f"   Risk/Reward: {profit_if_tp/loss_if_sl:.1f}:1")
        
        return True
    else:
        print("❌ Position size still too small even with $100")
        return False

if __name__ == "__main__":
    asyncio.run(test_with_different_balances())
    asyncio.run(simulate_successful_trade())
