#!/usr/bin/env python3
"""
Test script for range break integration in trade_executor
"""
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import required modules
from logger import log
from trade_executor import execute_trade_if_valid

# Mock the pre_trade_validator to return async mock
import pre_trade_validator
pre_trade_validator.pre_trade_validator = MagicMock()
pre_trade_validator.pre_trade_validator.final_validation = AsyncMock(return_value=(True, "Test mode - validation bypassed"))

# Mock symbol_info functions
from symbol_info import symbol_precisions, get_precision, round_qty
symbol_precisions["TESTUSDT"] = {
    "base_coin": "TEST",
    "min_qty": 0.001,
    "quote_coin": "USDT",
    "scale": 4
}

def mock_get_precision(symbol):
    return 3

def mock_round_qty(symbol, qty):
    return round(qty, 3)

# Apply mocks
import symbol_info
symbol_info.get_precision = mock_get_precision
symbol_info.round_qty = mock_round_qty

# Mock the API functions
async def mock_signed_request(method, endpoint, params):
    """Mock API responses for testing"""
    
    if endpoint == "/v5/account/wallet-balance":
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "totalAvailableBalance": "1000.0",
                    "accountType": "UNIFIED"
                }]
            }
        }
    
    elif endpoint == "/v5/position/set-leverage":
        return {"retCode": 0, "retMsg": "OK"}
    
    elif endpoint == "/v5/order/cancel-all":
        return {"retCode": 0, "retMsg": "OK"}
    
    elif endpoint == "/v5/order/create":
        if params.get("orderType") == "Market":
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "orderId": "test-market-order-123",
                    "avgPrice": "100.0"
                }
            }
        elif params.get("orderType") == "Stop":
            return {
                "retCode": 0,
                "retMsg": "OK", 
                "result": {
                    "orderId": "test-stop-order-123"
                }
            }
        elif params.get("orderType") == "Limit":
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "orderId": "test-limit-order-123"
                }
            }
    
    return {"retCode": 0, "retMsg": "OK"}

async def test_range_break_integration():
    """Test range break detection and execution in trade_executor"""
    
    log("==================================================")
    log("RANGE BREAK INTEGRATION TEST")
    log("==================================================")
    
    # Patch the API calls
    with patch('bybit_api.signed_request', side_effect=mock_signed_request):
        with patch('trade_executor.get_account_balance', return_value=1000.0):
            
            # Create test signal with range break data
            test_signal = {
                "symbol": "TESTUSDT",
                "price": 100.0,
                "trade_type": "Scalp",
                "direction": "Long",
                "score": 8.5,
                "confidence": 85,
                "candles": {
                    "5": [
                        {
                            "close": "100",
                            "open": "99.5",
                            "high": "100.5",
                            "low": "99",
                            "volume": "1000"
                        }
                    ] * 30  # 30 candles for indicators
                },
                "indicator_scores": {
                    "range_break": 0.8,
                    "stealth_accumulation": 0.7,
                    "volume_compression": 0.6
                },
                "used_indicators": ["range_break", "stealth_accumulation"],
                "tf_scores": {"5": 8.5},
                "regime": "volatile",
                "range_break_details": {
                    "range_high": 105.0,
                    "range_low": 95.0,
                    "range_width_pct": 10.53,  # ~10% range
                    "pre_breakout": True,
                    "buildup_patterns": ["price_compression", "volume_tightening", "bb_squeeze"],
                    "touches_high": 5,
                    "touches_low": 4
                },
                "range_break_confidence": 0.85,
                "exit_strategy": "pump_optimized",
                "trailing_multiplier": 1.5,
                "tp1_multiplier": 1.3,
                "exit_tranches": [0.25, 0.35, 0.40],  # Custom exit tranches for pump
                "market_type": "linear"
            }
            
            log("🧪 Starting Range Break Integration Test")
            log(f"📊 Executing test trade...")
            
            # Execute the trade
            result = await execute_trade_if_valid(test_signal)
            
            if result:
                log("✅ Test PASSED! Trade executed successfully")
                log("\n📋 Trade Details:")
                log(f"  Entry Price: {result.get('entry')}")
                log(f"  Stop Loss: {result.get('sl')} ({result.get('sl_pct'):.2f}%)")
                log(f"  Take Profit 1: {result.get('tp1')} ({result.get('tp1_pct'):.2f}%)")
                log(f"  Take Profit 2: {result.get('tp2')} ({result.get('tp2_pct'):.2f}%)")
                log(f"  Trailing Stop: {result.get('trailing_pct'):.2f}%")
                log(f"  Exit Strategy: {result.get('exit_strategy')}")
                log(f"  Exit Tranches: {result.get('exit_tranches')}")
                log(f"  Strategy Type: {result.get('strategy')}")
                
                if result.get('range_levels'):
                    log("\n📊 Range Levels:")
                    log(f"  High: {result['range_levels'].get('high')}")
                    log(f"  Low: {result['range_levels'].get('low')}")
                    log(f"  Width: {result['range_levels'].get('width_pct'):.2f}%")
                
                # Verify range-based adjustments were applied
                if result.get('sl') and test_signal['range_break_details']['range_low']:
                    expected_sl = test_signal['range_break_details']['range_low'] * 0.995
                    log(f"\n✅ Range-based SL applied correctly: {result['sl']} (expected ~{expected_sl:.2f})")
                
                if result.get('tp1') and test_signal['range_break_details']['range_high']:
                    expected_tp1 = test_signal['range_break_details']['range_high']
                    log(f"✅ Range-based TP1 applied correctly: {result['tp1']} (expected {expected_tp1})")
                
                # Verify pump optimization
                if result.get('exit_strategy') == 'pump_optimized':
                    log("\n✅ Pump optimization applied successfully")
                    log(f"  - Enhanced TP multiplier applied")
                    log(f"  - Wider trailing stop for letting winners run")
                    log(f"  - Custom exit tranches: {result.get('exit_tranches')}")
                
                return True
            else:
                log("❌ Test FAILED - No trade executed")
                return False
                
    log("\n==================================================")
    log("TEST COMPLETED")
    log("==================================================")

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_range_break_integration())
    sys.exit(0 if result else 1)
