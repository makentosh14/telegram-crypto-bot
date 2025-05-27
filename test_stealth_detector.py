# test_stealth_detector_enhanced.py
import asyncio
import numpy as np
from stealth_detector import (
    detect_volume_divergence,
    detect_slow_breakout,
    detect_stealth_accumulation_advanced,
    get_stealth_statistics,
    StealthAccumulationDetector,
    clear_stealth_cache
)

def create_stealth_accumulation_candles():
    """Create candles that exhibit stealth accumulation pattern"""
    candles = []
    base_price = 100.0
    base_volume = 1000
    
    # Phase 1: Price decline with increasing volume (accumulation)
    for i in range(10):
        price = base_price - (i * 0.1)  # Slight price decline
        volume = base_volume * (1.2 + i * 0.1)  # Increasing volume
        
        candles.append({
            'open': price + 0.05,
            'high': price + 0.1,
            'low': price - 0.05,
            'close': price,
            'volume': volume,
            'timestamp': f'2024-01-01 00:{i:02d}:00'
        })
    
    # Phase 2: Sideways movement with high volume
    for i in range(10, 15):
        price = base_price - 1.0 + np.random.uniform(-0.05, 0.05)
        volume = base_volume * 2.0  # Sustained high volume
        
        candles.append({
            'open': price,
            'high': price + 0.02,
            'low': price - 0.02,
            'close': price + np.random.uniform(-0.01, 0.01),
            'volume': volume,
            'timestamp': f'2024-01-01 00:{i:02d}:00'
        })
    
    return candles

def create_slow_breakout_candles():
    """Create candles showing slow breakout pattern"""
    candles = []
    base_price = 100.0
    
    # Consolidation phase
    for i in range(10):
        price = base_price + np.random.uniform(-0.1, 0.1)
        candles.append({
            'open': price,
            'high': price + 0.05,
            'low': price - 0.05,
            'close': price + 0.02,
            'volume': 1000 + np.random.randint(-100, 100),
            'timestamp': f'2024-01-01 00:{i:02d}:00'
        })
    
    # Breakout phase - consistent closes above average
    avg_price = base_price
    for i in range(10, 16):
        price = avg_price + 0.05 * (i - 9)  # Gradual increase
        candles.append({
            'open': price - 0.02,
            'high': price + 0.03,
            'low': price - 0.01,
            'close': price + 0.02,  # Consistently closing higher
            'volume': 1200 + i * 50,
            'timestamp': f'2024-01-01 00:{i:02d}:00'
        })
    
    return candles

def create_volume_divergence_candles():
    """Create candles with volume divergence pattern"""
    candles = []
    base_price = 100.0
    
    for i in range(20):
        # Price stays flat or declines slightly
        price = base_price - (i * 0.01)
        # Volume increases significantly
        volume = 1000 * (1 + i * 0.15)  # 15% increase per candle
        
        candles.append({
            'open': price + 0.02,
            'high': price + 0.03,
            'low': price - 0.01,
            'close': price,
            'volume': volume,
            'timestamp': f'2024-01-01 00:{i:02d}:00'
        })
    
    return candles

