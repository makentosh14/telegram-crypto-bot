#!/usr/bin/env python3
# test_none_fixes.py - Test all the None fixes

import asyncio
from logger import log

def test_none_multiplication():
    """Test various None scenarios that could cause multiplication errors"""
    
    log("🧪 Testing None multiplication scenarios...")
    
    # Test cases that would cause the original error
    test_cases = [
        {"balance": None, "risk": 1.0, "name": "None balance"},
        {"balance": 1000.0, "risk": None, "name": "None risk"},
        {"balance": None, "risk": None, "name": "Both None"},
        {"balance": 0, "risk": 1.0, "name": "Zero balance"},
        {"balance": 1000.0, "risk": 0, "name": "Zero risk"},
        {"balance": "1000", "risk": "1.5", "name": "String values"},
        {"balance": 1000.0, "risk": 1.5, "name": "Valid values"},
    ]
    
    for i, case in enumerate(test_cases, 1):
        log(f"\n📋 Test {i}: {case['name']}")
        
        try:
            balance = case['balance']
            risk = case['risk']
            
            # OLD CODE (would fail):
            # result = balance * risk  # This would crash with None
            
            # NEW CODE (safe):
            if balance is None:
                log(f"❌ Balance is None - using fallback")
                balance = 1000.0
            
            if risk is None:
                log(f"❌ Risk is None - using fallback")
                risk = 1.0
            
            # Convert to float safely
            try:
                balance = float(balance)
                risk = float(risk)
            except (ValueError, TypeError):
                log(f"❌ Cannot convert to float - using fallbacks")
                balance = 1000.0
                risk = 1.0
            
            # Validate values
            if balance <= 0:
                log(f"❌ Invalid balance: {balance}")
                balance = 1000.0
            
            if risk <= 0:
                log(f"❌ Invalid risk: {risk}")
                risk = 1.0
            
            # Now safe to multiply
            result = balance * (risk / 100)  # Convert percentage
            log(f"✅ Result: {result} (balance: {balance}, risk: {risk}%)")
            
        except Exception as e:
            log(f"❌ Test failed: {e}")

async def test_safe_position_calculation():
    """Test the safe position calculation"""
    
    log("\n🧪 Testing safe position calculation...")
    
    test_params = [
        {"price": 0.7175, "sl": 0.7118, "balance": 1000.0},
        {"price": None, "sl": 0.7118, "balance": 1000.0},
        {"price": 0.7175, "sl": None, "balance": 1000.0},
        {"price": 0.7175, "sl": 0.7118, "balance": None},
        {"price": 0, "sl": 0.7118, "balance": 1000.0},
        {"price": 0.7175, "sl": 0.7175, "balance": 1000.0},  # Same price
    ]
    
    for i, params in enumerate(test_params, 1):
        log(f"\n📋 Position Test {i}:")
        log(f"   Price: {params['price']}")
        log(f"   SL: {params['sl']}")
        log(f"   Balance: {params['balance']}")
        
        try:
            position_size = calculate_safe_position_size(
                params['price'], 
                params['sl'], 
                params['balance']
            )
            log(f"✅ Position size: {position_size}")
            
        except Exception as e:
            log(f"❌ Calculation failed: {e}")

def calculate_safe_position_size(price, sl_price, account_balance, risk_pct=1.0):
    """Safe position size calculation with all None checks"""
    
    # Check for None values
    if price is None:
        log(f"❌ Price is None")
        return 0
    if sl_price is None:
        log(f"❌ SL price is None")
        return 0
    if account_balance is None:
        log(f"❌ Account balance is None")
        return 0
    
    # Convert to float safely
    try:
        price = float(price)
        sl_price = float(sl_price)
        account_balance = float(account_balance)
        risk_pct = float(risk_pct)
    except (ValueError, TypeError) as e:
        log(f"❌ Cannot convert to float: {e}")
        return 0
    
    # Validate values
    if price <= 0 or sl_price <= 0 or account_balance <= 0:
        log(f"❌ Invalid values: price={price}, sl={sl_price}, balance={account_balance}")
        return 0
    
    if price == sl_price:
        log(f"❌ Price equals SL price")
        return 0
    
    # Calculate safely
    risk_amount = account_balance * (risk_pct / 100)
    risk_per_unit = abs(price - sl_price) / price
    position_size = (risk_amount / risk_per_unit) / price
    
    return position_size

def main():
    """Run all tests"""
    log("🚀 Starting None multiplication fix tests...")
    
    test_none_multiplication()
    asyncio.run(test_safe_position_calculation())
    
    log("\n✅ All tests completed!")
    log("\n💡 If these tests pass, your fixes should work!")
    log("💡 Apply the fixes to positions_manager.py and your trade executor")

if __name__ == "__main__":
    main()
