import asyncio
from logger import log
from stealth_detector import (
    detect_volume_divergence,
    detect_slow_breakout,
    detect_stealth_accumulation_advanced,
    get_stealth_statistics
)
from candle_data import live_candles

async def test_stealth_detector():
    test_symbol = "BTCUSDT"
    if test_symbol in live_candles and '5' in live_candles[test_symbol]:
        candles = list(live_candles[test_symbol]['5'])
        
        vol_div = detect_volume_divergence(candles)
        slow_break = detect_slow_breakout(candles)
        advanced = detect_stealth_accumulation_advanced(candles, test_symbol)
        
        log(f"🧪 Stealth Detector Test for {test_symbol}:")
        log(f"  Volume Divergence: {vol_div}")
        log(f"  Slow Breakout: {slow_break}")
        log(f"  Advanced Detection: {advanced}")
        
        stats = get_stealth_statistics(test_symbol)
        log(f"  Statistics: {stats}")
    else:
        log(f"❌ No candle data found for {test_symbol} [5m]", level="ERROR")

async def main():
    await asyncio.sleep(30)  # Wait for candles to load
    await test_stealth_detector()

if __name__ == "__main__":
    asyncio.run(main())


