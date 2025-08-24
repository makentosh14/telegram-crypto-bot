# run_all_backtests.py - Simple script to backtest all strategies

import asyncio
from comprehensive_backtest import ComprehensiveBacktester

async def run_complete_backtest():
    """Run comprehensive backtest of all your strategies"""
    
    print("🚀 COMPLETE STRATEGY BACKTEST SYSTEM")
    print("=" * 50)
    print()
    print("This will test ALL your trading strategies:")
    print("✅ Core Strategy (score-based)")  
    print("✅ Mean Reversion")
    print("✅ Breakout Sniper")
    print("✅ Pattern Matching")
    print("✅ Range Break Detection")
    print()
    
    # Define test symbols (top liquid pairs)
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'MATICUSDT', 'ATOMUSDT', 'NEARUSDT', 'FTMUSDT'
    ]
    
    # Test parameters
    days = 14  # 2 weeks of data
    initial_balance = 10000  # $10,000 starting balance
    
    print(f"📊 Test Parameters:")
    print(f"   Symbols: {len(symbols)} top crypto pairs")
    print(f"   Time Period: {days} days")
    print(f"   Initial Balance: ${initial_balance:,.2f}")
    print(f"   Risk Per Trade: 2%")
    print(f"   Max Concurrent Trades: 5")
    print()
    
    print("⏰ Estimated time: 10-15 minutes")
    print("🔄 Starting backtest...")
    print()
    
    # Create and run comprehensive backtest
    backtester = ComprehensiveBacktester()
    
    try:
        await backtester.run_comprehensive_backtest(
            symbols=symbols,
            days=days, 
            initial_balance=initial_balance
        )
        
        print()
        print("🎉 BACKTEST COMPLETED SUCCESSFULLY!")
        print()
        print("📄 Generated Files:")
        print("   📊 comprehensive_backtest_report.json - Detailed analysis")
        print("   📈 backtest_trades.csv - All individual trades")
        print()
        print("🔍 Key Insights Available:")
        print("   • Which strategy performed best")
        print("   • Win rates for each approach") 
        print("   • Total returns and profitability")
        print("   • Average trade duration")
        print("   • Risk-adjusted performance")
        print()
        print("💡 Use this data to:")
        print("   ✨ Optimize strategy weightings")
        print("   🎯 Focus on best-performing approaches")
        print("   ⚙️  Fine-tune parameters")
        print("   🚫 Disable underperforming strategies")
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("🔧 Troubleshooting:")
        print("   • Check your API connection")
        print("   • Ensure all strategy modules are working")
        print("   • Try reducing the number of symbols")

# Custom backtest configurations
async def run_strategy_comparison():
    """Compare individual strategies head-to-head"""
    
    print("🥊 STRATEGY HEAD-TO-HEAD COMPARISON")
    print("=" * 50)
    
    # Test each strategy individually
    strategies_to_test = {
        'core_only': ['core_strategy'],
        'mean_reversion_only': ['mean_reversion'],
        'breakout_only': ['breakout_sniper'],
        'pattern_only': ['pattern_matching'],
        'range_break_only': ['range_break']
    }
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    results = {}
    
    for test_name, enabled_strategies in strategies_to_test.items():
        print(f"\n🧪 Testing: {test_name.replace('_', ' ').title()}")
        
        backtester = ComprehensiveBacktester()
        
        # Disable all strategies except the one being tested
        for strategy in backtester.strategies:
            backtester.strategies[strategy]['enabled'] = strategy in enabled_strategies
        
        await backtester.run_comprehensive_backtest(symbols, days=7, initial_balance=10000)
        
        # Store results
        if backtester.all_trades:
            total_pnl = sum(t['pnl'] for t in backtester.all_trades)
            win_rate = len([t for t in backtester.all_trades if t['pnl'] > 0]) / len(backtester.all_trades)
            results[test_name] = {
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'total_trades': len(backtester.all_trades),
                'return_pct': (total_pnl / 10000) * 100
            }
        else:
            results[test_name] = {
                'total_pnl': 0,
                'win_rate': 0,
                'total_trades': 0,
                'return_pct': 0
            }
    
    # Print comparison
    print(f"\n🏆 STRATEGY COMPARISON RESULTS")
    print(f"=" * 50)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['return_pct'], reverse=True)
    
    for i, (strategy, stats) in enumerate(sorted_results, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        print(f"{emoji} {strategy.replace('_', ' ').title()}")
        print(f"   Return: {stats['return_pct']:+.2f}%")
        print(f"   Win Rate: {stats['win_rate']:.1%}")
        print(f"   Trades: {stats['total_trades']}")
        print(f"   PnL: ${stats['total_pnl']:+.2f}")
        print()

async def run_timeframe_test():
    """Test strategies across different timeframes"""
    
    print("⏰ TIMEFRAME PERFORMANCE TEST")
    print("=" * 50)
    
    timeframes = [
        {'days': 3, 'name': '3-day (Recent)'},
        {'days': 7, 'name': '1-week (Short-term)'},
        {'days': 14, 'name': '2-week (Medium-term)'},
        {'days': 30, 'name': '1-month (Long-term)'}
    ]
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for timeframe in timeframes:
        print(f"\n📊 Testing {timeframe['name']}...")
        
        backtester = ComprehensiveBacktester()
        await backtester.run_comprehensive_backtest(
            symbols, 
            days=timeframe['days'], 
            initial_balance=10000
        )
        
        if backtester.all_trades:
            total_pnl = sum(t['pnl'] for t in backtester.all_trades)
            return_pct = (total_pnl / 10000) * 100
            win_rate = len([t for t in backtester.all_trades if t['pnl'] > 0]) / len(backtester.all_trades)
            
            print(f"   Return: {return_pct:+.2f}%")
            print(f"   Win Rate: {win_rate:.1%}")
            print(f"   Trades: {len(backtester.all_trades)}")

if __name__ == "__main__":
    print("🎯 STRATEGY BACKTEST SUITE")
    print("=" * 50)
    print()
    print("Choose backtest type:")
    print("1. 🚀 Complete Strategy Test (all strategies together)")
    print("2. 🥊 Strategy Comparison (head-to-head)")
    print("3. ⏰ Timeframe Analysis (performance across time periods)")
    print("4. 💨 Quick Test (fast 3-day test)")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        asyncio.run(run_complete_backtest())
    elif choice == "2":
        asyncio.run(run_strategy_comparison())
    elif choice == "3":
        asyncio.run(run_timeframe_test())
    elif choice == "4":
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        backtester = ComprehensiveBacktester()
        asyncio.run(backtester.run_comprehensive_backtest(symbols, days=3, initial_balance=10000))
    else:
        print("Invalid choice, running complete test...")
        asyncio.run(run_complete_backtest())
