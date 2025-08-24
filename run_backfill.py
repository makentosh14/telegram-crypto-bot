# run_backfill.py - Simple script to run pattern backfill

import asyncio
from pattern_backfill import PatternBackfillSystem

async def main():
    """Run a quick 7-day backfill on major pairs"""
    
    # Define symbols to test
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT'
    ]
    
    print("🚀 Starting Pattern Backfill System")
    print(f"📊 Testing {len(symbols)} symbols over 7 days")
    print("⏰ This will take 5-10 minutes...")
    print()
    
    # Create and run backfill system
    backfill = PatternBackfillSystem()
    
    try:
        await backfill.run_full_backfill(symbols, days=7)
        print()
        print("✅ Backfill completed successfully!")
        print("📄 Check 'pattern_backfill_report.json' for detailed results")
        print("📚 Pattern database updated in 'pattern_memory.json'")
        
    except Exception as e:
        print(f"❌ Backfill failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
