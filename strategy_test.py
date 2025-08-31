# comprehensive_backtest.py - FIXED VERSION - Addresses function signature issues
# Test ALL your strategies with proper function calls and error handling

import asyncio
import json
import os
import pandas as pd
import bisect
import random
from datetime import datetime, timedelta
from collections import defaultdict
import time
from logger import log
from bybit_api import signed_request

# Import all your strategies with error handling
try:
    from score import enhanced_score_symbol, score_symbol, determine_direction, calculate_confidence, has_pump_potential, detect_momentum_strength
except ImportError as e:
    log(f"❌ Import error for score functions: {e}")

try:
    from mean_reversion import score_mean_reversion
except ImportError as e:
    log(f"❌ Import error for mean_reversion: {e}")

try:
    from breakout_sniper import score_breakout_sniper
except ImportError as e:
    log(f"❌ Import error for breakout_sniper: {e}")

try:
    from pattern_matcher import pattern_match_scan
except ImportError as e:
    log(f"❌ Import error for pattern_matcher: {e}")

try:
    from pattern_discovery import pattern_discovery_scan
except ImportError as e:
    log(f"❌ Import error for pattern_discovery: {e}")

try:
    from range_break_detector import range_break_detector, scan_for_breaks_and_pumps
except ImportError as e:
    log(f"❌ Import error for range_break_detector: {e}")

try:
    from stealth_detector import detect_stealth_accumulation_advanced, calculate_accumulation_score
except ImportError as e:
    log(f"❌ Import error for stealth_detector: {e}")

try:
    from pump_detector import detect_early_pump
except ImportError as e:
    log(f"❌ Import error for pump_detector: {e}")

try:
    from trend_filters import get_trend_context_cached
except ImportError as e:
    log(f"❌ Import error for trend_filters: {e}")

try:
    from trade_executor import calculate_dynamic_sl_tp
except ImportError as e:
    log(f"❌ Import error for trade_executor: {e}")

FEE_PCT = 0.0006     # 0.06% taker per side
SLIP_PCT = 0.0002    # 0.02% slippage per side