async def test_enhanced_detection():
    print("\n🔬 Enhanced Stealth Detection Tests")
    print("=" * 70)
    
    # Test 1: Volume Divergence
    print("\n1. Testing Volume Divergence Pattern:")
    div_candles = create_volume_divergence_candles()
    
    # Basic detection
    has_divergence = detect_volume_divergence(div_candles, min_growth_ratio=1.5)
    print(f"   Basic Detection: {has_divergence}")
    
    # Advanced detection
    detector = StealthAccumulationDetector("TESTUSDT")
    for candle in div_candles:
        result = detector.update(candle)
    
    advanced_result = detect_stealth_accumulation_advanced(div_candles, "TESTUSDT")
    print(f"   Advanced Detection: {advanced_result['detected']}")
    print(f"   Patterns Found: {advanced_result['patterns']}")
    print(f"   Strength: {advanced_result['strength']}")
    
    # Test 2: Slow Breakout
    print("\n2. Testing Slow Breakout Pattern:")
    breakout_candles = create_slow_breakout_candles()
    
    has_breakout = detect_slow_breakout(breakout_candles)
    print(f"   Basic Detection: {has_breakout}")
    
    # Test 3: Stealth Accumulation
    print("\n3. Testing Stealth Accumulation Pattern:")
    accum_candles = create_stealth_accumulation_candles()
    
    # Clear cache and detector
    clear_stealth_cache()
    detector2 = StealthAccumulationDetector("ACCUMUSDT")
    
    # Feed candles one by one
    for i, candle in enumerate(accum_candles):
        result = detector2.update(candle)
        if result['detected']:
            print(f"   Stealth pattern detected at candle {i}!")
            print(f"   Type: {result['type']}")
            print(f"   Strength: {result['strength']}")
    
    # Full analysis
    full_result = detect_stealth_accumulation_advanced(accum_candles, "ACCUMUSDT")
    print(f"\n   Full Analysis:")
    print(f"   Detected: {full_result['detected']}")
    print(f"   Patterns: {full_result['patterns']}")
    print(f"   Recommendation: {full_result['recommendation']}")
    
    # Test 4: Real-world scenario
    print("\n4. Testing Combined Patterns:")
    
    # Create mixed pattern candles
    mixed_candles = []
    # Start with accumulation
    mixed_candles.extend(create_stealth_accumulation_candles()[:10])
    # Add breakout
    mixed_candles.extend(create_slow_breakout_candles()[10:])
    
    mixed_result = detect_stealth_accumulation_advanced(mixed_candles, "MIXEDUSDT")
    print(f"   Detected: {mixed_result['detected']}")
    print(f"   All Patterns: {mixed_result['patterns']}")
    print(f"   Strength: {mixed_result['strength']}")
    print(f"   Recommendation: {mixed_result['recommendation']}")
    
    # Get statistics
    stats = get_stealth_statistics("MIXEDUSDT")
    print(f"\n   Statistics: {stats}")

async def test_thresholds():
    """Test with different threshold values"""
    print("\n⚙️ Testing Different Thresholds")
    print("=" * 70)
    
    candles = create_volume_divergence_candles()
    
    thresholds = [1.2, 1.5, 1.8, 2.0, 2.5]
    for threshold in thresholds:
        result = detect_volume_divergence(candles, min_growth_ratio=threshold)
        print(f"Threshold {threshold}: Detection = {result}")

async def visualize_patterns():
    """Show what the patterns look like"""
    print("\n📊 Pattern Visualization")
    print("=" * 70)
    
    # Volume Divergence
    print("\n1. Volume Divergence Pattern:")
    print("   Price: ↘️ (declining)")
    print("   Volume: ↗️ (increasing)")
    print("   Signal: Potential accumulation")
    
    # Slow Breakout
    print("\n2. Slow Breakout Pattern:")
    print("   Price: →↗️ (sideways then gradual up)")
    print("   Volume: ↗️ (increasing)")
    print("   Signal: Early pump detection")
    
    # Stealth Accumulation
    print("\n3. Stealth Accumulation:")
    print("   Phase 1: Price ↘️ Volume ↗️")
    print("   Phase 2: Price → Volume ↗️↗️")
    print("   Signal: Smart money accumulating")

async def main():
    print("🚀 Enhanced Stealth Detector Test Suite")
    print("=" * 70)
    
    # Run all tests
    await test_enhanced_detection()
    await test_thresholds()
    await visualize_patterns()
    
    print("\n✅ Enhanced tests completed!")
    print("\n💡 Key Insights:")
    print("1. Volume divergence needs price decline + volume increase")
    print("2. Slow breakout needs consistent closes above average")
    print("3. Stealth accumulation combines multiple patterns")
    print("4. Adjust thresholds based on your market (crypto is volatile)")
    
    print("\n🔧 Integration Example:")
    print("""
    # In your score.py, add this to score_symbol():
    
    # Stealth Detection Bonus
    stealth_result = detect_stealth_accumulation_advanced(candles, symbol)
    if stealth_result['detected']:
        if stealth_result['recommendation'] == 'accumulation_zone':
            score += 1.5 * stealth_result['strength']
            indicator_scores[f"{tf_label}_stealth_accumulation"] = 1.5
            used_indicators.add("stealth_accumulation")
            log(f"🕵️ Stealth accumulation detected: {stealth_result['patterns']}")
    """)

if __name__ == "__main__":
    asyncio.run(main())

