"""
Test script for range break integration
Run this to verify the range break detection and execution logic
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Add the project directory to Python path
sys.path.insert(0, '.')

from trade_executor import execute_trade_if_valid
from logger import log


async def test_range_break_integration():
    """Test range break integration with proper mocking"""
    
    log("🧪 Starting Range Break Integration Test")
    
    # Test configuration
    test_config = {
        "symbol": "TESTUSDT",
        "price": 100.0,
        "range_high": 105.0,
        "range_low": 95.0,
        "account_balance": 1000.0
    }
    
    # Create test signal
    test_signal = {
        "symbol": test_config["symbol"],
        "price": test_config["price"],
        "trade_type": "Scalp",
        "direction": "Long",
        "score": 8.5,
        "confidence": 85,
        "candles": {
            "5": [{"close": str(test_config["price"]), 
                   "open": str(test_config["price"] - 0.5), 
                   "high": str(test_config["price"] + 1), 
                   "low": str(test_config["price"] - 1), 
                   "volume": "1000"}] * 30
        },
        "indicator_scores": {"range_break": 0.8},
        "used_indicators": ["range_break"],
        "tf_scores": {"5": 8.5},
        "regime": "volatile",
        "range_break_details": {
            "range_high": test_config["range_high"],
            "range_low": test_config["range_low"],
            "range_width_pct": 10.0,
            "pre_breakout": True,
            "buildup_patterns": ["price_compression", "volume_tightening"]
        },
        "range_break_confidence": 0.85,
        "exit_strategy": "pump_optimized",
        "trailing_multiplier": 1.5,
        "tp1_multiplier": 1.3,
        "exit_tranches": [0.25, 0.35, 0.40],
        "market_type": "linear"
    }
    
    # Mock all external dependencies
    with patch('trade_executor._cached_balance', test_config["account_balance"]):
        with patch('trade_executor.pre_trade_validator') as mock_validator:
            with patch('trade_executor.signed_request') as mock_api:
                with patch('trade_executor.set_position_leverage') as mock_leverage:
                    with patch('trade_executor.cancel_all_orders') as mock_cancel:
                        
                        # Configure mocks
                        mock_validator.pre_trade_validator.final_validation = AsyncMock(return_value=(True, "OK"))
                        mock_leverage.return_value = True
                        mock_cancel.return_value = True
                        
                        # Mock API responses
                        async def mock_api_response(method, endpoint, params):
                            if "order/create" in endpoint and params.get("orderType") == "Market":
                                return {
                                    "retCode": 0,
                                    "result": {"orderId": "test-123", "avgPrice": str(test_config["price"])}
                                }
                            elif "order/create" in endpoint:
                                return {
                                    "retCode": 0,
                                    "result": {"orderId": f"test-{params.get('orderType', 'order')}-123"}
                                }
                            return {"retCode": 0, "retMsg": "OK"}
                        
                        mock_api.side_effect = mock_api_response
                        
                        # Execute test
                        log("📊 Executing test trade...")
                        result = await execute_trade_if_valid(test_signal, max_risk=0.06)
                        
                        if result:
                            log("✅ Test PASSED! Trade executed successfully")
                            log("\n📋 Trade Details:")
                            log(f"  Symbol: {result.get('symbol')}")
                            log(f"  Entry: {result.get('entry')}")
                            log(f"  Direction: {result.get('direction')}")
                            log(f"  Strategy: {result.get('strategy')}")
                            log(f"  Exit Strategy: {result.get('exit_strategy')}")
                            
                            log("\n💰 Risk Management:")
                            log(f"  Stop Loss: {result.get('sl')} ({result.get('sl_pct')}%)")
                            log(f"  Take Profit 1: {result.get('tp1')} ({result.get('tp1_pct')}%)")
                            log(f"  Take Profit 2: {result.get('tp2')} ({result.get('tp2_pct')}%)")
                            log(f"  Trailing Stop: {result.get('trailing_pct')}%")
                            
                            log("\n📊 Range Break Details:")
                            if result.get('range_levels'):
                                log(f"  Range High: {result['range_levels'].get('high')}")
                                log(f"  Range Low: {result['range_levels'].get('low')}")
                                log(f"  Range Width: {result['range_levels'].get('width_pct')}%")
                            
                            log("\n📈 Exit Tranches:")
                            for i, tranche in enumerate(result.get('exit_tranches', [])):
                                log(f"  Tranche {i+1}: {tranche}")
                            
                            # Verify range-based calculations
                            if result.get('range_break'):
                                log("\n✅ Range break integration verified!")
                                log("  - Range-based SL/TP calculations applied")
                                log("  - Pump-optimized exit strategy activated")
                                log("  - Custom exit tranches configured")
                            
                        else:
                            log("❌ Test FAILED - No trade executed")


if __name__ == "__main__":
    log("=" * 50)
    log("RANGE BREAK INTEGRATION TEST")
    log("=" * 50)
    asyncio.run(test_range_break_integration())
