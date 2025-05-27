import sys
import os
import asyncio

# Adjust path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stealth_detector import detect_volume_divergence, detect_slow_breakout

# ✅ Mock candles data for 5m timeframe
def generate_mock_candles():
    return [
        {"open": "100.0", "high": "101.0", "low": "99.5", "close": "100.5", "volume": "200"},
        {"open": "100.5", "high": "101.2", "low": "100.0", "close": "101.0", "volume": "180"},
        {"open": "101.0", "high": "101.5", "low": "100.8", "close": "101.3", "volume": "160"},
        {"open": "101.3", "high": "102.0", "low": "101.0", "close": "101.9", "volume": "150"},
        {"open": "101.9", "high": "102.5", "low": "101.5", "close": "102.2", "volume": "130"},
        {"open": "102.2", "high": "103.0", "low": "102.0", "close": "102.8", "volume": "120"},
        {"open": "102.8", "high": "103.5", "low": "102.5", "close": "103.2", "volume": "110"},
        {"open": "103.2", "high": "104.0", "low": "102.8", "close": "103.5", "volume": "100"},
        {"open": "103.5", "high": "104.2", "low": "103.0", "close": "104.0", "volume": "90"},
        {"open": "104.0", "high": "105.0", "low": "103.5", "close": "104.8", "volume": "80"},
    ]

async def test_stealth_logic():
    print("🔍 Running stealth detection integration test...")

    mock_candles = generate_mock_candles()

    divergence_result = detect_volume_divergence(mock_candles)
    breakout_result = detect_slow_breakout(mock_candles)

    print("📈 Volume Divergence Detected:", divergence_result)
    print("🚀 Slow Breakout Detected:", breakout_result)

if __name__ == "__main__":
    asyncio.run(test_stealth_logic())



