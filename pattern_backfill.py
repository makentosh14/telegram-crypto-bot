# pattern_backfill.py - Historical Pattern Discovery and Testing System

import asyncio
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import time
from logger import log
from bybit_api import signed_request
from pattern_detector import detect_pattern
from score import score_symbol

class PatternBackfillSystem:
    def __init__(self):
        self.discovered_patterns = []
        self.backtest_results = []
        self.symbol_data_cache = {}
        
    async def run_full_backfill(self, symbols, days=30):
        """
        Complete backfill process:
        1. Download historical data
        2. Discover patterns 
        3. Test pattern matching
        4. Generate performance report
        """
        log(f"🚀 Starting {days}-day pattern backfill for {len(symbols)} symbols")
        
        # Step 1: Download historical data
        await self.download_historical_data(symbols, days)
        
        # Step 2: Discover patterns from historical moves
        await self.discover_historical_patterns(symbols, days)
        
        # Step 3: Test pattern matching on different time period
        await self.backtest_pattern_matching(symbols, days)
        
        # Step 4: Generate comprehensive report
        self.generate_backfill_report()
        
        log("✅ Backfill process completed!")

    async def download_historical_data(self, symbols, days):
        """Download historical candle data for all symbols and timeframes"""
        log(f"📥 Downloading {days} days of historical data...")
        
        end_time = int(time.time() * 1000)  # Current time in ms
        start_time = end_time - (days * 24 * 60 * 60 * 1000)  # X days ago
        
        timeframes = ['1', '3', '5', '15', '30', '60', '240']  # All needed timeframes
        
        for symbol in symbols:
            log(f"📊 Downloading {symbol}...")
            self.symbol_data_cache[symbol] = {}
            
            for tf in timeframes:
                try:
                    # Convert timeframe to Bybit format
                    interval_map = {
                        '1': '1', '3': '3', '5': '5', '15': '15',
                        '30': '30', '60': '60', '240': '240'
                    }
                    
                    interval = interval_map[tf]
                    candles = await self.fetch_historical_candles(
                        symbol, interval, start_time, end_time
                    )
                    
                    if candles:
                        self.symbol_data_cache[symbol][tf] = candles
                        log(f"   ✅ {symbol} {tf}m: {len(candles)} candles")
                    else:
                        log(f"   ❌ {symbol} {tf}m: No data")
                        
                    await asyncio.sleep(0.1)  # Rate limiting
                    
                except Exception as e:
                    log(f"❌ Error downloading {symbol} {tf}m: {e}", level="ERROR")
                    continue
            
            await asyncio.sleep(0.5)  # Prevent API overload
        
        log("✅ Historical data download completed")

    async def fetch_historical_candles(self, symbol, interval, start_time, end_time):
        """Fetch historical candles from Bybit API"""
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "start": start_time,
                "end": end_time,
                "limit": 1000  # Max per request
            }
            
            result = await signed_request("GET", "/v5/market/kline", params)
            
            if result.get("retCode") == 0:
                klines = result.get("result", {}).get("list", [])
                
                # Convert to your standard format
                candles = []
                for kline in klines:
                    candles.append({
                        "timestamp": int(kline[0]),
                        "open": float(kline[1]),
                        "high": float(kline[2]),
                        "low": float(kline[3]),
                        "close": float(kline[4]),
                        "volume": float(kline[5])
                    })
                
                # Sort chronologically (oldest first)
                candles.sort(key=lambda x: x["timestamp"])
                return candles
            else:
                log(f"API Error: {result}", level="ERROR")
                return []
                
        except Exception as e:
            log(f"Error fetching candles: {e}", level="ERROR")
            return []

    async def discover_historical_patterns(self, symbols, days):
        """Replay pattern discovery on historical data"""
        log("🔍 Discovering patterns from historical data...")
        
        MIN_MOVE_PCT = 2.0  # Same as your pattern_discovery.py
        
        for symbol in symbols:
            if symbol not in self.symbol_data_cache:
                continue
                
            try:
                # Use 1-minute candles for move detection
                candles_1m = self.symbol_data_cache[symbol].get('1', [])
                if len(candles_1m) < 100:
                    continue
                
                # Sliding window to detect significant moves
                window_size = 20
                for i in range(window_size, len(candles_1m) - 10):  # Leave buffer for future moves
                    
                    window = candles_1m[i-window_size:i]
                    open_price = window[0]['open']
                    high = max(c['high'] for c in window)
                    low = min(c['low'] for c in window)
                    
                    move_up = ((high - open_price) / open_price) * 100
                    move_down = ((open_price - low) / open_price) * 100
                    
                    # Check if significant move occurred
                    if max(move_up, move_down) >= MIN_MOVE_PCT:
                        direction = "pump" if move_up >= move_down else "dump"
                        move_pct = move_up if direction == "pump" else move_down
                        
                        # Build candles_by_tf at this point in time
                        candles_by_tf = self.build_historical_candles_by_tf(
                            symbol, candles_1m[i]['timestamp']
                        )
                        
                        if not candles_by_tf:
                            continue
                        
                        # Detect pattern that was present before the move
                        pattern_candles = candles_by_tf.get('5', [])[-10:]  # Last 10 candles
                        if len(pattern_candles) >= 3:
                            detected_pattern = detect_pattern(pattern_candles)
                            
                            if detected_pattern:
                                # Calculate score and context at that time
                                try:
                                    score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                                        symbol, candles_by_tf
                                    )
                                    
                                    # Record this pattern discovery
                                    pattern_record = {
                                        "timestamp": datetime.fromtimestamp(candles_1m[i]['timestamp'] / 1000).isoformat(),
                                        "symbol": symbol,
                                        "direction": direction,
                                        "move_pct": round(move_pct, 2),
                                        "trade_type": trade_type,
                                        "pattern": detected_pattern,
                                        "score": score,
                                        "tf_scores": tf_scores,
                                        "indicator_scores": indicator_scores,
                                        "used_indicators": used_indicators,
                                        "context": {
                                            "rsi": tf_scores.get('rsi'),
                                            "macd": tf_scores.get('macd'),
                                            "supertrend": tf_scores.get('supertrend')
                                        }
                                    }
                                    
                                    self.discovered_patterns.append(pattern_record)
                                    
                                except Exception as e:
                                    # Skip if scoring fails
                                    continue
                    
                    # Skip ahead to avoid overlapping patterns
                    if max(move_up, move_down) >= MIN_MOVE_PCT:
                        i += 10  # Skip 10 candles ahead
            
            except Exception as e:
                log(f"❌ Pattern discovery error for {symbol}: {e}", level="ERROR")
                continue
        
        log(f"✅ Discovered {len(self.discovered_patterns)} historical patterns")

    def build_historical_candles_by_tf(self, symbol, timestamp):
        """Build candles_by_tf dictionary at a specific historical timestamp"""
        candles_by_tf = {}
        
        for tf in ['1', '3', '5', '15', '30', '60', '240']:
            if tf in self.symbol_data_cache[symbol]:
                # Get candles up to this timestamp
                all_candles = self.symbol_data_cache[symbol][tf]
                historical_candles = [
                    c for c in all_candles 
                    if c['timestamp'] <= timestamp
                ]
                
                if len(historical_candles) >= 30:  # Ensure enough data
                    candles_by_tf[tf] = historical_candles[-100:]  # Last 100 candles
        
        return candles_by_tf if candles_by_tf else None

    async def backtest_pattern_matching(self, symbols, days):
        """Test pattern matching on a different time period"""
        log("🧪 Backtesting pattern matching...")
        
        if not self.discovered_patterns:
            log("❌ No patterns to test - run discovery first")
            return
        
        # Use patterns from first half to test on second half
        mid_point = len(self.discovered_patterns) // 2
        training_patterns = self.discovered_patterns[:mid_point]
        testing_period = self.discovered_patterns[mid_point:]
        
        log(f"📊 Training on {len(training_patterns)} patterns")
        log(f"🧪 Testing on {len(testing_period)} patterns")
        
        # Group training patterns by type
        pattern_performance = defaultdict(list)
        for pattern_record in training_patterns:
            pattern_type = pattern_record.get('pattern')
            if pattern_type:
                pattern_performance[pattern_type].append(pattern_record)
        
        # Test each pattern in testing period
        correct_predictions = 0
        total_predictions = 0
        
        for test_record in testing_period:
            test_pattern = test_record.get('pattern')
            actual_direction = test_record.get('direction')
            actual_move = test_record.get('move_pct')
            
            if test_pattern not in pattern_performance:
                continue  # No historical data for this pattern
            
            # Predict based on historical performance
            historical_data = pattern_performance[test_pattern]
            predicted_direction, predicted_move, confidence = self.make_pattern_prediction(
                historical_data, test_record
            )
            
            if predicted_direction and confidence > 0.5:
                total_predictions += 1
                
                # Check if prediction was correct
                direction_correct = predicted_direction == actual_direction
                move_close = abs(predicted_move - actual_move) < 2.0  # Within 2%
                
                if direction_correct:
                    correct_predictions += 1
                    
                # Record backtest result
                self.backtest_results.append({
                    "symbol": test_record.get('symbol'),
                    "pattern": test_pattern,
                    "predicted_direction": predicted_direction,
                    "actual_direction": actual_direction,
                    "predicted_move": predicted_move,
                    "actual_move": actual_move,
                    "confidence": confidence,
                    "correct": direction_correct,
                    "timestamp": test_record.get('timestamp')
                })
        
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
        log(f"🎯 Backtest Results: {correct_predictions}/{total_predictions} ({accuracy:.1%} accuracy)")

    def make_pattern_prediction(self, historical_data, current_context):
        """Make prediction based on historical pattern performance"""
        if not historical_data:
            return None, 0, 0
        
        # Calculate historical performance
        directions = [r.get('direction') for r in historical_data]
        moves = [r.get('move_pct', 0) for r in historical_data]
        
        # Most common direction
        pump_count = directions.count('pump')
        dump_count = directions.count('dump')
        
        if pump_count > dump_count:
            predicted_direction = 'pump'
            confidence = pump_count / len(directions)
            relevant_moves = [m for r, m in zip(historical_data, moves) if r.get('direction') == 'pump']
        else:
            predicted_direction = 'dump'
            confidence = dump_count / len(directions)
            relevant_moves = [m for r, m in zip(historical_data, moves) if r.get('direction') == 'dump']
        
        predicted_move = sum(relevant_moves) / len(relevant_moves) if relevant_moves else 0
        
        return predicted_direction, predicted_move, confidence

    def generate_backfill_report(self):
        """Generate comprehensive backfill performance report"""
        log("📊 Generating backfill report...")
        
        # Save discovered patterns to file
        self.save_discovered_patterns()
        
        # Generate statistics
        pattern_stats = self.analyze_pattern_performance()
        backtest_stats = self.analyze_backtest_results()
        
        # Print comprehensive report
        print("\n" + "="*60)
        print("🎯 PATTERN BACKFILL REPORT")
        print("="*60)
        
        print(f"\n📚 PATTERN DISCOVERY:")
        print(f"   Total patterns discovered: {len(self.discovered_patterns)}")
        print(f"   Unique pattern types: {len(pattern_stats['pattern_types'])}")
        print(f"   Average move size: {pattern_stats['avg_move']:.2f}%")
        print(f"   Win rate: {pattern_stats['win_rate']:.1%}")
        
        print(f"\n🔥 TOP PERFORMING PATTERNS:")
        for pattern, stats in pattern_stats['top_patterns'][:5]:
            print(f"   {pattern}: {stats['win_rate']:.1%} win rate, {stats['avg_move']:+.1f}% avg move, {stats['count']} samples")
        
        if self.backtest_results:
            print(f"\n🧪 BACKTEST RESULTS:")
            print(f"   Total predictions: {len(self.backtest_results)}")
            print(f"   Accuracy: {backtest_stats['accuracy']:.1%}")
            print(f"   Average confidence: {backtest_stats['avg_confidence']:.1%}")
            
            print(f"\n📈 BEST PATTERN PREDICTIONS:")
            for result in backtest_stats['best_predictions'][:3]:
                print(f"   {result['pattern']} on {result['symbol']}: {result['confidence']:.1%} confidence, {'✅' if result['correct'] else '❌'}")
        
        print("\n" + "="*60)
        
        # Save full report to file
        self.save_backfill_report(pattern_stats, backtest_stats)

    def save_discovered_patterns(self):
        """Save discovered patterns to the pattern database"""
        pattern_file = "pattern_memory.json"
        
        # Load existing patterns
        existing_patterns = []
        if os.path.exists(pattern_file):
            try:
                with open(pattern_file, 'r') as f:
                    existing_patterns = json.load(f)
            except:
                existing_patterns = []
        
        # Add new patterns
        all_patterns = existing_patterns + self.discovered_patterns
        
        # Save combined patterns
        with open(pattern_file, 'w') as f:
            json.dump(all_patterns, f, indent=2)
        
        log(f"✅ Saved {len(self.discovered_patterns)} new patterns to {pattern_file}")

    def analyze_pattern_performance(self):
        """Analyze performance of discovered patterns"""
        if not self.discovered_patterns:
            return {}
        
        pattern_groups = defaultdict(list)
        for record in self.discovered_patterns:
            pattern_type = record.get('pattern')
            if pattern_type:
                pattern_groups[pattern_type].append(record)
        
        # Calculate stats for each pattern
        pattern_stats = {}
        for pattern, records in pattern_groups.items():
            moves = [r.get('move_pct', 0) for r in records]
            profitable = sum(1 for m in moves if m > 1.0)
            
            pattern_stats[pattern] = {
                'count': len(records),
                'win_rate': profitable / len(records),
                'avg_move': sum(moves) / len(moves),
                'max_move': max(moves),
                'min_move': min(moves)
            }
        
        # Overall stats
        all_moves = [r.get('move_pct', 0) for r in self.discovered_patterns]
        overall_profitable = sum(1 for m in all_moves if m > 1.0)
        
        # Top performing patterns
        top_patterns = sorted(
            pattern_stats.items(), 
            key=lambda x: x[1]['win_rate'] * x[1]['count'], 
            reverse=True
        )
        
        return {
            'pattern_types': pattern_stats,
            'avg_move': sum(all_moves) / len(all_moves),
            'win_rate': overall_profitable / len(all_moves),
            'top_patterns': top_patterns
        }

    def analyze_backtest_results(self):
        """Analyze backtest prediction results"""
        if not self.backtest_results:
            return {}
        
        correct = sum(1 for r in self.backtest_results if r['correct'])
        total = len(self.backtest_results)
        
        confidences = [r['confidence'] for r in self.backtest_results]
        avg_confidence = sum(confidences) / len(confidences)
        
        # Best predictions
        best_predictions = sorted(
            self.backtest_results,
            key=lambda x: x['confidence'],
            reverse=True
        )
        
        return {
            'accuracy': correct / total if total > 0 else 0,
            'avg_confidence': avg_confidence,
            'best_predictions': best_predictions
        }

    def save_backfill_report(self, pattern_stats, backtest_stats):
        """Save detailed backfill report to file"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'discovered_patterns': len(self.discovered_patterns),
            'pattern_stats': pattern_stats,
            'backtest_results': backtest_stats,
            'detailed_results': self.backtest_results
        }
        
        with open('pattern_backfill_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        log("✅ Detailed report saved to pattern_backfill_report.json")

# USAGE FUNCTIONS

async def run_quick_backfill(symbols=None, days=7):
    """Quick backfill for testing - 1 week of data"""
    if symbols is None:
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)

async def run_full_backfill(symbols=None, days=30):
    """Full backfill - 30 days of data"""
    if symbols is None:
        # Load your symbols from scanner or use top coins
        try:
            from scanner import fetch_symbols
            symbols = await fetch_symbols()
            symbols = symbols[:50]  # Limit to top 50 for speed
        except:
            symbols = [
                'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
                'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT'
            ]
    
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)

async def run_extended_backfill(symbols=None, days=60):
    """Extended backfill - 60 days for maximum pattern discovery"""
    if symbols is None:
        try:
            from scanner import fetch_symbols
            symbols = await fetch_symbols()
        except:
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']  # Minimal set for extended run
    
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)

# STANDALONE EXECUTION
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            asyncio.run(run_quick_backfill())
        elif sys.argv[1] == "full":
            asyncio.run(run_full_backfill())
        elif sys.argv[1] == "extended":
            asyncio.run(run_extended_backfill())
    else:
        print("Usage:")
        print("  python pattern_backfill.py quick    # 7 days, 5 symbols")
        print("  python pattern_backfill.py full     # 30 days, 50 symbols")  
        print("  python pattern_backfill.py extended # 60 days, all symbols")
