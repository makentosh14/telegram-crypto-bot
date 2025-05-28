#!/usr/bin/env python3
"""
Comprehensive test script for range break integration
Tests the full flow without requiring actual API calls or balance
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import log
from trade_executor import execute_trade_if_valid
from range_break_detector import range_break_detector
import json

# Mock the API modules to avoid real calls
import bybit_api
import pre_trade_validator
import risk_manager

# Store original functions
original_signed_request = bybit_api.signed_request
original_get_futures_balance = bybit_api.get_futures_available_balance
original_place_stop_loss_with_retry = bybit_api.place_stop_loss_with_retry
original_final_validation = pre_trade_validator.pre_trade_validator.final_validation

# Mock implementations
async def mock_signed_request(method, endpoint, params):
    """Mock API responses for testing"""
    log(f"🔧 MOCK API: {method} {endpoint}")
    log(f"📦 Params: {json.dumps(params, indent=2)}")
    
    if endpoint == "/v5/position/set-leverage":
        return {"retCode": 0, "retMsg": "OK"}
    
    elif endpoint == "/v5/order/cancel-all":
        return {"retCode": 0, "retMsg": "OK", "result": {"list": [], "success": "1"}}
    
    elif endpoint == "/v5/order/create" and params.get("orderType") == "Market":
        # Simulate successful market order
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": f"test-market-{params.get('qty')}",
                "avgPrice": "107416.60",  # Return the expected price
                "price": "107416.60"
            }
        }
    
    elif endpoint == "/v5/order/create" and params.get("orderType") == "Stop":
        # Simulate successful stop loss order
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": f"test-sl-{params.get('stopPrice')}"
            }
        }
    
    elif endpoint == "/v5/order/create" and params.get("orderType") == "Limit":
        # Simulate successful take profit order
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": f"test-tp-{params.get('price')}"
            }
        }
    
    elif endpoint == "/v5/market/tickers":
        # Mock ticker response
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "symbol": params.get("symbol", "BTCUSDT"),
                    "lastPrice": "107416.60",
                    "markPrice": "107416.60"
                }]
            }
        }
    
    else:
        return {"retCode": 0, "retMsg": "OK", "result": {}}

async def mock_get_futures_balance():
    """Mock balance for testing"""
    balance = 10000.0  # $10,000 test balance
    log(f"💰 MOCK Balance: ${balance}")
    return balance

async def mock_place_stop_loss_with_retry(symbol, direction, qty, sl_price, market_type="linear"):
    """Mock stop loss placement"""
    log(f"🛡️ MOCK SL: {symbol} {direction} @ {sl_price}")
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "orderId": f"test-sl-{sl_price}"
        }
    }

async def mock_final_validation(*args, **kwargs):
    """Mock validation - always pass for testing"""
    return True, "Test mode - validation bypassed"

async def test_range_break_integration():
    """Comprehensive test of range break integration"""
    
    log("==================================================")
    log("RANGE BREAK INTEGRATION TEST")
    log("==================================================")
    
    # Apply mocks
    bybit_api.signed_request = mock_signed_request
    bybit_api.get_futures_available_balance = mock_get_futures_balance
    bybit_api.place_stop_loss_with_retry = mock_place_stop_loss_with_retry
    pre_trade_validator.pre_trade_validator.final_validation = mock_final_validation
    
    # Mock risk manager functions
    risk_manager.load_risk_state = lambda: log("✅ MOCK: Risk state loaded")
    risk_manager.reset_daily_risk = lambda: log("✅ MOCK: Daily risk reset")
    risk_manager.check_trading_allowed = lambda: True
    risk_manager.register_trade_risk = lambda *args: log("✅ MOCK: Trade risk registered")
    
    try:
        # Test 1: Pre-breakout pump signal
        log("\n🧪 TEST 1: Pre-breakout Pump Signal")
        log("=" * 50)
        
        pump_signal = {
            "symbol": "BTCUSDT",
            "price": 107416.60,
            "trade_type": "Scalp",
            "direction": "Long",
            "score": 8.5,
            "confidence": 85,
            "candles": {
                "1": [{"close": "107416.60", "open": "107316.60", "high": "107516.60", 
                       "low": "107216.60", "volume": "1000"}] * 30,
                "3": [{"close": "107416.60", "open": "107316.60", "high": "107516.60", 
                       "low": "107216.60", "volume": "3000"}] * 30,
                "5": [{"close": "107416.60", "open": "107316.60", "high": "107516.60", 
                       "low": "107216.60", "volume": "5000"}] * 30,
            },
            "indicator_scores": {"range_break": 0.8, "stealth_accumulation": 0.7},
            "used_indicators": ["range_break", "stealth_accumulation"],
            "tf_scores": {"5": 8.5},
            "regime": "volatile",
            "range_break_details": {
                "range_high": 108500.0,
                "range_low": 106000.0,
                "range_width_pct": 2.36,
                "pre_breakout": True,
                "buildup_patterns": ["price_compression", "volume_tightening", "bb_squeeze"],
                "compression_data": {"compression_ratio": 0.6, "consistency": 0.8},
                "stealth_score": 0.7,
                "stealth_direction": "Long"
            },
            "range_break_confidence": 0.85,
            "exit_strategy": "pump_optimized",
            "trailing_multiplier": 1.5,
            "tp1_multiplier": 1.3,
            "exit_tranches": [0.25, 0.35, 0.40],
            "market_type": "linear"
        }
        
        result = await execute_trade_if_valid(pump_signal, max_risk=0.06)
        
        if result:
            log("\n✅ TEST 1 PASSED - Pre-breakout pump trade executed successfully")
            log_trade_details(result)
        else:
            log("\n❌ TEST 1 FAILED - No trade executed")
        
        # Test 2: Regular breakout signal
        log("\n🧪 TEST 2: Regular Breakout Signal")
        log("=" * 50)
        
        breakout_signal = {
            "symbol": "ETHUSDT",
            "price": 3800.0,
            "trade_type": "Scalp",
            "direction": "Short",
            "score": 7.5,
            "confidence": 75,
            "candles": {
                "1": [{"close": "3800", "open": "3810", "high": "3820", 
                       "low": "3790", "volume": "500"}] * 30,
                "3": [{"close": "3800", "open": "3810", "high": "3820", 
                       "low": "3790", "volume": "1500"}] * 30,
                "5": [{"close": "3800", "open": "3810", "high": "3820", 
                       "low": "3790", "volume": "2500"}] * 30,
            },
            "indicator_scores": {"range_break": 0.7},
            "used_indicators": ["range_break"],
            "tf_scores": {"5": 7.5},
            "regime": "volatile",
            "range_break_details": {
                "range_high": 3850.0,
                "range_low": 3750.0,
                "range_width_pct": 2.67,
                "pre_breakout": False,
                "volume_analysis": {
                    "tightening": {"detected": True, "score": 0.6},
                    "profile": {"score": 0.7},
                    "trend": {"score": 0.5},
                    "buildup": {"detected": True, "score": 0.8}
                }
            },
            "range_break_confidence": 0.7,
            "market_type": "linear"
        }
        
        result = await execute_trade_if_valid(breakout_signal, max_risk=0.06)
        
        if result:
            log("\n✅ TEST 2 PASSED - Regular breakout trade executed successfully")
            log_trade_details(result)
        else:
            log("\n❌ TEST 2 FAILED - No trade executed")
        
        # Test 3: Test range break detector directly
        log("\n🧪 TEST 3: Range Break Detector Direct Test")
        log("=" * 50)
        
        # Create test candles for range detection
        test_candles = []
        base_price = 50000.0
        for i in range(60):
            # Create ranging price action
            price_offset = (i % 10 - 5) * 50  # Oscillate within range
            test_candles.append({
                "high": str(base_price + price_offset + 25),
                "low": str(base_price + price_offset - 25),
                "open": str(base_price + price_offset - 10),
                "close": str(base_price + price_offset + 10),
                "volume": str(1000 + i * 10),
                "timestamp": f"2025-05-28 {i:02d}:00:00"
            })
        
        # Add breakout candle
        test_candles.append({
            "high": str(base_price + 300),
            "low": str(base_price + 200),
            "open": str(base_price + 210),
            "close": str(base_price + 290),
            "volume": str(5000),  # High volume
            "timestamp": "2025-05-28 60:00:00"
        })
        
        # Test detection
        trend_context = {"regime": "volatile", "btc_trend": "ranging"}
        breakout, direction, confidence, details = range_break_detector.detect_range_breakout(
            "TESTUSDT", test_candles, "5", trend_context
        )
        
        log(f"\n📊 Range Detection Results:")
        log(f"  Breakout Detected: {breakout}")
        log(f"  Direction: {direction}")
        log(f"  Confidence: {confidence:.2f}")
        log(f"  Details: {json.dumps(details, indent=2)}")
        
        if breakout:
            log("\n✅ TEST 3 PASSED - Range breakout detected correctly")
        else:
            log("\n❌ TEST 3 FAILED - Range breakout not detected")
        
    except Exception as e:
        log(f"\n❌ Test error: {e}")
        import traceback
        log(traceback.format_exc())
    
    finally:
        # Restore original functions
        bybit_api.signed_request = original_signed_request
        bybit_api.get_futures_available_balance = original_get_futures_balance
        bybit_api.place_stop_loss_with_retry = original_place_stop_loss_with_retry
        pre_trade_validator.pre_trade_validator.final_validation = original_final_validation
    
    log("\n==================================================")
    log("TEST COMPLETED")
    log("==================================================")

def log_trade_details(result):
    """Log trade execution details"""
    log(f"\n📊 Trade Execution Details:")
    log(f"  Symbol: {result.get('symbol')}")
    log(f"  Direction: {result.get('direction')}")
    log(f"  Entry Price: ${result.get('entry'):,.2f}")
    log(f"  Stop Loss: ${result.get('sl'):,.2f} ({result.get('sl_pct'):.2f}%)")
    log(f"  Take Profit 1: ${result.get('tp1'):,.2f} ({result.get('tp1_pct'):.2f}%)")
    
    if result.get('tp2'):
        log(f"  Take Profit 2: ${result.get('tp2'):,.2f} ({result.get('tp2_pct'):.2f}%)")
    
    log(f"  Position Size: {result.get('qty')}")
    log(f"  Exit Strategy: {result.get('exit_strategy', 'normal')}")
    log(f"  Exit Tranches: {result.get('exit_tranches')}")
    
    if result.get('range_levels'):
        log(f"\n  📊 Range Levels:")
        log(f"    High: ${result['range_levels'].get('high'):,.2f}")
        log(f"    Low: ${result['range_levels'].get('low'):,.2f}")
        log(f"    Width: {result['range_levels'].get('width_pct'):.2f}%")
    
    log(f"\n  Strategy: {result.get('strategy')}")
    log(f"  Trailing %: {result.get('trailing_pct'):.2f}%")
    log(f"  Leverage: {result.get('leverage')}x")

if __name__ == "__main__":
    asyncio.run(test_range_break_integration())
