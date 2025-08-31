# clean_comprehensive_backtest.py - Syntax Error Free Version
# Clean version with all function signature fixes and no syntax errors

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

# Import strategies with error handling
try:
    from score import enhanced_score_symbol, score_symbol, determine_direction, calculate_confidence
    log("✅ Imported score functions")
except ImportError as e:
    log(f"❌ Import error for score functions: {e}")

try:
    from mean_reversion import score_mean_reversion
    log("✅ Imported mean_reversion")
except ImportError as e:
    log(f"❌ Import error for mean_reversion: {e}")

try:
    from breakout_sniper import score_breakout_sniper
    log("✅ Imported breakout_sniper")
except ImportError as e:
    log(f"❌ Import error for breakout_sniper: {e}")

FEE_PCT = 0.0006
SLIP_PCT = 0.0002

class CleanBacktester:
    def __init__(self):
        self.historical_data = {}
        self.all_trades = []
        self.strategy_performance = defaultdict(list)
        self.daily_pnl = defaultdict(float)
        self._ts_index = {}
        
        # Simple strategy configurations - only working ones
        self.strategies = {
            'core_strategy': {
                'function': self.test_core_strategy,
                'min_score': 7.0,
                'enabled': True,
                'description': 'Main trend-following strategy'
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
            }
        }

    async def run_comprehensive_backtest(self, symbols, days=7, initial_balance=10000):
        """Run complete backtest on all strategies"""
        
        log(f"🚀 Starting CLEAN {days}-day backtest")
        log(f"💰 Initial balance: ${initial_balance:,.2f}")
        log(f"📊 Testing {len(symbols)} symbols")
        log(f"🎯 Strategies: {[name for name, config in self.strategies.items() if config['enabled']]}")
        
        # Step 1: Download historical data
        await self.download_all_historical_data(symbols, days)
        
        # Step 2: Run backtests for each strategy
        await self.backtest_all_strategies(symbols, days, initial_balance)
        
        # Step 3: Generate comprehensive report
        self.generate_comprehensive_report(initial_balance)
        
        log("✅ CLEAN comprehensive backtest completed!")

    async def download_all_historical_data(self, symbols, days):
        """Download historical data for all symbols and timeframes"""
        log(f"📥 Downloading {days} days of historical data...")
        
        timeframes = ['1', '3', '5', '15', '30']  # Essential timeframes
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        for symbol in symbols:
            log(f"📊 Downloading data for {symbol}...")
            self.historical_data[symbol] = {}
            self._ts_index[symbol] = {}
            
            for tf in timeframes:
                try:
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
                        
                        for kline in reversed(response['result']['list']):
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
                
                await asyncio.sleep(0.1)

    def get_candles_at_timestamp(self, symbol, timestamp):
        """Get candles for all timeframes at specific timestamp"""
        candles_by_tf = {}
        
        for tf, candles in self.historical_data.get(symbol, {}).items():
            if not candles:
                continue
                
            ts_list = self._ts_index[symbol][tf]
            i = bisect.bisect_right(ts_list, timestamp)
            
            start_idx = max(0, i - 100)
            end_idx = i
            
            if start_idx < end_idx:
                candles_by_tf[tf] = candles[start_idx:end_idx]
        
        return candles_by_tf

    def get_price_at_timestamp(self, symbol, timestamp):
        """Get price at specific timestamp"""
        series = self.historical_data.get(symbol, {}).get('1')
        if not series:
            return None
        
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_right(ts_list, timestamp)
        
        return series[i-1]['close'] if i > 0 else None

    def get_next_open(self, symbol, timestamp):
        """Get next candle open price"""
        series = self.historical_data.get(symbol, {}).get('1')
        if not series:
            return None
        
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_right(ts_list, timestamp)
        
        return series[i]['open'] if 0 <= i < len(series) else None

    async def backtest_all_strategies(self, symbols, days, initial_balance):
        """Run backtest simulation across all enabled strategies"""
        log("🧪 Running CLEAN strategy backtests...")
        
        current_balance = initial_balance
        open_trades = {}
        trade_id = 0
        
        # Get all timestamps
        all_timestamps = set()
        for symbol in symbols:
            if symbol in self.historical_data and '1' in self.historical_data[symbol]:
                timestamps = [c['timestamp'] for c in self.historical_data[symbol]['1']]
                all_timestamps.update(timestamps)
        
        sorted_timestamps = sorted(all_timestamps)
        log(f"📈 Processing {len(sorted_timestamps)} timestamps...")
        
        # Simulate trading at each timestamp
        for i, timestamp in enumerate(sorted_timestamps):
            if i % 2000 == 0:
                progress = (i / len(sorted_timestamps)) * 100
                log(f"📊 Progress: {progress:.1f}% ({i}/{len(sorted_timestamps)})")
            
            current_time = datetime.fromtimestamp(timestamp / 1000)
            
            # Check exits first
            trades_to_close = []
            for trade_id_key, trade in open_trades.items():
                exit_result = self.check_trade_exit(trade, timestamp)
                if exit_result:
                    trades_to_close.append((trade_id_key, trade, exit_result))
            
            # Close trades
            for trade_id_key, trade, exit_result in trades_to_close:
                pnl = exit_result['pnl']
                current_balance += pnl
                
                completed_trade = {
                    'id': trade['id'],
                    'strategy': trade['strategy'],
                    'symbol': trade['symbol'],
                    'entry_time': trade['entry_time'],
                    'entry_timestamp': trade['entry_timestamp'],
                    'entry_price': trade['entry_price'],
                    'direction': trade['direction'],
                    'position_value': trade['position_value'],
                    'score': trade['score'],
                    'confidence': trade['confidence'],
                    'sl_price': trade.get('sl_price'),
                    'tp1_price': trade.get('tp1_price'),
                    'trade_type': trade.get('trade_type', 'Intraday'),
                    'exit_time': current_time.isoformat(),
                    'exit_price': exit_result['exit_price'],
                    'exit_reason': exit_result['reason'],
                    'pnl': pnl,
                    'pnl_pct': (pnl / trade['position_value']) * 100,
                    'duration_minutes': (timestamp - trade['entry_timestamp']) // 60000
                }
                
                self.all_trades.append(completed_trade)
                self.strategy_performance[trade['strategy']].append(completed_trade)
                
                del open_trades[trade_id_key]
            
            if len(open_trades) >= 5:
                continue
                
            # Check for new signals
            for symbol in symbols:
                if len(open_trades) >= 5:
                    break
                
                if any(trade['symbol'] == symbol for trade in open_trades.values()):
                    continue
                
                candles_by_tf = self.get_candles_at_timestamp(symbol, timestamp)
                if not candles_by_tf or '1' not in candles_by_tf:
                    continue
                
                # Test each strategy
                for strategy_name, strategy_config in self.strategies.items():
                    if not strategy_config['enabled']:
                        continue
                        
                    if len(open_trades) >= 5:
                        break
                    
                    try:
                        signal = await strategy_config['function'](symbol, candles_by_tf, timestamp)
                        
                        if signal and signal.get('score', 0) >= strategy_config['min_score']:
                            delay_ms = random.randint(2000, 6000)
                            entry_price = self.get_next_open(symbol, timestamp + delay_ms)
                            
                            if not entry_price:
                                continue
                            
                            risk_per_trade = current_balance * 0.02
                            sl_distance_pct = abs(signal.get('sl_pct', 2.0))
                            position_value = risk_per_trade / (sl_distance_pct / 100)
                            position_value = min(position_value, current_balance * 0.05)
                            
                            if position_value < 100:
                                continue
                            
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
                                'trade_type': signal.get('trade_type', 'Intraday')
                            }
                            
                            open_trades[trade_id] = trade
                            current_balance -= position_value
                            
                            log(f"📈 {strategy_name} SIGNAL: {symbol} {signal['direction']} @ {entry_price:.6f} (score: {signal.get('score', 0):.2f})")
                            break
                            
                    except Exception as e:
                        log(f"❌ Error testing {strategy_name} on {symbol}: {e}")
                        continue
        
        # Close remaining trades
        final_timestamp = sorted_timestamps[-1] if sorted_timestamps else int(time.time() * 1000)
        
        for trade in list(open_trades.values()):
            exit_price = self.get_price_at_timestamp(trade['symbol'], final_timestamp)
            if exit_price:
                if trade['direction'] == 'Long':
                    price_change = (exit_price - trade['entry_price']) / trade['entry_price']
                else:
                    price_change = (trade['entry_price'] - exit_price) / trade['entry_price']
                
                total_fees = FEE_PCT + SLIP_PCT
                pnl = (price_change - total_fees) * trade['position_value']
                
                current_balance += (trade['position_value'] + pnl)
                
                completed_trade = {
                    'id': trade['id'],
                    'strategy': trade['strategy'],
                    'symbol': trade['symbol'],
                    'entry_time': trade['entry_time'],
                    'entry_timestamp': trade['entry_timestamp'],
                    'entry_price': trade['entry_price'],
                    'direction': trade['direction'],
                    'position_value': trade['position_value'],
                    'score': trade['score'],
                    'confidence': trade['confidence'],
                    'sl_price': trade.get('sl_price'),
                    'tp1_price': trade.get('tp1_price'),
                    'trade_type': trade.get('trade_type', 'Intraday'),
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

    def check_trade_exit(self, trade, timestamp):
        """Check if trade should be closed"""
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
            if (direction == 'Long' and current_price <= sl_price) or (direction == 'Short' and current_price >= sl_price):
                return {
                    'exit_price': current_price,
                    'reason': 'stop_loss',
                    'pnl': calculate_pnl_with_fees(current_price)
                }
        
        # Check take profit
        if tp1_price:
            if (direction == 'Long' and current_price >= tp1_price) or (direction == 'Short' and current_price <= tp1_price):
                return {
                    'exit_price': current_price,
                    'reason': 'take_profit',
                    'pnl': calculate_pnl_with_fees(current_price)
                }
        
        # Time-based exit
        max_duration_minutes = 240 if trade.get('trade_type') == 'Intraday' else 1440
        duration_minutes = (timestamp - trade['entry_timestamp']) // 60000
        
        if duration_minutes >= max_duration_minutes:
            return {
                'exit_price': current_price,
                'reason': 'time_exit',
                'pnl': calculate_pnl_with_fees(current_price)
            }
        
        return None

    # STRATEGY TESTING FUNCTIONS

    async def test_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test core strategy with correct function signatures"""
        try:
            score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(symbol, candles_by_tf)
            
            if score < 7.0:
                return None
            
            # FIXED: determine_direction only takes tf_scores (1 parameter)
            direction = determine_direction(tf_scores)
            if not direction:
                return None

            try:
                from trend_filters import get_trend_context_cached
                trend_ctx = await get_trend_context_cached()
            except Exception:
                trend_ctx = {"btc_trend": "ranging", "regime": "volatile"}
            
            confidence = calculate_confidence(score, tf_scores, trend_ctx, trade_type)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Simple SL/TP calculation
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.04
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

    async def test_mean_reversion(self, symbol, candles_by_tf, timestamp):
        """Test mean reversion strategy"""
        try:
            score, direction, confidence, reasons = score_mean_reversion(symbol, candles_by_tf, "ranging")
            
            if score < 4.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            if direction == "Long":
                sl_price = entry_price * 0.985
                tp1_price = entry_price * 1.025
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
            score, direction, confidence, reasons = score_breakout_sniper(symbol, candles_by_tf, "volatile")
            
            if score < 4.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            if direction == "Long":
                sl_price = entry_price * 0.975
                tp1_price = entry_price * 1.06
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

    def generate_comprehensive_report(self, initial_balance):
        """Generate detailed performance report"""
        
        if not self.all_trades:
            log("❌ No trades to analyze")
            return
        
        log("📊 Generating CLEAN comprehensive performance report...")
        
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
        print("📈 CLEAN COMPREHENSIVE STRATEGY BACKTEST RESULTS")
        print("="*80)
        
        print(f"\n💰 OVERALL PERFORMANCE:")
        print(f"   Initial Balance: ${initial_balance:,.2f}")
        print(f"   Final Balance: ${initial_balance + total_pnl:,.2f}")
        print(f"   Total PnL: ${total_pnl:+,.2f}")
        print(f"   Total Return: {(total_pnl / initial_balance) * 100:+.2f}%")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1%}")
        if total_trades > 0:
            print(f"   Avg PnL per Trade: ${total_pnl / total_trades:+.2f}")
        
        print(f"\n🎯 CLEAN STRATEGY BREAKDOWN:")
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
        
        # Save reports
        report_data = {
            'backtest_date': datetime.now().isoformat(),
            'backtest_type': 'clean_comprehensive',
            'initial_balance': initial_balance,
            'final_balance': initial_balance + total_pnl,
            'total_return_pct': (total_pnl / initial_balance) * 100,
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'strategy_performance': strategy_stats,
            'all_trades': self.all_trades
        }
        
        with open('clean_backtest_report.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        if self.all_trades:
            df = pd.DataFrame(self.all_trades)
            df.to_csv('clean_backtest_trades.csv', index=False)
        
        print(f"\n📄 CLEAN reports saved:")
        print(f"   📊 clean_backtest_report.json")
        print(f"   📈 clean_backtest_trades.csv")
        
        print("="*80)

# USAGE FUNCTIONS

async def run_clean_test():
    """Run the clean comprehensive test"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    
    backtester = CleanBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=7, initial_balance=10000)

if __name__ == "__main__":
    print("🚀 CLEAN COMPREHENSIVE STRATEGY BACKTESTER")
    print("=" * 60)
    print()
    print("🛠️ SYNTAX ERROR FREE VERSION:")
    print("✅ Fixed all function signature issues")
    print("✅ Clean syntax with no indentation errors")
    print("✅ Only essential strategies (core, mean_reversion, breakout_sniper)")
    print("✅ Comprehensive error handling")
    print()
    
    print("Running clean test...")
    asyncio.run(run_clean_test())
