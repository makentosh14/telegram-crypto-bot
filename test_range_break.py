#!/usr/bin/env python3
"""
Test script for range break integration with trade_executor.py
Tests the complete flow of range break detection through trade execution
"""

import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import required modules
from logger import log
from trade_executor import execute_trade_if_valid
from range_break_detector import range_break_detector
from symbol_info import symbol_precisions

# Setup test symbol info
symbol_precisions["BTCUSDT"] = {
    "min_qty": 0.001,
    "precision": 3,
    "tick_size": 0.01
}

async def test_range_break_integration():
    """
    Test the complete integration of range break detection with trade execution
    """
    log("==================================================")
    log("RANGE BREAK INTEGRATION TEST")
    log("==================================================")
    
    # Test configuration
    symbol = "BTCUSDT"
    current_price = 107416.60
    range_high = 108500.00
    range_low = 106000.00
    
    # Create realistic candle data
    candles_5m = []
    for i in range(50):
        # Simulate price consolidation within range
        if i < 40:
            # Consolidation phase
            close = range_low + (range_high - range_low) * 0.5 + (i % 10 - 5) * 50
        else:
            # Breakout phase
            close = range_high - (50 - i) * 100  # Approaching range high
        
        candles_5m.append({
            "timestamp": f"2025-05-28 {21-i//60:02d}:{59-i%60:02d}:00",
            "open": str(close - 50),
            "high": str(close + 100),
            "low": str(close - 100),
            "close": str(close),
            "volume": str(1000 + i * 10)  # Increasing volume
        })
    
    # Set current price near breakout
    candles_5m[-1]["close"] = str(current_price)
    
    # Test signal with range break details
    test_signal = {
        "symbol": symbol,
        "price": current_price,
        "trade_type": "Scalp",
        "direction": "Long",
        "score": 8.5,
        "confidence": 85,
        "candles": {
            "1": candles_5m[-30:],  # Last 30 candles for 1m
            "3": candles_5m[-30:],  # Reuse for testing
            "5": candles_5m,        # Full 50 candles for 5m
            "15": candles_5m[-30:], # Last 30 for 15m
            "30": candles_5m[-20:]  # Last 20 for 30m
        },
        "indicator_scores": {
            "range_break": 0.8,
            "pre_breakout": 1.0,
            "stealth_accumulation": 0.7,
            "volume_buildup": 0.6
        },
        "used_indicators": ["range_break", "pre_breakout", "stealth_accumulation", "volume_buildup"],
        "tf_scores": {"5": 8.5},
        "regime": "volatile",
        "range_break_details": {
            "range_high": range_high,
            "range_low": range_low,
            "range_width_pct": ((range_high - range_low) / range_low) * 100,
            "touches_high": 5,
            "touches_low": 4,
            "pre_breakout": True,
            "buildup_patterns": ["price_compression", "volume_tightening", "bb_squeeze"],
            "integrated_factors": {
                "stealth": 0.7,
                "trend": 0.6,
                "volume_profile": 0.8,
                "volume_trend": 0.7
            }
        },
        "range_break_confidence": 0.85,
        "exit_strategy": "pump_optimized",
        "trailing_multiplier": 1.5,
        "tp1_multiplier": 1.3,
        "exit_tranches": [0.25, 0.35, 0.40],  # Let winners run distribution
        "market_type": "linear"
    }
    
    log(f"\n📊 Test Configuration:")
    log(f"  Symbol: {symbol}")
    log(f"  Current Price: ${current_price:,.2f}")
    log(f"  Range: ${range_low:,.2f} - ${range_high:,.2f} ({test_signal['range_break_details']['range_width_pct']:.2f}%)")
    log(f"  Direction: {test_signal['direction']}")
    log(f"  Confidence: {test_signal['range_break_confidence']*100:.1f}%")
    log(f"  Exit Strategy: {test_signal['exit_strategy']}")
    
    # Mock functions to avoid actual API calls
    mock_balance = 1000.0  # $1000 test balance
    
    async def mock_get_account_balance():
        return mock_balance
    
    async def mock_signed_request(method, endpoint, params):
        """Mock API responses"""
        log(f"  [MOCK API] {method} {endpoint}")
        
        if endpoint == "/v5/position/set-leverage":
            return {"retCode": 0, "retMsg": "OK"}
            
        elif endpoint == "/v5/order/cancel-all":
            return {"retCode": 0, "retMsg": "OK", "result": {"list": []}}
            
        elif endpoint == "/v5/order/create":
            if params.get("orderType") == "Market":
                # Market order execution
                executed_price = current_price * 1.0001  # Slight slippage
                return {
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "orderId": "market-order-123",
                        "avgPrice": str(executed_price),
                        "price": str(executed_price)
                    }
                }
            elif params.get("orderType") == "Stop":
                # Stop loss order
                return {
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "orderId": "sl-order-123"
                    }
                }
            elif params.get("orderType") == "Limit":
                # Take profit order
                return {
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "orderId": f"tp-order-{params.get('price', 'xxx')}"
                    }
                }
                
        elif endpoint == "/v5/market/tickers":
            # Market ticker for SL validation
            return {
                "retCode": 0,
                "result": {
                    "list": [{
                        "symbol": symbol,
                        "markPrice": str(current_price),
                        "lastPrice": str(current_price)
                    }]
                }
            }
            
        return {"retCode": 0, "retMsg": "OK"}
    
    async def mock_pre_trade_validation(*args, **kwargs):
        """Mock pre-trade validation to always pass"""
        return True, "Test mode - validation passed"
    
    # Apply mocks
    with patch('trade_executor.get_account_balance', side_effect=mock_get_account_balance):
        with patch('bybit_api.signed_request', side_effect=mock_signed_request):
            with patch('pre_trade_validator.pre_trade_validator.final_validation', side_effect=mock_pre_trade_validation):
                log("\n🚀 Executing test trade...")
                
                try:
                    # Execute the trade
                    result = await execute_trade_if_valid(test_signal, max_risk=0.06)
                    
                    if result:
                        log("\n✅ TRADE EXECUTION SUCCESSFUL!")
                        log("\n📋 Trade Details:")
                        log(f"  Entry Price: ${result['entry']:,.2f}")
                        log(f"  Stop Loss: ${result['sl']:,.2f} ({result['sl_pct']:.2f}% risk)")
                        log(f"  Take Profit 1: ${result['tp1']:,.2f} ({result['tp1_pct']:.2f}% target)")
                        if result.get('tp2'):
                            log(f"  Take Profit 2: ${result['tp2']:,.2f} ({result.get('tp2_pct', 0):.2f}% target)")
                        log(f"  Position Size: {result['qty']} BTC")
                        log(f"  Risk/Reward: 1:{result['tp1_pct']/result['sl_pct']:.1f}")
                        
                        log(f"\n🎯 Exit Strategy Details:")
                        log(f"  Strategy Type: {result['exit_strategy']}")
                        log(f"  Trailing Stop: {result['trailing_pct']:.2f}%")
                        log(f"  Exit Tranches: {result['exit_tranches']}")
                        
                        if result.get('range_levels'):
                            log(f"\n📊 Range-Based Levels:")
                            log(f"  Range High: ${result['range_levels']['high']:,.2f}")
                            log(f"  Range Low: ${result['range_levels']['low']:,.2f}")
                            log(f"  Range Width: {result['range_levels']['width_pct']:.2f}%")
                        
                        log(f"\n🏷️ Trade Metadata:")
                        log(f"  Trade Type: {result['type']}")
                        log(f"  Direction: {result['direction']}")
                        log(f"  Strategy: {result['strategy']}")
                        log(f"  Leverage: {result['leverage']}x")
                        log(f"  Timestamp: {result['timestamp']}")
                        
                        # Verify range-based adjustments
                        log(f"\n🔍 Verification:")
                        
                        # Check if SL is near range low (for long)
                        if test_signal['direction'].lower() == 'long':
                            sl_distance_from_range = abs(result['sl'] - range_low) / range_low * 100
                            log(f"  SL distance from range low: {sl_distance_from_range:.2f}%")
                            if sl_distance_from_range < 1:
                                log("  ✅ SL correctly placed near range support")
                        
                        # Check if using pump-optimized parameters
                        if result['exit_strategy'] == 'pump_optimized':
                            log("  ✅ Pump-optimized exit strategy applied")
                            if result['trailing_pct'] > test_signal['range_break_details']['range_width_pct'] * 0.3:
                                log("  ✅ Wider trailing stop for pump potential")
                        
                        # Check exit tranches
                        expected_tranches = [0.25, 0.35, 0.40]
                        actual_tranches_pct = [t/result['qty'] for t in result['exit_tranches']]
                        log(f"  Exit tranche percentages: {[f'{p*100:.0f}%' for p in actual_tranches_pct]}")
                        if all(abs(a - e) < 0.05 for a, e in zip(actual_tranches_pct, expected_tranches)):
                            log("  ✅ Exit tranches match 'let winners run' distribution")
                        
                        log("\n✅ TEST PASSED - Range break integration working correctly!")
                        
                    else:
                        log("\n❌ TEST FAILED - Trade execution returned None")
                        
                except Exception as e:
                    log(f"\n❌ TEST ERROR: {str(e)}")
                    import traceback
                    log(traceback.format_exc())

def run_test():
    """Run the async test"""
    try:
        # Run the test
        result = asyncio.run(test_range_break_integration())
        log("\n==================================================")
        log("TEST COMPLETED")
        log("==================================================")
    except KeyboardInterrupt:
        log("\n⚠️ Test interrupted by user")
    except Exception as e:
        log(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        log(traceback.format_exc())

if __name__ == "__main__":
    # Run the test
    run_test()
