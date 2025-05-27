# Add this temporary test function to verify integration:
async def test_stealth_detector():
    # Get candles for a symbol
    test_symbol = "BTCUSDT"
    if test_symbol in live_candles and '5' in live_candles[test_symbol]:
        candles = list(live_candles[test_symbol]['5'])
        
        # Test basic functions
        vol_div = detect_volume_divergence(candles)
        slow_break = detect_slow_breakout(candles)
        
        # Test advanced detection
        advanced = detect_stealth_accumulation_advanced(candles, test_symbol)
        
        log(f"🧪 Stealth Detector Test for {test_symbol}:")
        log(f"  Volume Divergence: {vol_div}")
        log(f"  Slow Breakout: {slow_break}")
        log(f"  Advanced Detection: {advanced}")
        
        # Get statistics
        stats = get_stealth_statistics(test_symbol)
        log(f"  Statistics: {stats}")

# Run once after bot starts:
await asyncio.sleep(30)  # Wait for candles to load
await test_stealth_detector()
