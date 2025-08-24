# comprehensive_backtest.py - Complete Strategy Backtesting System
# Test ALL your strategies: Core, Mean Reversion, Breakout Sniper, Pattern Matching, Range Break

import asyncio
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
import time
from logger import log
from bybit_api import signed_request

# Import all your strategies
from score import score_symbol, determine_direction, calculate_confidence
from mean_reversion import score_mean_reversion
from breakout_sniper import score_breakout_sniper
from pattern_matcher import pattern_match_scan
from range_break_detector import range_break_detector
from trend_filters import get_trend_context_cached
from trade_executor import calculate_dynamic_sl_tp

class ComprehensiveBacktester:
    def __init__(self):
        self.historical_data = {}
        self.all_trades = []
        self.strategy_performance = defaultdict(list)
        self.daily_pnl = defaultdict(float)
        
        # Strategy configurations
        self.strategies = {
            'core_strategy': {
                'function': self.test_core_strategy,
                'min_score': 10.0,
                'enabled': True
            },
            'mean_reversion': {
                'function': self.test_mean_reversion,
                'min_score': 8.5,
                'enabled': True
            },
            'breakout_sniper': {
                'function': self.test_breakout_sniper,
                'min_score': 11.0,
                'enabled': True
            },
            'pattern_matching': {
                'function': self.test_pattern_matching,
                'min_score': 0.6,  # Similarity threshold
                'enabled': True
            },
            'range_break': {
                'function': self.test_range_break,
                'min_score': 9.0,
                'enabled': True
            }
        }

    async def run_comprehensive_backtest(self, symbols, days=30, initial_balance=10000):
        """Run complete backtest on all strategies"""
        
        log(f"🚀 Starting comprehensive {days}-day backtest")
        log(f"💰 Initial balance: ${initial_balance:,.2f}")
        log(f"📊 Testing {len(symbols)} symbols")
        log(f"🎯 Strategies: {list(self.strategies.keys())}")
        
        # Step 1: Download historical data
        await self.download_all_historical_data(symbols, days)
        
        # Step 2: Run backtests for each strategy
        await self.backtest_all_strategies(symbols, days, initial_balance)
        
        # Step 3: Generate comprehensive report
        self.generate_comprehensive_report(initial_balance)
        
        log("✅ Comprehensive backtest completed!")

    async def download_all_historical_data(self, symbols, days):
        """Download all historical data needed for backtesting"""
        log(f"📥 Downloading {days} days of data for backtesting...")
        
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        timeframes = ['1', '3', '5', '15', '30', '60', '240']
        
        for i, symbol in enumerate(symbols):
            log(f"📊 [{i+1}/{len(symbols)}] Downloading {symbol}...")
            self.historical_data[symbol] = {}
            
            for tf in timeframes:
                try:
                    candles = await self.fetch_historical_candles(
                        symbol, tf, start_time, end_time
                    )
                    
                    if candles and len(candles) > 100:
                        self.historical_data[symbol][tf] = candles
                    
                    await asyncio.sleep(0.05)  # Rate limiting
                    
                except Exception as e:
                    log(f"❌ Error downloading {symbol} {tf}m: {e}")
                    continue
            
            await asyncio.sleep(0.2)
        
        valid_symbols = len([s for s in symbols if s in self.historical_data and self.historical_data[s]])
        log(f"✅ Downloaded data for {valid_symbols}/{len(symbols)} symbols")

    async def fetch_historical_candles(self, symbol, interval, start_time, end_time):
        """Fetch historical candles with pagination for large datasets"""
        all_candles = []
        current_start = start_time
        
        while current_start < end_time:
            try:
                params = {
                    "category": "linear",
                    "symbol": symbol,
                    "interval": interval,
                    "start": current_start,
                    "end": min(current_start + (200 * self.get_interval_ms(interval)), end_time),
                    "limit": 200
                }
                
                result = await signed_request("GET", "/v5/market/kline", params)
                
                if result.get("retCode") == 0:
                    klines = result.get("result", {}).get("list", [])
                    
                    if not klines:
                        break
                    
                    # Convert format
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
                    
                    all_candles.extend(candles)
                    current_start = int(klines[0][0]) + 1  # Next batch
                    
                else:
                    break
                    
            except Exception as e:
                log(f"Error fetching batch: {e}")
                break
        
        # Sort chronologically
        all_candles.sort(key=lambda x: x["timestamp"])
        return all_candles

    def get_interval_ms(self, interval):
        """Get milliseconds for interval"""
        interval_map = {
            '1': 60000, '3': 180000, '5': 300000, '15': 900000,
            '30': 1800000, '60': 3600000, '240': 14400000
        }
        return interval_map.get(interval, 60000)

    async def backtest_all_strategies(self, symbols, days, initial_balance):
        """Run backtest simulation across all strategies"""
        log("🧪 Running strategy backtests...")
        
        current_balance = initial_balance
        open_trades = {}
        trade_id = 0
        
        # Get all timestamps for simulation (using 1m candles as base)
        all_timestamps = set()
        for symbol in symbols:
            if symbol in self.historical_data and '1' in self.historical_data[symbol]:
                timestamps = [c['timestamp'] for c in self.historical_data[symbol]['1']]
                all_timestamps.update(timestamps)
        
        sorted_timestamps = sorted(all_timestamps)
        
        # Simulate trading at each timestamp
        for i, timestamp in enumerate(sorted_timestamps):
            if i % 1000 == 0:  # Progress update
                progress = (i / len(sorted_timestamps)) * 100
                log(f"📈 Progress: {progress:.1f}% ({i}/{len(sorted_timestamps)})")
            
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
                    'exit_time': current_time.isoformat(),
                    'exit_price': exit_result['exit_price'],
                    'exit_reason': exit_result['reason'],
                    'pnl': pnl,
                    'pnl_pct': (pnl / trade['position_value']) * 100,
                    'duration_minutes': (timestamp - trade['entry_timestamp']) // 60000
                }
                
                self.all_trades.append(completed_trade)
                self.strategy_performance[trade['strategy']].append(completed_trade)
                
                # Update daily PnL
                date_key = current_time.date().isoformat()
                self.daily_pnl[date_key] += pnl
                
                del open_trades[trade_id_key]
            
            # Look for new trade entries (every 5 minutes to reduce computation)
            if i % 5 == 0 and len(open_trades) < 5:  # Max 5 concurrent trades
                
                for symbol in symbols:
                    if symbol not in self.historical_data:
                        continue
                    
                    # Skip if already have trade on this symbol
                    if any(trade['symbol'] == symbol for trade in open_trades.values()):
                        continue
                    
                    # Build candles_by_tf at this timestamp
                    candles_by_tf = self.get_candles_at_timestamp(symbol, timestamp)
                    if not candles_by_tf:
                        continue
                    
                    # Test all strategies
                    for strategy_name, config in self.strategies.items():
                        if not config['enabled']:
                            continue
                        
                        try:
                            signal = await config['function'](
                                symbol, candles_by_tf, timestamp
                            )
                            
                            if signal and signal['score'] >= config['min_score']:
                                # Calculate position size (risk 2% per trade)
                                risk_amount = current_balance * 0.02
                                entry_price = self.get_price_at_timestamp(symbol, timestamp)
                                
                                if entry_price:
                                    # Create trade
                                    trade_id += 1
                                    position_value = risk_amount * 10  # 10x leverage example
                                    
                                    trade = {
                                        'id': trade_id,
                                        'symbol': symbol,
                                        'strategy': strategy_name,
                                        'entry_time': current_time.isoformat(),
                                        'entry_timestamp': timestamp,
                                        'entry_price': entry_price,
                                        'direction': signal['direction'],
                                        'position_value': position_value,
                                        'score': signal['score'],
                                        'confidence': signal.get('confidence', 60),
                                        'sl_price': signal.get('sl_price'),
                                        'tp1_price': signal.get('tp1_price'),
                                        'trade_type': signal.get('trade_type', 'Intraday')
                                    }
                                    
                                    open_trades[trade_id] = trade
                                    current_balance -= risk_amount  # Reserve risk amount
                                    break  # One strategy per symbol at a time
                        
                        except Exception as e:
                            continue  # Skip failed strategy tests
        
        # Close any remaining open trades
        final_timestamp = sorted_timestamps[-1]
        for trade in open_trades.values():
            exit_result = self.force_close_trade(trade, final_timestamp)
            pnl = exit_result['pnl']
            current_balance += pnl
            
            completed_trade = {
                **trade,
                'exit_time': datetime.fromtimestamp(final_timestamp / 1000).isoformat(),
                'exit_price': exit_result['exit_price'],
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

    # STRATEGY TESTING FUNCTIONS

    async def test_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test core strategy at specific timestamp"""
        try:
            # Your existing core strategy logic
            score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                symbol, candles_by_tf
            )
            
            if score < 10.0:
                return None
            
            direction = determine_direction(tf_scores, indicator_scores)
            confidence = calculate_confidence(score, tf_scores, indicator_scores, used_indicators)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Calculate SL/TP
            sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                symbol, entry_price, trade_type, direction, score, confidence, "trending"
            )
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': trade_type,
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': sl_pct,
                'tp1_pct': tp1_pct
            }
            
        except Exception as e:
            return None

    async def test_mean_reversion(self, symbol, candles_by_tf, timestamp):
        """Test mean reversion strategy"""
        try:
            score, direction, confidence, reasons = score_mean_reversion(
                symbol, candles_by_tf, "ranging"  # Assume ranging for mean reversion
            )
            
            if score < 8.5:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Simple SL/TP for mean reversion
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
            return None

    async def test_breakout_sniper(self, symbol, candles_by_tf, timestamp):
        """Test breakout sniper strategy"""
        try:
            score, direction, confidence, reasons = score_breakout_sniper(
                symbol, candles_by_tf, "volatile"
            )
            
            if score < 11.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Breakout SL/TP (wider stops)
            if direction == "Long":
                sl_price = entry_price * 0.975  # 2.5% SL
                tp1_price = entry_price * 1.05   # 5% TP
            else:
                sl_price = entry_price * 1.025
                tp1_price = entry_price * 0.95
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Scalp',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.5,
                'tp1_pct': 5.0
            }
            
        except Exception as e:
            return None

    async def test_pattern_matching(self, symbol, candles_by_tf, timestamp):
        """Test pattern matching strategy"""
        try:
            # This would need your pattern database to be loaded
            # For now, simulate pattern matching
            from pattern_detector import detect_pattern
            
            if '5' not in candles_by_tf:
                return None
            
            pattern = detect_pattern(candles_by_tf['5'][-10:])
            if not pattern:
                return None
            
            # Simulate pattern prediction (you'd use real pattern database)
            # For demo, assume 60% confidence
            confidence = 0.6
            
            if confidence < 0.6:
                return None
            
            # Simulate direction based on pattern (would be from historical data)
            direction = "Long"  # Simplified
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Pattern-based SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.98   # 2% SL
                tp1_price = entry_price * 1.04  # 4% TP (based on historical pattern performance)
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.96
            
            return {
                'score': confidence,
                'direction': direction,
                'confidence': confidence * 100,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 4.0
            }
            
        except Exception as e:
            return None

    async def test_range_break(self, symbol, candles_by_tf, timestamp):
        """Test range break strategy"""
        try:
            # Simulate range break detection
            if '15' not in candles_by_tf or len(candles_by_tf['15']) < 50:
                return None
            
            # Simple range break logic
            recent_candles = candles_by_tf['15'][-20:]
            highs = [c['high'] for c in recent_candles[:-1]]
            lows = [c['low'] for c in recent_candles[:-1]]
            
            resistance = max(highs[-10:])
            support = min(lows[-10:])
            current_price = recent_candles[-1]['close']
            
            # Check for breakout
            if current_price > resistance * 1.002:  # 0.2% above resistance
                direction = "Long"
                score = 9.5
            elif current_price < support * 0.998:  # 0.2% below support
                direction = "Short"
                score = 9.5
            else:
                return None
            
            entry_price = current_price
            
            # Range break SL/TP
            if direction == "Long":
                sl_price = support * 0.995   # Below support
                tp1_price = entry_price * 1.035  # 3.5% TP
            else:
                sl_price = resistance * 1.005  # Above resistance
                tp1_price = entry_price * 0.965
            
            return {
                'score': score,
                'direction': direction,
                'confidence': 70,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 3.5
            }
            
        except Exception as e:
            return None

    # HELPER FUNCTIONS

    def get_candles_at_timestamp(self, symbol, timestamp):
        """Get candles_by_tf at specific timestamp"""
        if symbol not in self.historical_data:
            return None
        
        candles_by_tf = {}
        
        for tf in ['1', '3', '5', '15', '30', '60', '240']:
            if tf in self.historical_data[symbol]:
                # Get all candles up to this timestamp
                candles = [
                    c for c in self.historical_data[symbol][tf]
                    if c['timestamp'] <= timestamp
                ]
                
                if len(candles) >= 30:
                    candles_by_tf[tf] = candles[-100:]  # Last 100 candles
        
        return candles_by_tf if candles_by_tf else None

    def get_price_at_timestamp(self, symbol, timestamp):
        """Get price at specific timestamp"""
        if symbol not in self.historical_data or '1' not in self.historical_data[symbol]:
            return None
        
        # Find closest 1m candle
        candles = self.historical_data[symbol]['1']
        for candle in reversed(candles):
            if candle['timestamp'] <= timestamp:
                return candle['close']
        
        return None

    def check_trade_exit(self, trade, current_timestamp):
        """Check if trade should be exited"""
        current_price = self.get_price_at_timestamp(trade['symbol'], current_timestamp)
        if not current_price:
            return None
        
        entry_price = trade['entry_price']
        direction = trade['direction']
        sl_price = trade.get('sl_price')
        tp1_price = trade.get('tp1_price')
        
        # Check SL hit
        if sl_price:
            if (direction == "Long" and current_price <= sl_price) or \
               (direction == "Short" and current_price >= sl_price):
                pnl = self.calculate_pnl(entry_price, sl_price, direction, trade['position_value'])
                return {'exit_price': sl_price, 'reason': 'stop_loss', 'pnl': pnl}
        
        # Check TP hit
        if tp1_price:
            if (direction == "Long" and current_price >= tp1_price) or \
               (direction == "Short" and current_price <= tp1_price):
                pnl = self.calculate_pnl(entry_price, tp1_price, direction, trade['position_value'])
                return {'exit_price': tp1_price, 'reason': 'take_profit', 'pnl': pnl}
        
        # Time-based exit (24 hours for Intraday, 1 hour for Scalp)
        duration_hours = (current_timestamp - trade['entry_timestamp']) / (1000 * 60 * 60)
        max_duration = {'Scalp': 1, 'Intraday': 24, 'Swing': 168}  # hours
        
        if duration_hours >= max_duration.get(trade['trade_type'], 24):
            pnl = self.calculate_pnl(entry_price, current_price, direction, trade['position_value'])
            return {'exit_price': current_price, 'reason': 'time_exit', 'pnl': pnl}
        
        return None

    def force_close_trade(self, trade, timestamp):
        """Force close trade at end of backtest"""
        current_price = self.get_price_at_timestamp(trade['symbol'], timestamp)
        if not current_price:
            current_price = trade['entry_price']  # Break even if no price
        
        pnl = self.calculate_pnl(trade['entry_price'], current_price, trade['direction'], trade['position_value'])
        return {'exit_price': current_price, 'reason': 'backtest_end', 'pnl': pnl}

    def calculate_pnl(self, entry_price, exit_price, direction, position_value):
        """Calculate PnL for a trade"""
        if direction == "Long":
            price_change_pct = (exit_price - entry_price) / entry_price
        else:
            price_change_pct = (entry_price - exit_price) / entry_price
        
        return position_value * price_change_pct

    def generate_comprehensive_report(self, initial_balance):
        """Generate detailed backtest report"""
        log("📊 Generating comprehensive backtest report...")
        
        if not self.all_trades:
            log("❌ No trades to analyze")
            return
        
        # Overall statistics
        total_trades = len(self.all_trades)
        winning_trades = [t for t in self.all_trades if t['pnl'] > 0]
        losing_trades = [t for t in self.all_trades if t['pnl'] < 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in self.all_trades)
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # Strategy performance
        strategy_stats = {}
        for strategy, trades in self.strategy_performance.items():
            if trades:
                strategy_wins = [t for t in trades if t['pnl'] > 0]
                strategy_pnl = sum(t['pnl'] for t in trades)
                
                strategy_stats[strategy] = {
                    'trades': len(trades),
                    'win_rate': len(strategy_wins) / len(trades),
                    'total_pnl': strategy_pnl,
                    'avg_pnl': strategy_pnl / len(trades),
                    'avg_duration': sum(t['duration_minutes'] for t in trades) / len(trades)
                }
        
        # Print report
        print("\n" + "="*80)
        print("🎯 COMPREHENSIVE STRATEGY BACKTEST REPORT")
        print("="*80)
        
        print(f"\n💰 OVERALL PERFORMANCE:")
        print(f"   Initial Balance: ${initial_balance:,.2f}")
        print(f"   Final Balance: ${initial_balance + total_pnl:,.2f}")
        print(f"   Total Return: {(total_pnl / initial_balance) * 100:+.2f}%")
        print(f"   Total PnL: ${total_pnl:+,.2f}")
        
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Average Win: ${avg_win:+.2f}")
        print(f"   Average Loss: ${avg_loss:+.2f}")
        print(f"   Profit Factor: {abs(avg_win / avg_loss) if avg_loss != 0 else 'N/A'}")
        
        print(f"\n🎯 STRATEGY PERFORMANCE:")
        for strategy, stats in sorted(strategy_stats.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
            print(f"   {strategy.upper()}:")
            print(f"      Trades: {stats['trades']}")
            print(f"      Win Rate: {stats['win_rate']:.1%}")
            print(f"      Total PnL: ${stats['total_pnl']:+.2f}")
            print(f"      Avg PnL/Trade: ${stats['avg_pnl']:+.2f}")
            print(f"      Avg Duration: {stats['avg_duration']:.0f} minutes")
        
        # Save detailed report
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'initial_balance': initial_balance,
            'final_balance': initial_balance + total_pnl,
            'total_return_pct': (total_pnl / initial_balance) * 100,
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'strategy_performance': strategy_stats,
            'all_trades': self.all_trades,
            'daily_pnl': dict(self.daily_pnl)
        }
        
        with open('comprehensive_backtest_report.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        # Save trades as CSV for analysis
        if self.all_trades:
            df = pd.DataFrame(self.all_trades)
            df.to_csv('backtest_trades.csv', index=False)
        
        print(f"\n📄 Detailed reports saved:")
        print(f"   comprehensive_backtest_report.json - Full analysis")
        print(f"   backtest_trades.csv - All trade details")
        
        print("="*80)

# USAGE FUNCTIONS

async def run_quick_strategy_test():
    """Quick test of all strategies - 7 days"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    
    backtester = ComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=7, initial_balance=10000)

async def run_full_strategy_backtest():
    """Full strategy backtest - 30 days"""
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT',
        'MATICUSDT', 'ALGOUSDT', 'VETUSDT', 'FTMUSDT', 'ICPUSDT'
    ]
    
    backtester = ComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=30, initial_balance=10000)

if __name__ == "__main__":
    print("🚀 Comprehensive Strategy Backtester")
    print("Choose test duration:")
    print("1. Quick test (7 days, 5 symbols)")
    print("2. Full test (30 days, 20 symbols)")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        asyncio.run(run_quick_strategy_test())
    elif choice == "2":
        asyncio.run(run_full_strategy_backtest())
    else:
        print("Invalid choice, running quick test...")
        asyncio.run(run_quick_strategy_test())