class FixedComprehensiveBacktester:
    def __init__(self):
        self.historical_data = {}
        self.all_trades = []
        self.strategy_performance = defaultdict(list)
        self.daily_pnl = defaultdict(float)
        self._ts_index = {}
        
        # Strategy configurations with proper function signatures
        self.strategies = {
            'core_strategy': {
                'function': self.test_core_strategy,
                'min_score': 7.0,
                'enabled': True,
                'description': 'Main trend-following strategy'
            },
            'enhanced_core': {
                'function': self.test_enhanced_core_strategy,
                'min_score': 8.0,
                'enabled': True,
                'description': 'Enhanced core with advanced scoring'
            },
            'mean_reversion': {
                'function': self.test_mean_reversion,
                'min_score': 4.0,
                'enabled': True,
                'description': 'Mean reversion for ranging markets'
            },
            'breakout_sniper': {
                'function': self.test_breakout_sniper,
                'min_score': 4.0,
                'enabled': True,
                'description': 'Breakout detection with patterns'
            },
            'pattern_matching': {
                'function': self.test_pattern_matching,
                'min_score': 0.6,  # Similarity threshold
                'enabled': True,
                'description': 'Historical pattern matching'
            },
            'pattern_discovery': {
                'function': self.test_pattern_discovery,
                'min_score': 0.7,
                'enabled': True,
                'description': 'Dynamic pattern discovery'
            },
            'range_break': {
                'function': self.test_range_break,
                'min_score': 6.0,
                'enabled': True,
                'description': 'Range breakout detection'
            },
            'stealth_accumulation': {
                'function': self.test_stealth_accumulation,
                'min_score': 0.6,
                'enabled': True,
                'description': 'Stealth accumulation detection'
            },
            'pump_detector': {
                'function': self.test_pump_detector,
                'min_score': 0.7,
                'enabled': True,
                'description': 'Early pump detection'
            },
            'momentum_surge': {
                'function': self.test_momentum_surge,
                'min_score': 8.0,
                'enabled': True,
                'description': 'Strong momentum detection'
            }
        }

    async def run_comprehensive_backtest(self, symbols, days=30, initial_balance=10000):
        """Run complete backtest on all strategies"""
        
        log(f"🚀 Starting FIXED comprehensive {days}-day backtest")
        log(f"💰 Initial balance: ${initial_balance:,.2f}")
        log(f"📊 Testing {len(symbols)} symbols")
        log(f"🎯 Strategies: {[name for name, config in self.strategies.items() if config['enabled']]}")
        
        # Step 1: Download historical data
        await self.download_all_historical_data(symbols, days)
        
        # Step 2: Run backtests for each strategy
        await self.backtest_all_strategies(symbols, days, initial_balance)
        
        # Step 3: Generate comprehensive report
        self.generate_comprehensive_report(initial_balance)
        
        log("✅ FIXED comprehensive backtest completed!")

    async def download_all_historical_data(self, symbols, days):
        """Download historical data for all symbols and timeframes"""
        log(f"📥 Downloading {days} days of historical data...")
        
        timeframes = ['1', '3', '5', '15', '30', '60', '240']  # All timeframes you use
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        for symbol in symbols:
            log(f"📊 Downloading data for {symbol}...")
            self.historical_data[symbol] = {}
            self._ts_index[symbol] = {}
            
            for tf in timeframes:
                try:
                    # Calculate limit based on timeframe
                    tf_minutes = int(tf)
                    max_candles = min((days * 24 * 60) // tf_minutes, 1000)
                    
                    response = await signed_request(
                        method='GET',
                        endpoint='/v5/market/kline',
                        params={
                            'category': 'linear',
                            'symbol': symbol,
                            'interval': tf,
                            'start': start_time,
                            'end': end_time,
                            'limit': max_candles
                        }
                    )
                    
                    if response.get('result') and response['result'].get('list'):
                        candles = []
                        timestamps = []
                        
                        for kline in reversed(response['result']['list']):  # Reverse to get chronological order
                            timestamp = int(kline[0])
                            candle = {
                                'timestamp': timestamp,
                                'open': float(kline[1]),
                                'high': float(kline[2]),
                                'low': float(kline[3]),
                                'close': float(kline[4]),
                                'volume': float(kline[5])
                            }
                            candles.append(candle)
                            timestamps.append(timestamp)
                        
                        self.historical_data[symbol][tf] = candles
                        self._ts_index[symbol][tf] = timestamps
                        
                        log(f"   ✅ {tf}m: {len(candles)} candles")
                    else:
                        log(f"   ❌ {tf}m: No data received")
                        self.historical_data[symbol][tf] = []
                        self._ts_index[symbol][tf] = []
                        
                except Exception as e:
                    log(f"   ❌ Error downloading {tf}m data: {e}")
                    self.historical_data[symbol][tf] = []
                    self._ts_index[symbol][tf] = []
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)

    def get_candles_at_timestamp(self, symbol, timestamp):
        """Get candles for all timeframes at specific timestamp"""
        candles_by_tf = {}
        
        for tf, candles in self.historical_data.get(symbol, {}).items():
            if not candles:
                continue
                
            ts_list = self._ts_index[symbol][tf]
            i = bisect.bisect_right(ts_list, timestamp)
            
            # Get sufficient candles for analysis (up to last 100)
            start_idx = max(0, i - 100)
            end_idx = i
            
            if start_idx < end_idx:
                candles_by_tf[tf] = candles[start_idx:end_idx]
        
        return candles_by_tf

    def get_price_at_timestamp(self, symbol, timestamp):
        """Get price at specific timestamp (using 1m candles)"""
        series = self.historical_data.get(symbol, {}).get('1')
        if not series:
            return None
        
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_right(ts_list, timestamp)
        
        return series[i-1]['close'] if i > 0 else None

    def get_next_open(self, symbol, timestamp):
        """Get next candle open price (for more realistic entry simulation)"""
        series = self.historical_data.get(symbol, {}).get('1')
        if not series:
            return None
        
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_right(ts_list, timestamp)
        
        return series[i]['open'] if 0 <= i < len(series) else None

    async def backtest_all_strategies(self, symbols, days, initial_balance):
        """Run backtest simulation across all enabled strategies"""
        log("🧪 Running FIXED strategy backtests...")
        
        current_balance = initial_balance
        open_trades = {}
        trade_id = 0
        
        # Track strategy testing results for debugging
        strategy_test_results = defaultdict(lambda: {"tested": 0, "signals": 0, "errors": 0})
        
        # Get all timestamps for simulation (using 1m candles as base)
        all_timestamps = set()
        for symbol in symbols:
            if symbol in self.historical_data and '1' in self.historical_data[symbol]:
                timestamps = [c['timestamp'] for c in self.historical_data[symbol]['1']]
                all_timestamps.update(timestamps)
        
        sorted_timestamps = sorted(all_timestamps)
        
        log(f"📈 Processing {len(sorted_timestamps)} timestamps...")
        
        # Simulate trading at each timestamp
        for i, timestamp in enumerate(sorted_timestamps):
            if i % 2000 == 0:  # Progress update every 2000 timestamps
                progress = (i / len(sorted_timestamps)) * 100
                log(f"📊 Progress: {progress:.1f}% ({i}/{len(sorted_timestamps)})")
                
                # Print strategy testing stats every so often
                if i > 0:
                    log("🔍 Strategy Testing Stats:")
                    for strategy_name, stats in strategy_test_results.items():
                        signal_rate = (stats["signals"] / stats["tested"] * 100) if stats["tested"] > 0 else 0
                        error_rate = (stats["errors"] / stats["tested"] * 100) if stats["tested"] > 0 else 0
                        log(f"   {strategy_name}: {stats['tested']} tested, {stats['signals']} signals ({signal_rate:.1f}%), {stats['errors']} errors ({error_rate:.1f}%)")
            
            current_time = datetime.fromtimestamp(timestamp / 1000)
            
            # Check exits first
            trades_to_close = []
            for trade_id_key, trade in open_trades.items():
                exit_result = self.check_trade_exit(trade, timestamp)
                if exit_result:
                    trades_to_close.append((trade_id_key, trade, exit_result))
            
            # Close trades and update balance
            for trade_id_key, trade, exit_result in trades_to_close:
                pnl = exit_result['pnl']
                current_balance += pnl
                
                # Record completed trade
                completed_trade = {
                    **trade,
                    'exit_time': datetime.fromtimestamp(timestamp / 1000).isoformat(),
                    'exit_price': exit_result['exit_price'],
                    'exit_reason': exit_result['reason'],
                    'pnl': pnl,
                    'pnl_pct': (pnl / trade['position_value']) * 100,
                    'duration_minutes': (timestamp - trade['entry_timestamp']) // 60000
                }
                
                self.all_trades.append(completed_trade)
                self.strategy_performance[trade['strategy']].append(completed_trade)
                
                del open_trades[trade_id_key]
            
            # Don't open new trades if we have too many open
            if len(open_trades) >= 5:  # Max 5 concurrent trades
                continue
                
            # Check for new signals for each symbol
            for symbol in symbols:
                if len(open_trades) >= 5:
                    break
                
                # Skip if already have a trade on this symbol
                if any(trade['symbol'] == symbol for trade in open_trades.values()):
                    continue
                
                candles_by_tf = self.get_candles_at_timestamp(symbol, timestamp)
                if not candles_by_tf or '1' not in candles_by_tf:
                    continue
                
                # Test each enabled strategy
                for strategy_name, strategy_config in self.strategies.items():
                    if not strategy_config['enabled']:
                        continue
                        
                    if len(open_trades) >= 5:
                        break
                    
                    strategy_test_results[strategy_name]["tested"] += 1
                    
                    try:
                        signal = await strategy_config['function'](symbol, candles_by_tf, timestamp)
                        
                        if signal and signal.get('score', 0) >= strategy_config['min_score']:
                            strategy_test_results[strategy_name]["signals"] += 1
                            
                            # Simulate entry with delay (2-6 seconds)
                            delay_ms = random.randint(2000, 6000)
                            entry_price = self.get_next_open(symbol, timestamp + delay_ms)
                            
                            if not entry_price:
                                continue
                            
                            # Calculate position size (2% risk)
                            risk_per_trade = current_balance * 0.02
                            sl_distance_pct = abs(signal.get('sl_pct', 2.0))
                            position_value = risk_per_trade / (sl_distance_pct / 100)
                            
                            # Don't risk more than 5% of balance per trade
                            position_value = min(position_value, current_balance * 0.05)
                            
                            if position_value < 100:  # Minimum position size
                                continue
                            
                            # Create trade record
                            trade_id += 1
                            trade = {
                                'id': trade_id,
                                'strategy': strategy_name,
                                'symbol': symbol,
                                'entry_time': current_time.isoformat(),
                                'entry_timestamp': timestamp,
                                'entry_price': entry_price,
                                'direction': signal['direction'],
                                'position_value': position_value,
                                'score': signal.get('score', 0),
                                'confidence': signal.get('confidence', 0),
                                'sl_price': signal.get('sl_price'),
                                'tp1_price': signal.get('tp1_price'),
                                'trade_type': signal.get('trade_type', 'Intraday'),
                                'reserved_margin': position_value
                            }
                            
                            open_trades[trade_id] = trade
                            current_balance -= position_value  # Reserve margin
                            
                            log(f"📈 {strategy_name} SIGNAL: {symbol} {signal['direction']} @ {entry_price:.6f} (score: {signal.get('score', 0):.2f})")
                            
                            # Only take one signal per symbol per timestamp
                            break
                            
                    except Exception as e:
                        strategy_test_results[strategy_name]["errors"] += 1
                        log(f"❌ Error testing {strategy_name} on {symbol}: {e}")
                        continue
        
        # Close any remaining open trades at the end
        final_timestamp = sorted_timestamps[-1] if sorted_timestamps else int(time.time() * 1000)
        
        for trade in list(open_trades.values()):
            # Simulate closing at last available price
            exit_price = self.get_price_at_timestamp(trade['symbol'], final_timestamp)
            if exit_price:
                # Calculate PnL
                if trade['direction'] == 'Long':
                    price_change = (exit_price - trade['entry_price']) / trade['entry_price']
                else:
                    price_change = (trade['entry_price'] - exit_price) / trade['entry_price']
                
                # Apply fees and slippage
                total_fees = FEE_PCT + SLIP_PCT
                pnl = (price_change - total_fees) * trade['position_value']
                
                current_balance += (trade['position_value'] + pnl)
                
                completed_trade = {
                    **trade,
                    'exit_time': datetime.fromtimestamp(final_timestamp / 1000).isoformat(),
                    'exit_price': exit_price,
                    'exit_reason': 'backtest_end',
                    'pnl': pnl,
                    'pnl_pct': (pnl / trade['position_value']) * 100,
                    'duration_minutes': (final_timestamp - trade['entry_timestamp']) // 60000
                }
                
                self.all_trades.append(completed_trade)
                self.strategy_performance[trade['strategy']].append(completed_trade)
        
        final_balance = current_balance
        total_return = ((final_balance - initial_balance) / initial_balance) * 100
        
        log(f"💰 Final balance: ${final_balance:,.2f}")
        log(f"📈 Total return: {total_return:+.2f}%")
        log(f"📊 Total trades: {len(self.all_trades)}")
        
        # Final strategy testing summary
        log("\n🎯 FINAL STRATEGY TESTING SUMMARY:")
        for strategy_name, stats in strategy_test_results.items():
            signal_rate = (stats["signals"] / stats["tested"] * 100) if stats["tested"] > 0 else 0
            error_rate = (stats["errors"] / stats["tested"] * 100) if stats["tested"] > 0 else 0
            log(f"   {strategy_name}: {stats['tested']} tests, {stats['signals']} signals ({signal_rate:.2f}%), {stats['errors']} errors ({error_rate:.2f}%)")

    def check_trade_exit(self, trade, timestamp):
        """Check if trade should be closed (SL/TP hit)"""
        current_price = self.get_price_at_timestamp(trade['symbol'], timestamp)
        if not current_price:
            return None
        
        direction = trade['direction']
        entry_price = trade['entry_price']
        sl_price = trade.get('sl_price')
        tp1_price = trade.get('tp1_price')
        
        def calculate_pnl_with_fees(exit_price):
            if direction == 'Long':
                price_change = (exit_price - entry_price) / entry_price
            else:
                price_change = (entry_price - exit_price) / entry_price
            
            total_fees = FEE_PCT + SLIP_PCT
            return (price_change - total_fees) * trade['position_value']
        
        # Check stop loss
        if sl_price:
            if (direction == 'Long' and current_price <= sl_price) or \
               (direction == 'Short' and current_price >= sl_price):
                
                return {
                    'exit_price': current_price,
                    'reason': 'stop_loss',
                    'pnl': calculate_pnl_with_fees(current_price)
                }
        
        # Check take profit
        if tp1_price:
            if (direction == 'Long' and current_price >= tp1_price) or \
               (direction == 'Short' and current_price <= tp1_price):
                
                return {
                    'exit_price': current_price,
                    'reason': 'take_profit',
                    'pnl': calculate_pnl_with_fees(current_price)
                }
        
        # Time-based exit (max 4 hours for intraday, 24 hours for swing)
        max_duration_minutes = 240 if trade.get('trade_type') == 'Intraday' else 1440
        duration_minutes = (timestamp - trade['entry_timestamp']) // 60000
        
        if duration_minutes >= max_duration_minutes:
            return {
                'exit_price': current_price,
                'reason': 'time_exit',
                'pnl': calculate_pnl_with_fees(current_price)
            }
        
        return None

    # FIXED STRATEGY TESTING FUNCTIONS with proper error handling

    async def test_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test core strategy at specific timestamp"""
        try:
            score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                symbol, candles_by_tf
            )
            
            if score < 7.0:
                return None
            
            direction = determine_direction(tf_scores, indicator_scores)
            if not direction:
                return None

            try:
                trend_ctx = await get_trend_context_cached()
            except Exception:
                trend_ctx = {"btc_trend": "ranging", "regime": "volatile"}
            
            confidence = calculate_confidence(score, tf_scores, indicator_scores, used_indicators, trend_ctx, trade_type)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Fallback SL/TP calculation
            if direction == "Long":
                sl_price = entry_price * 0.98  # 2% SL
                tp1_price = entry_price * 1.04  # 4% TP
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.96
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': trade_type,
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 4.0
            }
            
        except Exception as e:
            log(f"❌ Core strategy error for {symbol}: {e}")
            return None

    async def test_enhanced_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test enhanced core strategy"""
        try:
            score, tf_scores, trade_type, indicator_scores, used_indicators = enhanced_score_symbol(
                symbol, candles_by_tf
            )
            
            if score < 8.0:
                return None
            
            direction = determine_direction(tf_scores, indicator_scores)
            if not direction:
                return None

            try:
                trend_ctx = await get_trend_context_cached()
            except Exception:
                trend_ctx = {"btc_trend": "ranging", "regime": "volatile"}
            
            confidence = calculate_confidence(score, tf_scores, indicator_scores, used_indicators, trend_ctx, trade_type)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Enhanced SL/TP calculation
            if direction == "Long":
                sl_price = entry_price * 0.985  # Tighter 1.5% SL
                tp1_price = entry_price * 1.05   # Higher 5% TP
            else:
                sl_price = entry_price * 1.015
                tp1_price = entry_price * 0.95
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': trade_type,
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 1.5,
                'tp1_pct': 5.0
            }
            
        except Exception as e:
            log(f"❌ Enhanced core strategy error for {symbol}: {e}")
            return None

    async def test_mean_reversion(self, symbol, candles_by_tf, timestamp):
        """Test mean reversion strategy"""
        try:
            score, direction, confidence, reasons = score_mean_reversion(
                symbol, candles_by_tf, "ranging"
            )
            
            if score < 4.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Mean reversion SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.985  # 1.5% SL
                tp1_price = entry_price * 1.025  # 2.5% TP
            else:
                sl_price = entry_price * 1.015
                tp1_price = entry_price * 0.975
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 1.5,
                'tp1_pct': 2.5
            }
            
        except Exception as e:
            log(f"❌ Mean reversion strategy error for {symbol}: {e}")
            return None

    async def test_breakout_sniper(self, symbol, candles_by_tf, timestamp):
        """Test breakout sniper strategy"""
        try:
            score, direction, confidence, reasons = score_breakout_sniper(
                symbol, candles_by_tf, "volatile"
            )
            
            if score < 4.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Breakout SL/TP (wider stops for volatility)
            if direction == "Long":
                sl_price = entry_price * 0.975  # 2.5% SL
                tp1_price = entry_price * 1.06   # 6% TP
            else:
                sl_price = entry_price * 1.025
                tp1_price = entry_price * 0.94
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.5,
                'tp1_pct': 6.0
            }
            
        except Exception as e:
            log(f"❌ Breakout sniper strategy error for {symbol}: {e}")
            return None

    async def test_pattern_matching(self, symbol, candles_by_tf, timestamp):
        """FIXED: Test pattern matching strategy with single symbol"""
        try:
            if '5' not in candles_by_tf or len(candles_by_tf['5']) < 20:
                return None
                
            # CRITICAL FIX: pattern_match_scan expects list of symbols, not candles
            # We need to simulate it with single symbol analysis
            
            from pattern_detector import detect_pattern
            from pattern_matcher import load_pattern_memory
            
            # Detect current pattern
            candles = candles_by_tf['5']
            current_pattern = detect_pattern(candles)
            
            if not current_pattern:
                return None
            
            # Load pattern database
            patterns_db = load_pattern_memory()
            if not patterns_db:
                return None
                
            # Find matching historical patterns
            pattern_records = [r for r in patterns_db if r.get('pattern') == current_pattern]
            if not pattern_records:
                return None
            
            # Calculate similarity/success rate
            profitable = sum(1 for r in pattern_records if r.get('move_pct', 0) > 1.0)
            win_rate = profitable / len(pattern_records) if pattern_records else 0
            
            if win_rate < 0.6:  # 60% threshold
                return None
            
            # Determine direction from historical data
            avg_move = sum(r.get('move_pct', 0) for r in pattern_records) / len(pattern_records)
            direction = 'Long' if avg_move > 0 else 'Short'
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Pattern-based SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.04
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.96
            
            return {
                'score': win_rate * 10,  # Convert to score (0.6-1.0 → 6.0-10.0)
                'direction': direction,
                'confidence': win_rate,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 4.0
            }
            
        except Exception as e:
            log(f"❌ Pattern matching strategy error for {symbol}: {e}")
            return None

    async def test_pattern_discovery(self, symbol, candles_by_tf, timestamp):
        """FIXED: Test pattern discovery strategy"""
        try:
            if '5' not in candles_by_tf or len(candles_by_tf['5']) < 15:
                return None
                
            # CRITICAL FIX: pattern_discovery_scan expects list of symbols, not candles
            # We need to create a mock version or simulate it
            
            from pattern_detector import detect_pattern, analyze_pattern_strength
            
            candles = candles_by_tf['5']
            current_pattern = detect_pattern(candles)
            
            if not current_pattern:
                return None
            
            # Analyze pattern strength
            pattern_strength = analyze_pattern_strength(current_pattern, candles)
            if pattern_strength < 0.7:
                return None
            
            # Simple direction determination
            recent_candles = candles[-5:]  # Last 5 candles
            price_trend = (recent_candles[-1]['close'] - recent_candles[0]['close']) / recent_candles[0]['close']
            direction = 'Long' if price_trend > 0 else 'Short'
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Discovery pattern SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.982
                tp1_price = entry_price * 1.048  # 4.8% TP
            else:
                sl_price = entry_price * 1.018
                tp1_price = entry_price * 0.952
            
            return {
                'score': pattern_strength * 10,  # Convert to score
                'direction': direction,
                'confidence': pattern_strength,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 1.8,
                'tp1_pct': 4.8
            }
            
        except Exception as e:
            log(f"❌ Pattern discovery strategy error for {symbol}: {e}")
            return None

    async def test_range_break(self, symbol, candles_by_tf, timestamp):
        """Test range break strategy"""
        try:
            if '15' not in candles_by_tf or len(candles_by_tf['15']) < 20:
                return None
                
            result = range_break_detector(symbol, candles_by_tf, "ranging")
            if not result or result.get('score', 0) < 6.0:
                return None
            
            direction = result.get('direction', 'Long')
            score = result.get('score', 0)
            confidence = result.get('confidence', 0.5)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Range break SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.975  # 2.5% SL
                tp1_price = entry_price * 1.055  # 5.5% TP
            else:
                sl_price = entry_price * 1.025
                tp1_price = entry_price * 0.945
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.5,
                'tp1_pct': 5.5
            }
            
        except Exception as e:
            log(f"❌ Range break strategy error for {symbol}: {e}")
            return None

    async def test_stealth_accumulation(self, symbol, candles_by_tf, timestamp):
        """Test stealth accumulation strategy"""
        try:
            if '5' not in candles_by_tf or len(candles_by_tf['5']) < 25:
                return None
                
            # Test stealth accumulation
            stealth_result = detect_stealth_accumulation_advanced(candles_by_tf['5'])
            if not stealth_result.get('detected', False):
                return None
            
            strength = stealth_result.get('strength', 0)
            if strength < 0.6:
                return None
            
            # Calculate accumulation score
            accum_score = calculate_accumulation_score(candles_by_tf['5'])
            if accum_score < 0.6:
                return None
            
            # Stealth accumulation is typically bullish
            direction = 'Long'
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Conservative SL/TP for accumulation
            sl_price = entry_price * 0.985  # 1.5% SL
            tp1_price = entry_price * 1.035  # 3.5% TP
            
            return {
                'score': accum_score * 10,
                'direction': direction,
                'confidence': strength,
                'trade_type': 'Swing',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 1.5,
                'tp1_pct': 3.5
            }
            
        except Exception as e:
            log(f"❌ Stealth accumulation strategy error for {symbol}: {e}")
            return None

    async def test_pump_detector(self, symbol, candles_by_tf, timestamp):
        """Test early pump detection strategy"""
        try:
            if '1' not in candles_by_tf or '3' not in candles_by_tf:
                return None
                
            # Test for early pump signals
            pump_result = detect_early_pump(symbol, candles_by_tf)
            if not pump_result or pump_result.get('confidence', 0) < 0.7:
                return None
            
            # Also check for pump potential
            has_potential = has_pump_potential(symbol, candles_by_tf)
            if not has_potential:
                return None
            
            direction = pump_result.get('direction', 'Long')
            confidence = pump_result.get('confidence', 0)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Pump detection SL/TP (aggressive for quick moves)
            if direction == "Long":
                sl_price = entry_price * 0.97   # 3% SL
                tp1_price = entry_price * 1.08   # 8% TP
            else:
                sl_price = entry_price * 1.03
                tp1_price = entry_price * 0.92
            
            return {
                'score': confidence * 10,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Scalp',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 3.0,
                'tp1_pct': 8.0
            }
            
        except Exception as e:
            log(f"❌ Pump detector strategy error for {symbol}: {e}")
            return None

    async def test_momentum_surge(self, symbol, candles_by_tf, timestamp):
        """Test momentum surge detection"""
        try:
            if '3' not in candles_by_tf or '15' not in candles_by_tf:
                return None
                
            # Detect strong momentum
            momentum_strength = detect_momentum_strength(symbol, candles_by_tf)
            if not momentum_strength or momentum_strength.get('score', 0) < 8.0:
                return None
            
            direction = momentum_strength.get('direction', 'Long')
            score = momentum_strength.get('score', 0)
            confidence = momentum_strength.get('confidence', 0.5)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Momentum SL/TP (wider TP for strong moves)
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.065  # 6.5% TP
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.935
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 6.5
            }
            
        except Exception as e:
            log(f"❌ Momentum surge strategy error for {symbol}: {e}")
            return None

    def generate_comprehensive_report(self, initial_balance):
        """Generate detailed performance report for all strategies"""
        
        if not self.all_trades:
            log("❌ No trades to analyze")
            return
        
        log("📊 Generating FIXED comprehensive performance report...")
        
        # Overall performance
        total_pnl = sum(trade['pnl'] for trade in self.all_trades)
        total_trades = len(self.all_trades)
        winning_trades = len([t for t in self.all_trades if t['pnl'] > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Strategy-specific performance
        strategy_stats = {}
        for strategy_name in self.strategies.keys():
            strategy_trades = self.strategy_performance[strategy_name]
            
            if strategy_trades:
                strategy_pnl = sum(t['pnl'] for t in strategy_trades)
                strategy_wins = len([t for t in strategy_trades if t['pnl'] > 0])
                strategy_win_rate = strategy_wins / len(strategy_trades)
                avg_duration = sum(t['duration_minutes'] for t in strategy_trades) / len(strategy_trades)
                avg_pnl = strategy_pnl / len(strategy_trades)
                
                strategy_stats[strategy_name] = {
                    'total_trades': len(strategy_trades),
                    'total_pnl': strategy_pnl,
                    'win_rate': strategy_win_rate,
                    'avg_pnl_per_trade': avg_pnl,
                    'avg_duration_minutes': avg_duration,
                    'return_pct': (strategy_pnl / initial_balance) * 100
                }
            else:
                strategy_stats[strategy_name] = {
                    'total_trades': 0,
                    'total_pnl': 0,
                    'win_rate': 0,
                    'avg_pnl_per_trade': 0,
                    'avg_duration_minutes': 0,
                    'return_pct': 0
                }
        
        # Print summary
        print("\n" + "="*80)
        print("📈 FIXED COMPREHENSIVE STRATEGY BACKTEST RESULTS")
        print("="*80)
        
        print(f"\n💰 OVERALL PERFORMANCE:")
        print(f"   Initial Balance: ${initial_balance:,.2f}")
        print(f"   Final Balance: ${initial_balance + total_pnl:,.2f}")
        print(f"   Total PnL: ${total_pnl:+,.2f}")
        print(f"   Total Return: {(total_pnl / initial_balance) * 100:+.2f}%")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Avg PnL per Trade: ${total_pnl / total_trades:+.2f}")
        
        print(f"\n🎯 FIXED STRATEGY BREAKDOWN:")
        print("-" * 80)
        
        # Sort strategies by return percentage
        sorted_strategies = sorted(strategy_stats.items(), key=lambda x: x[1]['return_pct'], reverse=True)
        
        for i, (strategy, stats) in enumerate(sorted_strategies, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            strategy_description = self.strategies[strategy].get('description', strategy.replace('_', ' ').title())
            
            print(f"\n{emoji} {strategy_description}")
            print(f"   Return: {stats['return_pct']:+.2f}%")
            print(f"   PnL: ${stats['total_pnl']:+,.2f}")
            print(f"   Trades: {stats['total_trades']}")
            if stats['total_trades'] > 0:
                print(f"   Win Rate: {stats['win_rate']:.1%}")
                print(f"   Avg PnL/Trade: ${stats['avg_pnl_per_trade']:+.2f}")
                print(f"   Avg Duration: {stats['avg_duration_minutes']:.0f} min")
        
        # Save detailed report
        report_data = {
            'backtest_date': datetime.now().isoformat(),
            'backtest_type': 'fixed_comprehensive',
            'initial_balance': initial_balance,
            'final_balance': initial_balance + total_pnl,
            'total_return_pct': (total_pnl / initial_balance) * 100,
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'strategy_performance': strategy_stats,
            'strategy_configurations': {name: config for name, config in self.strategies.items()},
            'all_trades': self.all_trades,
            'daily_pnl': dict(self.daily_pnl)
        }
        
        # Save JSON report
        with open('fixed_backtest_report.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        # Save trades as CSV for analysis
        if self.all_trades:
            df = pd.DataFrame(self.all_trades)
            df.to_csv('fixed_backtest_trades.csv', index=False)
        
        print(f"\n📄 FIXED reports saved:")
        print(f"   📊 fixed_backtest_report.json - Complete analysis")
        print(f"   📈 fixed_backtest_trades.csv - Individual trade details")
        
        print("="*80)

# USAGE FUNCTIONS

async def run_fixed_quick_test():
    """Fixed quick test - 7 days"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    
    backtester = FixedComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=7, initial_balance=10000)

async def run_fixed_full_test():
    """Fixed full test - 30 days"""
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT',
        'MATICUSDT', 'ALGOUSDT', 'VETUSDT', 'FTMUSDT', 'ICPUSDT'
    ]
    
    backtester = FixedComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=30, initial_balance=10000)

async def run_debug_strategy_test():
    """Debug version to understand what's happening"""
    print("🔍 RUNNING DEBUG STRATEGY TEST")
    print("=" * 50)
    
    symbols = ['BTCUSDT']  # Test with just one symbol first
    backtester = FixedComprehensiveBacktester()
    
    # Enable detailed logging
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    await backtester.run_comprehensive_backtest(symbols, days=3, initial_balance=10000)

if __name__ == "__main__":
    print("🚀 FIXED COMPREHENSIVE STRATEGY BACKTESTER")
    print("=" * 60)
    print()
    print("🛠️ FIXES APPLIED:")
    print("✅ Fixed function signature mismatches")
    print("✅ Added proper error handling for all strategies")
    print("✅ Fixed pattern_match_scan parameter issue")
    print("✅ Fixed pattern_discovery_scan parameter issue")
    print("✅ Added detailed strategy testing statistics")
    print("✅ Added import error handling")
    print("✅ Added debug logging for strategy testing")
    print()
    print("Available Tests:")
    print("1. 🏃‍♂️ Fixed Quick Test (7 days)")
    print("2. 📊 Fixed Full Test (30 days)")
    print("3. 🔍 Debug Test (3 days, 1 symbol)")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        print("\n⚡ Running FIXED quick test...")
        asyncio.run(run_fixed_quick_test())
    elif choice == "2":
        print("\n📈 Running FIXED full backtest...")
        asyncio.run(run_fixed_full_test())
    elif choice == "3":
        print("\n🔍 Running DEBUG test...")
        asyncio.run(run_debug_strategy_test())
    else:
        print("Running FIXED quick test...")
        asyncio.run(run_fixed_quick_test())
