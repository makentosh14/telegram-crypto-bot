# test_btc_analyzer.py - Quick debug test
import asyncio
from trend_filters import btc_analyzer

async def test_analyzer():
    print("🔍 Testing BTC Analyzer...")
    
    # Check if analyzer has the new methods
    methods_to_check = [
        '_analyze_moving_averages',
        '_analyze_price_structure', 
        '_analyze_momentum',
        '_analyze_volume_trend'
    ]
    
    print("\n📋 Checking for required methods:")
    for method in methods_to_check:
        if hasattr(btc_analyzer, method):
            print(f"✅ {method} - FOUND")
        else:
            print(f"❌ {method} - MISSING")
    
    print(f"\n📊 Current analyzer state:")
    print(f"   Last trend: {btc_analyzer.last_trend}")
    print(f"   Strength: {btc_analyzer.trend_strength}")
    print(f"   Confidence: {btc_analyzer.confidence}")
    
    print(f"\n🧪 Running actual analysis...")
    try:
        result = await btc_analyzer.analyze_btc_trend()
        print(f"   Result: {result}")
        
        if result['confidence'] > 0:
            print("✅ New analyzer is working!")
        else:
            print("❌ Still getting 0% confidence - analyzer not working")
            
    except Exception as e:
        print(f"❌ Error running analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_analyzer())
