# run_backfill.py - Simple script to run pattern backfill (leak-proof mode)

import asyncio
from pattern_backfill import PatternBackfillSystem

async def main():
    """Run a quick 7-day backfill on major pairs"""

    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT'
    ]

    print("🚀 Starting Pattern Backfill System")
    print(f"📊 Testing {len(symbols)} symbols over 7 days")
    print()

    backfill = PatternBackfillSystem()

    try:
        await backfill.run_full_backfill(symbols, days=7)
        print()
        print("✅ Backfill completed successfully!")
        print("📄 Check 'pattern_backfill_report.json' for detailed results")
        print("📚 Discoveries saved to 'pattern_discovered_backfill.json' (read-only).")
        print("   Set BACKTEST_WRITE_MEMORY=1 to also append to 'pattern_memory.json'.")
    except Exception as e:
        print(f"❌ Backfill failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
