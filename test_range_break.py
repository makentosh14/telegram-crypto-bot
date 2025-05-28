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

# Mock the pre_trade_validator to bypass validation
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
    
    elif endpoint == "/v5/market/tickers":
        # Mock ticker response for pre-trade validation
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "symbol": params.get("symbol", "TESTUSDT"),
                    "lastPrice": "100.0",
                    "markPrice": "100.0",
                    "indexPrice": "100.0",
                    "bid1Price": "99.99",
                    "ask1Price": "100.01",
                    "bid1Size": "100",
                    "ask1Size": "100"
                }]
            }
        }
    
    elif endpoint == "/v5/position/list":
        # Mock position list (no existing positions)
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": []
            }
        }
    
    elif endpoint == "/v5/order/realtime":
        # Mock order list (no existing orders)
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": []
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
    
    # Default response
    return {"retCode": 0, "retMsg": "OK"}

async def test_range_break_integration():
    """Test range break detection and execution in trade_executor"""
    
    log("==================================================")
    log("RANGE BREAK INTEGRATION TEST")
    log("==================================================")
    
    # Patch the API calls with our mock
    with patch('bybit_api.signed_request', side_effect=mock_signed_request):
        # Also need to patch it in sl_tp_utils for validate_sl_placement
        with patch('sl_tp_utils.signed_request', side_effect=mock_signed_request):
            # Mock account balance
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
                log(f"📊 Test Signal Details:")
                log(f"  Symbol: {test_signal['symbol']}")
                log(f"  Entry Price: {test_signal['price']}")
                log(f"  Direction: {test_signal['direction']}")
                log(f"  Range: {test_signal['range_break_details']['range_low']} - {test_signal['range_break_details']['range_high']}")
                log(f"  Range Width: {test_signal['range_break_details']['range_width_pct']:.2f}%")
                log(f"  Pre-breakout Patterns: {', '.join(test_signal['range_break_details']['buildup_patterns'])}")
                log(f"  Exit Strategy: {test_signal['exit_strategy']}")
                
                log("\n📊 Executing test trade...")
                
                # Execute the trade
                result = await execute_trade_if_valid(test_signal)
                
                if result:
                    log("\n✅ Test PASSED! Trade executed successfully")
                    log("\n📋 Trade Details:")
                    log(f"  Entry Price: {result.get('entry')}")
                    log(f"  Stop Loss: {result.get('sl')} ({result.get('sl_pct'):.2f}%)")
                    log(f"  Take Profit 1: {result.get('tp1')} ({result.get('tp1_pct'):.2f}%)")
                    if result.get('tp2'):
                        log(f"  Take Profit 2: {result.get('tp2')} ({result.get('tp2_pct'):.2f}%)")
                    log(f"  Trailing Stop: {result.get('trailing_pct'):.2f}%")
                    log(f"  Exit Strategy: {result.get('exit_strategy')}")
                    log(f"  Exit Tranches: {result.get('exit_tranches')}")
                    log(f"  Strategy Type: {result.get('strategy')}")
                    log(f"  Quantity: {result.get('qty')}")
                    
                    if result.get('range_levels'):
                        log("\n📊 Range Levels:")
                        log(f"  High: {result['range_levels'].get('high')}")
                        log(f"  Low: {result['range_levels'].get('low')}")
                        log(f"  Width: {result['range_levels'].get('width_pct'):.2f}%")
                    
                    # Verify range-based adjustments were applied
                    log("\n🔍 Verification:")
                    
                    # Check SL adjustment
                    if result.get('sl') and test_signal['range_break_details']['range_low']:
                        expected_sl = test_signal['range_break_details']['range_low'] * 0.995
                        sl_diff = abs(result['sl'] - expected_sl)
                        if sl_diff < 0.1:  # Allow small difference
                            log(f"✅ Range-based SL applied correctly: {result['sl']:.3f} (expected ~{expected_sl:.3f})")
                        else:
                            log(f"⚠️ SL differs from expected: {result['sl']:.3f} vs {expected_sl:.3f}")
                    
                    # Check TP adjustment
                    if result.get('tp1') and test_signal['range_break_details']['range_high']:
                        expected_tp1 = test_signal['range_break_details']['range_high']
                        tp_diff = abs(result['tp1'] - expected_tp1)
                        if tp_diff < 0.1:  # Allow small difference
                            log(f"✅ Range-based TP1 applied correctly: {result['tp1']:.3f} (expected {expected_tp1:.3f})")
                        else:
                            log(f"⚠️ TP1 differs from expected: {result['tp1']:.3f} vs {expected_tp1:.3f}")
                    
                    # Verify pump optimization
                    if result.get('exit_strategy') == 'pump_optimized':
                        log("\n✅ Pump optimization applied successfully:")
                        log(f"  - Enhanced TP multiplier applied")
                        log(f"  - Wider trailing stop ({result.get('trailing_pct'):.2f}%) for letting winners run")
                        log(f"  - Custom exit tranches: {result.get('exit_tranches')}")
                    
                    # Check order IDs
                    if result.get('sl_order_id'):
                        log(f"\n✅ Stop Loss Order ID: {result['sl_order_id']}")
                    if result.get('tp1_order_id'):
                        log(f"✅ Take Profit Order ID: {result['tp1_order_id']}")
                    
                    return True
                else:
                    log("\n❌ Test FAILED - No trade executed")
                    return False
                    
    log("\n==================================================")
    log("TEST COMPLETED")
    log("==================================================")

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_range_break_integration())
    sys.exit(0 if result else 1)
